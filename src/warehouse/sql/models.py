from chassis.sql import BaseModel
from datetime import datetime
from sqlalchemy import (
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column
)


class PieceModel(BaseModel):
    __tablename__ = "piece"
    STATUS_CREATED = "CREATED" 
    STATUS_QUEUED = "QUEUED" 
    STATUS_MANUFACTURING = "MANUFACTURING" 
    STATUS_MANUFACTURED = "MANUFACTURED" 
    STATUS_CANCELLED = "CANCELLED" 

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    piece_type: Mapped[str] = mapped_column(
        String(1), 
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STATUS_CREATED,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    manufacturing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    manufactured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
