from chassis.messaging import RabbitMQConfig
from pathlib import Path
from typing import (
    Dict,
    LiteralString,
    Optional,
)
import os
import socket

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
LISTENING_QUEUES: Dict[LiteralString, str] = {
    "piece_request": "order.piece.request",
    "piece_producing": "machine.piece.producing",
    "piece_produced": "machine.piece.produced",
    "saga_reserve": "warehouse.reserve",
    "saga_release": "warehouse.release",
    "saga_cancel": "warehouse.cancel",
    "public_key": f"client.public_key.warehouse.{socket.gethostname()}",
}
PUBLIC_KEY: Dict[str, Optional[str]] = {"key": None}
