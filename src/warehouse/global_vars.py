from chassis.messaging import RabbitMQConfig
from pathlib import Path
from typing import (
    Dict,
    LiteralString,
    Optional,
)
import os

RABBITMQ_CONFIG: RabbitMQConfig = {
    "host": os.getenv("RABBITMQ_HOST", "localhost"),
    "port": int(os.getenv("RABBITMQ_PORT", "5672")),
    "username": os.getenv("RABBITMQ_USER", "guest"),
    "password": os.getenv("RABBITMQ_PASSWD", "guest"),
    "use_tls": bool(int(os.getenv("RABBITMQ_USE_TLS", "0"))),
    "ca_cert": Path(ca_cert_path) if (ca_cert_path := os.getenv("RABBITMQ_CA_CERT_PATH")) else None,
    "client_cert": Path(client_cert_path) if (client_cert_path := os.getenv("RABBITMQ_CLIENT_CERT_PATH")) else None,
    "client_key": Path(client_key_path) if (client_key_path := os.getenv("RABBITMQ_CLIENT_KEY_PATH")) else None,
    "prefetch_count": int(os.getenv("RABBITMQ_PREFETCH_COUNT", 10)),
}

PUBLISHING_QUEUES: Dict[LiteralString, LiteralString] = {
    "piece_created": "warehouse.piece_created",
    "order_completed": "warehouse.order_completed", 
     "machine_cancel_piece": "warehouse.machine_cancel_piece",
     "warehouse_cancelled": "warehouse.cancelled",
    "machine_piece_A": "machine.piece.A",
    "machine_piece_B": "machine.piece.B",
}

LISTENING_QUEUES: Dict[LiteralString, LiteralString] = {
    "piece_executed": "machine.piece_executed",
    "public_key": "client.public_key.warehouse",
    "warehouse_cancel": "warehouse.cancel",
    "order_created": "order.created"
    
}


PUBLIC_KEY: Dict[str, Optional[str]] = {"key": None}
