from ..global_vars import (
    RABBITMQ_CONFIG,
    PUBLIC_KEY,
)
from ..sql import Message
from chassis.messaging import is_rabbitmq_healthy
from chassis.routers import (
    get_system_metrics,
    raise_and_log_error,
)
from chassis.security import create_jwt_verifier
from fastapi import (
    APIRouter,
    Depends,
    status,
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