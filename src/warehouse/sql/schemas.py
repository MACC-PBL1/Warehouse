from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List


class Message(BaseModel):
    detail: str
    system_metrics: dict

class PieceBase(BaseModel):
    id: int
    order_id: Optional[int]
    status: str
    created_at: datetime
    manufacturing_started_at: Optional[datetime] = None
    manufactured_at: Optional[datetime] = None
   # piece_type: str


class Piece(PieceBase):
    class Config:
        from_attributes = True


class PieceCreate(BaseModel):
    order_id: Optional[int]
    amount: int


class PieceCancel(BaseModel):
    order_id: Optional[int]


class PiecesByOrder(BaseModel):
    order_id: Optional[int]
    pieces: List[Piece]
