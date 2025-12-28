from ..global_vars import (
    RABBITMQ_CONFIG,
    PUBLIC_KEY,
)

from ..sql import (
    Message,
    Piece,
    PieceModel,
)

from chassis.messaging import is_rabbitmq_healthy
from chassis.routers import (
    get_system_metrics,
    raise_and_log_error,
)
from chassis.security import create_jwt_verifier
from chassis.sql import (
    get_db,
    get_list,
    get_list_statement_result,
    get_element_statement_result,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import (
    List,
    Optional,
)
import logging
import socket

logger = logging.getLogger(__name__)

Router = APIRouter(prefix="/warehouse", tags=["Warehouse"])


@Router.get(
    "/health",
    summary="Health check endpoint",
    response_model=Message,
)
async def health_check():
    if not is_rabbitmq_healthy(RABBITMQ_CONFIG):
        raise_and_log_error(
            logger=logger,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message="[LOG:REST] - RabbitMQ not reachable",
        )

    container_id = socket.gethostname()
    logger.debug(f"[LOG:REST] - GET '/warehouse/health' served by {container_id}")

    return {
        "detail": f"OK - Served by {container_id}",
        "system_metrics": get_system_metrics(),
    }


@Router.get(
    "/health/auth",
    summary="Health check endpoint (JWT protected)",
    response_model=Message,
)
async def health_check_auth(
    token_data: dict = Depends(create_jwt_verifier(lambda: PUBLIC_KEY["key"], logger))
):
    logger.debug("[LOG:REST] - GET '/warehouse/health/auth' endpoint called.")

    user_id = token_data.get("sub")
    user_role = token_data.get("role")

    logger.info(
        "[LOG:REST] - Valid JWT: user_id=%s, role=%s",
        user_id,
        user_role,
    )

    return {
        "detail": (
            "Warehouse service is running. "
            f"Authenticated as (id={user_id}, role={user_role})"
        ),
        "system_metrics": get_system_metrics(),
    }

@Router.get(
    "/pieces",
    response_model=List[Piece],
    summary="Lista de todas las piezas en producción",
)
async def get_all_pieces(
    token_data: dict = Depends(create_jwt_verifier(lambda: PUBLIC_KEY["key"], logger)),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("[LOG:REST] - GET '/warehouse/pieces' endpoint called.")

    user_role = token_data.get("role")
    if user_role != "admin":
        raise_and_log_error(
            logger,
            status.HTTP_401_UNAUTHORIZED,
            f"Access denied: user_role={user_role} (admin required)",
        )
    return await get_list(db, PieceModel)


@Router.get(
    "/pieces/order/{order_id}",
    response_model=List[Piece],
    summary="Lista de piezas por order_id",
)
async def get_pieces_by_order(
    order_id: int,
    token_data: dict = Depends(create_jwt_verifier(lambda: PUBLIC_KEY["key"], logger)),
    db: AsyncSession = Depends(get_db),
):
    logger.debug(
        "[LOG:REST] - GET '/warehouse/pieces/order/%s' endpoint called.",
        order_id,
    )

    user_role = token_data.get("role")
    if user_role != "admin":
        raise_and_log_error(
            logger,
            status.HTTP_401_UNAUTHORIZED,
            f"Access denied: user_role={user_role} (admin required)",
        )

    return await get_list_statement_result(
        db=db,
        stmt=select(PieceModel).where(PieceModel.order_id == order_id),
    )

@Router.get(
    "/pieces/{piece_id}",
    response_model=Piece,
    summary="Información de una pieza específica",
)
async def get_piece_detail(
    piece_id: int,
    token_data: dict = Depends(create_jwt_verifier(lambda: PUBLIC_KEY["key"], logger)),
    db: AsyncSession = Depends(get_db),
):
    logger.debug(
        "[LOG:REST] - GET '/warehouse/pieces/%s' endpoint called.",
        piece_id,
    )

    user_role = token_data.get("role")
    if user_role != "admin":
        raise_and_log_error(
            logger,
            status.HTTP_401_UNAUTHORIZED,
            f"Access denied: user_role={user_role} (admin required)",
        )

    piece: Optional[PieceModel] = await get_element_statement_result(
        db=db,
        stmt=select(PieceModel).where(PieceModel.id == piece_id),
    )

    if piece is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Piece not found",
        )

    return piece
