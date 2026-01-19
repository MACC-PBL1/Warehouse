from chassis.sql import BaseModel
from sqlalchemy import (
    Integer,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)
from typing import Optional

class Warehouse(BaseModel):
    __tablename__ = "warehouse"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False)


class Piece(BaseModel):
    __tablename__ = "w_piece"

    STATUS_QUEUED = "QUEUED" 
    STATUS_PRODUCING = "PRODUCING" 
    STATUS_PRODUCED = "PRODUCED" 
    STATUS_CANCELLED = "CANCELLED" 

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(1), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
