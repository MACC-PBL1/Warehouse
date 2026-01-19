from pydantic import BaseModel
from typing import TypedDict

class Message(BaseModel):
    detail: str
    system_metrics: dict

class OrderPieceSchema(TypedDict):
    type: str
    quantity: int