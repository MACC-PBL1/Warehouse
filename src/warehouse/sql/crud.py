from .models import (
    Piece,
    Warehouse,
)
from chassis.sql import (
    get_element_by_id,
    get_list_statement_result,
    update_elements_statement_result,
)
from sqlalchemy import (
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

async def cancel_queued_pieces_in_order(
    db: AsyncSession,
    order_id: int,
) -> list[Piece]:
    await update_elements_statement_result(
        db=db,
        stmt=(
            update(Piece)
                .where(Piece.order_id == order_id)
                .where(Piece.status == Piece.STATUS_QUEUED)
                .values(status=Piece.STATUS_CANCELLED)
        )
    )
    return await get_list_statement_result(
        db=db,
        stmt=(
            select(Piece)
                .where(Piece.order_id == order_id)
                .where(Piece.status == Piece.STATUS_CANCELLED)
        )
    )

async def create_piece(
    db: AsyncSession,
    order_id: int,
    piece_type: str,
) -> Piece:
    piece = Piece(
        order_id=order_id,
        type=piece_type,
        status=Piece.STATUS_QUEUED,
    )
    db.add(piece)
    await db.flush()
    await db.commit()
    await db.refresh(piece)
    return piece

async def create_warehouse(db: AsyncSession, warehouse_id: int) -> Warehouse:
    warehouse = Warehouse(id=warehouse_id, reserved=0)
    db.add(warehouse)
    await db.flush()
    await db.commit()
    await db.refresh(warehouse)
    return warehouse

async def derregister_active_pieces_from_order(
    db: AsyncSession,
    order_id: int,
) -> None:
    await update_elements_statement_result(
        db=db,
        stmt=(
            update(Piece)
                .where(Piece.order_id == order_id)
                .where(
                    (Piece.status == Piece.STATUS_PRODUCED) | 
                    (Piece.status == Piece.STATUS_PRODUCING)
                )
                .values(order_id=None)
        )
    )

async def get_free_pieces(
    db: AsyncSession,
    piece_type: str,
    quantity: Optional[int],
) -> list[Piece]:
    return await get_list_statement_result(
        db=db,
        stmt=(
            select(Piece)
                .where(Piece.order_id == None)
                .where(Piece.status == Piece.STATUS_PRODUCED)
                .where(Piece.type == piece_type)
        )
        .with_for_update(skip_locked=True)
        .limit(quantity)
    )

async def get_piece(
    db: AsyncSession,
    piece_id: int,
) -> Optional[Piece]:
    return await get_element_by_id(
        db=db,
        model=Piece,
        element_id=piece_id,
    )

async def get_pieces_by_order(
    db: AsyncSession,
    order_id: int,
) -> list[Piece]:
    return await get_list_statement_result(
        db=db,
        stmt=select(Piece).where(Piece.order_id == order_id),
    )

async def get_warehouse(
    db: AsyncSession,
    warehouse_id: int,
) -> Optional[Warehouse]:
    return await get_element_by_id(
        db=db,
        model=Warehouse,
        element_id=warehouse_id,
    )

async def release_pieces(
    db: AsyncSession,
    warehouse_id: int,
    quantity: int,
) -> None:
    await update_elements_statement_result(
        db=db,
        stmt=(
            update(Warehouse)
                .where(Warehouse.id == warehouse_id)
                .values(reserved=Warehouse.reserved - quantity)
        )
    )

async def reserve_pieces(
    db: AsyncSession,
    warehouse_id: int,
    quantity: int,
    max_capacity: int
) -> None:
    result = await (await db.connection()).execute(
        update(Warehouse)
            .where(Warehouse.id == warehouse_id)
            .where(Warehouse.reserved + quantity <= max_capacity)
            .values(reserved=Warehouse.reserved + quantity) 
    )

    await db.commit()

    if result.rowcount == 0:
        raise ValueError("Warehouse capacity exceeded")

async def update_piece(
    db: AsyncSession,
    piece: Piece,
    **updates,
) -> Optional[Piece]:
    """
    Update multiple fields on a Piece object using direct UPDATE statement.
    
    Example:
        await update_piece(db, piece, status="completed", order_id=5)
    """
    if not updates:
        return piece
    
    piece_id = piece.id

    await update_elements_statement_result(
        db=db,
        stmt=update(Piece)
                .where(Piece.id == piece_id)
                .values(**updates)
    )
    return await get_element_by_id(db=db, model=Piece, element_id=piece_id)
