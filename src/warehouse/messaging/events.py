from ..business_logic import WarehouseManager
from ..global_vars import (
    LISTENING_QUEUES,
    PUBLIC_KEY,
    RABBITMQ_CONFIG,
)
from ..sql import OrderPieceSchema
from chassis.consul import CONSUL_CLIENT
from chassis.messaging import (
    MessageType,
    RabbitMQPublisher,
    register_queue_handler,
)
from typing import cast
import logging
import requests

logger = logging.getLogger(__name__)

@register_queue_handler(LISTENING_QUEUES["piece_request"])
async def piece_request(message: MessageType) -> None:
    assert (order_id := message.get("order_id")) is not None, "'order_id' should be present"
    assert (pieces := message.get("pieces")) is not None, "'pieces' should be present"

    order_id = int(order_id)
    pieces = cast(list[OrderPieceSchema], list(pieces))
    
    logger.info(f"[EVENT:WAREHOUSE:PIECES_REQUESTED] - order_id={order_id} pieces={pieces}")

    await WarehouseManager.produce_pieces(
        order_id=order_id,
        pieces=pieces,
    )

@register_queue_handler(
    queue=LISTENING_QUEUES["piece_producing"],
    exchange="machine_events",
    exchange_type="topic",
    routing_key="machine.piece.producing",
)
async def piece_producing(message: MessageType) -> None:
    assert (piece_id := message.get("piece_id")) is not None, "'piece_id' should exist"
    piece_id = int(piece_id)
    await WarehouseManager.piece_producing(piece_id)
    logger.info(f"[EVENT:WAREHOUSE:PIECE_PRODUCING] - piece_id={piece_id}")

@register_queue_handler(
    queue=LISTENING_QUEUES["piece_produced"],
    exchange="machine_events",
    exchange_type="topic",
    routing_key="machine.piece.produced",
)
async def piece_produced(message: MessageType) -> None:
    assert (piece_id := message.get("piece_id")) is not None, "'piece_id' should be present"
    piece_id = int(piece_id)
    await WarehouseManager.piece_produced(piece_id)
    logger.info(f"[EVENT:WAREHOUSE:PIECE_PRODUCED] - piece_id={piece_id}")

@register_queue_handler(
    queue=LISTENING_QUEUES["saga_reserve"],
    exchange="cmd",
    exchange_type="topic",
    routing_key="warehouse.reserve",
)
async def warehouse_reservation(message: MessageType) -> None:
    assert (order_id := message.get("order_id")) is not None, "'order_id' should exist"
    assert (response_exchange := message.get("response_exchange")) is not None, "'response_exchange' should exist"
    assert (response_exchange_type := message.get("response_exchange_type")) is not None, "'response_exchange_type' should exist"
    assert (response_routing_key := message.get("response_routing_key")) is not None, "'response_routing_key' should exist"

    order_id = int(order_id)
    response_exchange = str(response_exchange)
    response_exchange_type = str(response_exchange_type)
    response_routing_key = str(response_routing_key)
    response = {}

    logger.info(
        "[CMD:WAREHOUSE_RESERVE:RECEIVED] - Received reserve command: "
        f"order_id={order_id}"
    )

    try:
        await WarehouseManager.try_reserve_space(order_id)
        response["status"] = "OK"
        logger.info(
            "[EVENT:WAREHOUSE_RESERVE:SUCCESS] - Warehouse space reserved: "
            f"order_id={order_id}"
        )
    except Exception as e:
        response["status"] = f"Error: {e}"
        logger.info(
            "[EVENT:PAYMENT_RESERVE:FAILED] - Payment reserve failed: "
            f"order_id={order_id}, "
            f"status='{response["status"]}'"
        )

    with RabbitMQPublisher(
        queue="",
        rabbitmq_config=RABBITMQ_CONFIG,
        exchange=response_exchange,
        exchange_type=response_exchange_type,
        routing_key=response_routing_key,
        auto_delete_queue=True,
    ) as publisher:
        publisher.publish(response)

@register_queue_handler(
    queue=LISTENING_QUEUES["saga_release"],
    exchange="cmd",
    exchange_type="topic",
    routing_key="warehouse.release",
)
async def warehouse_release(message: MessageType) -> None:
    assert (order_id := message.get("order_id")) is not None, "'order_id' should exist"

    order_id = int(order_id)

    logger.info(
        "[CMD:WAREHOUSE_RELEASE:RECEIVED] - Received release command: "
        f"order_id={order_id}, "
    )

    await WarehouseManager.release_space(order_id)

@register_queue_handler(
    queue=LISTENING_QUEUES["saga_cancel"],
    exchange="cancellation-approved",
    exchange_type="fanout",
)
async def warehouse_cancel(message: MessageType) -> None:
    assert (order_id := message.get("order_id")) is not None, "'order_id' should exist"

    order_id = int(order_id)

    logger.info(
        "[EVENT:WAREHOUSE_CANCEL:RECEIVED] - Received order cancel command: "
        f"order_id={order_id}, "
    )
    await WarehouseManager.cancel_order(order_id)

@register_queue_handler(
    queue=LISTENING_QUEUES["public_key"],
    exchange="public_key",
    exchange_type="fanout"
)
def public_key(message: MessageType) -> None:
    global PUBLIC_KEY
    assert (auth_base_url := CONSUL_CLIENT.discover_service("auth")) is not None, (
        "The 'auth' service should be accesible"
    )
    assert "public_key" in message, "'public_key' field should be present."
    assert message["public_key"] == "AVAILABLE", (
        f"'public_key' value is '{message['public_key']}', expected 'AVAILABLE'"
    )
    address, port = auth_base_url
    response = requests.get(f"{address}:{port}/auth/key", timeout=5)
    assert response.status_code == 200, (
        f"Public key request returned '{response.status_code}', should return '200'"
    )
    data: dict = response.json()
    new_key = data.get("public_key")
    assert new_key is not None, (
        "Auth response did not contain expected 'public_key' field."
    )
    PUBLIC_KEY["key"] = str(new_key)
    logger.info(
        "[EVENT:PUBLIC_KEY:UPDATED] - Public key updated: "
        f"key={PUBLIC_KEY["key"]}"
    )