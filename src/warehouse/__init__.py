from .business_logic import WarehouseManager
from .global_vars import (
    LISTENING_QUEUES,
    RABBITMQ_CONFIG,
)
from chassis.logging import (
    get_logger,
    setup_rabbitmq_logging,
)
from chassis.messaging import start_rabbitmq_listener
from chassis.consul import CONSUL_CLIENT
from chassis.sql import (
    Base,
    Engine,
)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from hypercorn.asyncio import serve
from hypercorn.config import Config
from threading import Thread
import asyncio
import logging.config
import os
import socket

# Configure logging ################################################################################
logging.config.fileConfig(
    os.path.join(os.path.dirname(__file__), "logging.ini")
)
setup_rabbitmq_logging(
    rabbitmq_config=RABBITMQ_CONFIG,
    capture_dependencies=True,
)
logger = get_logger(__name__)

from .routers import Router
from .messaging import *

# App Lifespan #####################################################################################
@asynccontextmanager
async def lifespan(__app: FastAPI):
    try:
        logger.info("[LOG:WAREHOUSE] - Starting up")
        try:
            # Create DB tables
            logger.info("[LOG:WAREHOUSE] - Creating database tables")
            async with Engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            await WarehouseManager.create()

            logger.info("[LOG:WAREHOUSE] - Starting RabbitMQ listeners")
            try:
                for _, queue in LISTENING_QUEUES.items():
                    Thread(
                        target=start_rabbitmq_listener,
                        args=(queue, RABBITMQ_CONFIG),
                        daemon=True,
                    ).start()
            except Exception as e:
                logger.error(
                    f"[LOG:WAREHOUSE] - Could not start RabbitMQ listeners: {e}",
                    exc_info=True
                )
            logger.info("[LOG:WAREHOUSE] - Registering service to Consul")
            try:
                CONSUL_CLIENT.register_service(
                    service_name="warehouse",
                    ec2_address=os.getenv("HOST_IP", socket.gethostbyname(socket.gethostname())),
                    service_port=int(os.getenv("HOST_PORT", 8000)),
                )
            except Exception as e:
                logger.error(
                    f"[LOG:WAREHOUSE] - Failed to register with Consul: {e}",
                    exc_info=True
                )
            yield
        except Exception as e:
            logger.error(f"[LOG:ORDER] - Could not create tables at startup: Reason={e}", exc_info=True)
    finally:
        logger.info("[LOG:WAREHOUSE] - Shutting down database")
        await Engine.dispose()
        CONSUL_CLIENT.deregister_service()




# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
logger.info("[LOG:WAREHOUSE] - Running app version %s", APP_VERSION)

DESCRIPTION = """
Warehouse service responsible for production and piece lifecycle management.
"""

tag_metadata = [
    {
        "name": "Warehouse",
        "description": "Production and inventory management",
    },
    {
        "name": "Piece",
        "description": "Piece lifecycle and order association",
    },
]

APP = FastAPI(
    redoc_url=None,
    title="FastAPI - Warehouse app",
    description=DESCRIPTION,
    version=APP_VERSION,
    servers=[{"url": "/", "description": "Development"}],
    license_info={
        "name": "MIT License",
        "url": "https://choosealicense.com/licenses/mit/",
    },
    openapi_tags=tag_metadata,
    lifespan=lifespan,
)

APP.include_router(Router)


def start_server():
    config = Config()
    config.bind = [
        os.getenv("HOST", "0.0.0.0")
        + ":"
        + os.getenv("PORT", "8000")
    ]
    config.workers = int(os.getenv("WORKERS", "1"))

    logger.info(
        "[LOG:WAREHOUSE] - Starting Hypercorn server on %s",
        config.bind
    )

    asyncio.run(serve(APP, config))  # type: ignore