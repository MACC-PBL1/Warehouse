from ..global_vars import RABBITMQ_CONFIG
from ..sql import (
    cancel_queued_pieces_in_order,
    create_piece,
    create_warehouse,
    derregister_active_pieces_from_order,
    get_free_pieces,
    get_piece,
    get_pieces_by_order,
    get_warehouse,
    OrderPieceSchema,
    Piece,
    release_pieces,
    reserve_pieces,
    update_piece,
)
from chassis.messaging import RabbitMQPublisher
from chassis.sql import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import (
    Type,
    TypeVar,
)
import logging
import os

logger = logging.getLogger(__name__)

WarehouseManagerType = TypeVar("WarehouseManagerType", bound="WarehouseManager")

class WarehouseManager:
    """"""
    WAREHOUSE_ID = 1
    MAX_CAPACITY = int(os.getenv("WAREHOUSE_CAPACITY", "1000"))

    def __init__(self) -> None:
        pass

    @classmethod
    async def create(cls: Type[WarehouseManagerType]) -> None:
        async with SessionLocal() as db:
            warehouse = await get_warehouse(db, WarehouseManager.WAREHOUSE_ID)
            if warehouse is None:
                warehouse = await create_warehouse(db, WarehouseManager.WAREHOUSE_ID)

    @staticmethod
    def _ask_piece(piece_id: int, piece_type: str) -> None:
        with RabbitMQPublisher(
            queue="",
            rabbitmq_config=RABBITMQ_CONFIG,
            exchange="machine",
            exchange_type="topic",
            routing_key=f"machine.piece.produce.{piece_type}",
            auto_delete_queue=True,
        ) as publisher:
            publisher.publish({
                "piece_id": piece_id,
                "piece_type": piece_type,
            })

    @staticmethod
    async def _cancel_queued(order_id: int) -> None:
        async with SessionLocal() as db:           
            canceled_pieces = await cancel_queued_pieces_in_order(db, order_id)
            for piece in canceled_pieces:
                await WarehouseManager._send_cancel_piece(piece)

    @staticmethod
    async def _create_piece_entry(order_id: int, piece_type: str) -> int:
        async with SessionLocal() as db:
            piece = await create_piece(db, order_id, piece_type)
            return piece.id

    @staticmethod
    async def _is_order_completed(db: AsyncSession, order_id: int) -> bool:
        logger.info("is_completed??")
        pieces = await get_pieces_by_order(db, order_id)
        logger.info(f"ORDER_COMPLETION - pieces={pieces}")
        return all(piece.status == Piece.STATUS_PRODUCED for piece in pieces)

    @staticmethod
    def _notify_order_completion(order_id: int) -> None:
        with RabbitMQPublisher(
            queue="order.status.update",
            rabbitmq_config=RABBITMQ_CONFIG,
        ) as publisher:
            publisher.publish({
                "order_id": order_id,
                "status": "Processed"
            })

    @staticmethod
    async def _reallocate_pieces(order_id: int, piece_type: str, quantity: int) -> int:
        async with SessionLocal() as db:
            free_pieces = await get_free_pieces(db, piece_type, quantity)
            free_piece_ids = [piece.id for piece in free_pieces]
            for free_piece_id in free_piece_ids:
                assert (free_piece := await get_piece(db, free_piece_id)) is not None, "Piece should exist."
                assert (await update_piece(db, free_piece, order_id=order_id)) is not None, "Should update an existing piece"
        return len(free_pieces)
    
    @staticmethod
    async def _send_cancel_piece(piece: Piece) -> None:
        with RabbitMQPublisher(
            queue="",
            rabbitmq_config=RABBITMQ_CONFIG,
            exchange="machine_cancel",
            exchange_type="fanout",
            auto_delete_queue=True,
        ) as publisher:
            publisher.publish({
                "piece_id": piece.id,
            })

    @staticmethod
    async def cancel_order(order_id: int) -> None:
        async with SessionLocal() as db:
            await derregister_active_pieces_from_order(db, order_id)

    @staticmethod
    async def piece_produced(piece_id: int) -> None:
        async with SessionLocal() as db:
            assert (piece := await get_piece(db, piece_id)) is not None, "Piece should exist"
            assert (await update_piece(db, piece, status=Piece.STATUS_PRODUCED)) is not None, "Should update an existing piece"

            if piece.order_id is None:
                return

            if await WarehouseManager._is_order_completed(db, piece.order_id):
                WarehouseManager._notify_order_completion(piece.order_id)

    @staticmethod
    async def piece_producing(piece_id: int) -> None:
        async with SessionLocal() as db:
            assert (piece := await get_piece(db, piece_id)) is not None, "Piece should exist"
            assert (await update_piece(db, piece, status=Piece.STATUS_PRODUCING)) is not None, "Should update an existing piece"

    @staticmethod
    async def produce_pieces(order_id: int, pieces: list[OrderPieceSchema]) -> None:
        total_missing = 0

        for piece_type in pieces:
            reused_piece_count = await WarehouseManager._reallocate_pieces(
                order_id=order_id, 
                piece_type=piece_type["type"],
                quantity=piece_type["quantity"],
            )

            missing_pieces = piece_type["quantity"] - reused_piece_count

            for _ in range(missing_pieces):
                WarehouseManager._ask_piece(
                    piece_id=await WarehouseManager._create_piece_entry(order_id, piece_type["type"]),
                    piece_type=piece_type["type"],
                )

            total_missing += missing_pieces

        if total_missing == 0:
            WarehouseManager._notify_order_completion(order_id)

    @staticmethod
    async def release_space(order_id: int) -> None:
        async with SessionLocal() as db:
            all_pieces = await get_pieces_by_order(db, order_id)
            active_piece_count = sum(1 for piece in all_pieces if piece.status in [Piece.STATUS_PRODUCED, Piece.STATUS_PRODUCING])
            await release_pieces(db, WarehouseManager.WAREHOUSE_ID, active_piece_count)

    @staticmethod
    async def try_reserve_space(order_id: int) -> None:
        await WarehouseManager._cancel_queued(order_id)

        async with SessionLocal() as db:
            all_pieces = await get_pieces_by_order(db, order_id)
            active_pieces_count = sum(1 for piece in all_pieces if piece.status in [Piece.STATUS_PRODUCED, Piece.STATUS_PRODUCING])
            await reserve_pieces(db, WarehouseManager.WAREHOUSE_ID, active_pieces_count, WarehouseManager.MAX_CAPACITY)