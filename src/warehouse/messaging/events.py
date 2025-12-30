from ..global_vars import (
    LISTENING_QUEUES,
    PUBLISHING_QUEUES,
    PUBLIC_KEY,
    RABBITMQ_CONFIG,
)
from ..sql import (
    create_piece,
    mark_piece_queued,
    mark_piece_manufactured,
    are_all_pieces_manufactured,  
    get_pieces_by_order,
    get_piece,
    get_free_pieces,
    PieceModel,
)
from chassis.messaging import (
    MessageType,
    register_queue_handler,
    RabbitMQPublisher,
)
from chassis.sql import SessionLocal
from chassis.consul import ConsulClient
import requests
import logging

logger = logging.getLogger(__name__)

@register_queue_handler(LISTENING_QUEUES["order_created"])
async def order_created(message: MessageType) -> None:
    assert (order_id := message.get("order_id")) is not None
    assert (pieces := message.get("pieces")) is not None

    order_id = int(order_id)

    logger.info(
        "[EVENT:WAREHOUSE:ORDER_CREATED] - order_id=%s pieces=%s",
        order_id,
        pieces,
    )

    machine_piece_ids: list[tuple[int, str]] = []  # (piece_id, piece_type)

    async with SessionLocal() as db:

        for item in pieces:
            piece_type = item["piece_type"]
            quantity = int(item["quantity"])

            # REUTILIZAR PIEZAS YA FABRICADAS (POR TIPO)
            free_pieces = await get_free_pieces(
                db=db,
                piece_type=piece_type,
                limit=quantity,
            )

            for piece in free_pieces:
                piece.order_id = order_id
                logger.info(
                    "[WAREHOUSE] - Reusing %s piece_id=%s for order_id=%s",
                    piece_type,
                    piece.id,
                    order_id,
                )

            missing = quantity - len(free_pieces)


            #  CREAR PIEZAS NUEVAS (SOLO LAS QUE FALTAN)
            for _ in range(missing):
                piece = await create_piece(
                    db=db,
                    order_id=order_id,
                    piece_type=piece_type,
                )
                piece.status = PieceModel.STATUS_QUEUED
                machine_piece_ids.append((piece.id, piece_type))

        await db.commit()


        # SI NO HAY NADA QUE FABRICAR → ORDER COMPLETED
        if not machine_piece_ids:
            with RabbitMQPublisher(
                queue=PUBLISHING_QUEUES["order_completed"],
                rabbitmq_config=RABBITMQ_CONFIG,
            ) as publisher:
                publisher.publish({"order_id": order_id})

            logger.info(
                "[EVENT:WAREHOUSE:ORDER_COMPLETED] - order_id=%s (all reused)",
                order_id,
            )
            return

    #  NOTIFICAR A MACHINE: SOLO PIEZAS NUEVAS, POR TIPO
    for piece_id, piece_type in machine_piece_ids:
        queue_name = PUBLISHING_QUEUES[f"machine_piece_{piece_type}"]

        with RabbitMQPublisher(
            queue=queue_name,
            rabbitmq_config=RABBITMQ_CONFIG,
        ) as publisher:
            publisher.publish({
                "piece_id": piece_id,
                "piece_type": piece_type,
            })

    logger.info(
        "[EVENT:WAREHOUSE:PIECES_ASSIGNED] - order_id=%s created=%s",
        order_id,
        len(machine_piece_ids),
    )


@register_queue_handler(LISTENING_QUEUES["piece_executed"])
async def piece_executed(message: MessageType) -> None:
    piece_id = int(message["piece_id"])
    piece_type = message.get("piece_type")  

    async with SessionLocal() as db:
        piece = await get_piece(db, piece_id)

        if piece is None:
            return

        if piece.order_id is None:
            piece.status = piece.STATUS_MANUFACTURED
            await db.commit()
            logger.info(
                "[WAREHOUSE] - Executed piece %s (type=%s) stored as free stock",
                piece_id,
                piece_type,
            )
            return

        #  PIEZA CANCELADA → IGNORAR
        if piece.status == piece.STATUS_CANCELLED:
            logger.info(
                "[WAREHOUSE] - Ignoring executed cancelled piece %s",
                piece_id,
            )
            return

        #  Caso normal
        piece = await mark_piece_manufactured(db, piece_id)
        order_id = piece.order_id

        all_done = await are_all_pieces_manufactured(db, order_id)
        await db.commit()


    if all_done:
        with RabbitMQPublisher(
            queue=PUBLISHING_QUEUES["order_completed"],
            rabbitmq_config=RABBITMQ_CONFIG,
        ) as publisher:
            publisher.publish({"order_id": order_id})

        logger.info(
            "[EVENT:WAREHOUSE:ORDER_COMPLETED] - order_id=%s",
            order_id,
        )


@register_queue_handler(LISTENING_QUEUES["warehouse_cancel"])
async def warehouse_cancel(message: MessageType) -> None:
    """
    Cancels an order:
    - Releases reusable pieces back to stock
    - Best-effort cancels technical tasks in Machine
    """
    assert (order_id := message.get("order_id")) is not None, "'order_id' is required"
    order_id = int(order_id)

    logger.info(
        "[EVENT:WAREHOUSE:CANCEL] - Cancelling order_id=%s",
        order_id,
    )

    async with SessionLocal() as db:
        pieces = await get_pieces_by_order(db, order_id)

        machine_cancel_piece_ids: list[int] = []

        for piece in pieces:

            if piece.status in (
                piece.STATUS_CREATED,
                piece.STATUS_QUEUED,
            ):
                piece.status = piece.STATUS_CANCELLED
                piece.order_id = None  #  LIBERADA
                machine_cancel_piece_ids.append(piece.id)

            #  EN EJECUCIÓN 
            elif piece.status == piece.STATUS_MANUFACTURING:
                machine_cancel_piece_ids.append(piece.id)

            #  MANUFACTURED → stock, no tocar
            elif piece.status == piece.STATUS_MANUFACTURED:
                piece.order_id = None #LIBERADA (para reutilizarse ne otros pedidos)

        await db.commit()

    #  NOTIFY MACHINE 
    with RabbitMQPublisher(
        queue=PUBLISHING_QUEUES["machine_cancel_piece"],
        rabbitmq_config=RABBITMQ_CONFIG,
    ) as publisher:
        for piece_id in machine_cancel_piece_ids:
            publisher.publish({"piece_id": piece_id})

            logger.info(
                "[CMD:MACHINE:CANCEL_PIECE] - piece_id=%s",
                piece_id,
            )
    
    #  RESPUESTA A LA SAGA (CLAVE)
    with RabbitMQPublisher(
        queue="",
        rabbitmq_config=RABBITMQ_CONFIG,
        exchange="evt",
        exchange_type="topic",
        routing_key="warehouse.cancelled",
    ) as publisher:
        publisher.publish({
            "order_id": order_id,
            "cancelled_piece_ids": machine_cancel_piece_ids,
        })
    logger.info(
        "[EVENT:WAREHOUSE:CANCELLED] - order_id=%s",
        order_id,
    )


@register_queue_handler(
    queue=LISTENING_QUEUES["public_key"],
    exchange="public_key",
    exchange_type="fanout",
)
def public_key(message: MessageType) -> None:
    global PUBLIC_KEY

    assert (auth_base_url := ConsulClient(logger).get_service_url("auth")) is not None
    assert message.get("public_key") == "AVAILABLE"

    response = requests.get(f"{auth_base_url}/auth/key", timeout=5)
    assert response.status_code == 200

    data = response.json()
    assert "public_key" in data

    PUBLIC_KEY["key"] = str(data["public_key"])

    logger.info("[EVENT:WAREHOUSE:PUBLIC_KEY_UPDATED]")
