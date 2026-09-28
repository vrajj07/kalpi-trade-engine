"""Append-only audit log: one row per state change of an execution or one of its orders.

Written in the same transaction as the state change it records (see transitions.py), so the
log and the current-state columns cannot disagree. Rows are never updated or deleted.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    __table_args__ = (Index("ix_execution_events_execution_id_id", "execution_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("execution_orders.id", ondelete="CASCADE"))  # None: execution
    from_state: Mapped[str] = mapped_column(String(20))  # OrderState or ExecutionState, by order_id
    to_state: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
