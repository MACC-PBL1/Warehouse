# warehouse/crud.py
from .models import PieceModel
from chassis.sql import (
    get_list_statement_result,
    get_element_statement_result,
)
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# =========================
# PIECE (WAREHOUSE)
# =========================

async def create_piece(
    db: AsyncSession,
    order_id: int,
) -> PieceModel:
    piece = PieceModel(
        order_id=order_id,
        status=PieceModel.STATUS_CREATED,
    )
    db.add(piece)
    await db.commit()
    await db.refresh(piece)
    return piece



async def get_piece(
    db: AsyncSession,
    piece_id: int,
) -> Optional[PieceModel]:
    return await get_element_statement_result(
        db=db,
        stmt=select(PieceModel).where(PieceModel.id == piece_id),
    )


async def get_pieces(db: AsyncSession) -> List[PieceModel]:
    return await get_list_statement_result(
        db=db,
        stmt=select(PieceModel),
    )


async def get_pieces_by_order(
    db: AsyncSession,
    order_id: int,
) -> List[PieceModel]:
    return await get_list_statement_result(
        db=db,
        stmt=select(PieceModel).where(PieceModel.order_id == order_id),
    )


async def get_pieces_by_status(
    db: AsyncSession,
    status: str,
) -> List[PieceModel]:
    return await get_list_statement_result(
        db=db,
        stmt=select(PieceModel).where(PieceModel.status == status),
    )


async def mark_piece_queued(
    db: AsyncSession,
    piece_id: int,
) -> Optional[PieceModel]:
    piece = await get_piece(db, piece_id)
    if piece:
        piece.status = PieceModel.STATUS_QUEUED
        await db.commit()
        await db.refresh(piece)
    return piece


async def mark_piece_manufacturing_started(
    db: AsyncSession,
    piece_id: int,
) -> Optional[PieceModel]:
    piece = await get_piece(db, piece_id)
    if piece:
        piece.status = PieceModel.STATUS_MANUFACTURING
        piece.manufacturing_started_at = datetime.utcnow()
        await db.commit()
        await db.refresh(piece)
    return piece


async def mark_piece_manufactured(
    db: AsyncSession,
    piece_id: int,
) -> Optional[PieceModel]:
    piece = await get_piece(db, piece_id)
    if piece:
        piece.status = PieceModel.STATUS_MANUFACTURED
        piece.manufactured_at = datetime.utcnow()
        await db.commit()
        await db.refresh(piece)
    return piece




async def are_all_pieces_manufactured(
    db: AsyncSession,
    order_id: int,
) -> bool:

    pieces = await get_pieces_by_order(db, order_id)

    if not pieces:
        logger.warning(
            "[WAREHOUSE] - No pieces found for order_id=%s",
            order_id,
        )
        return False

    for piece in pieces:
        if piece.status != PieceModel.STATUS_MANUFACTURED:
            return False
    return True

async def cancel_pieces_by_order(
    db: AsyncSession,
    order_id: int,
) -> int:
    """
    Cancels all cancellable pieces for an order.
    Rules:
    - MANUFACTURED → NO SE TOCA
    - MANUFACTURING → NO SE TOCA 
    - CREATED / QUEUED → CANCELLED
    """

    pieces = await get_pieces_by_order(db, order_id)

    cancelled_count = 0

    for piece in pieces:
        if piece.status in (
            PieceModel.STATUS_CREATED,
            PieceModel.STATUS_QUEUED,
        ):
            piece.status = PieceModel.STATUS_CANCELLED


            piece.order_id = None

            cancelled_count += 1

    await db.commit()

    logger.info(
        "[WAREHOUSE] - cancel_pieces_by_order: order_id=%s cancelled=%s",
        order_id,
        cancelled_count,
    )

    return cancelled_count



async def get_free_pieces(
    db: AsyncSession,
    limit: int,
) -> list[PieceModel]:
    return await get_list_statement_result(
        db=db,
        stmt=(
            select(PieceModel)
            .where(
                PieceModel.order_id.is_(None),
                PieceModel.status == PieceModel.STATUS_MANUFACTURED,
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    )
