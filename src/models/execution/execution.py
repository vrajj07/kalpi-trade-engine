"""Execution: the write-ahead record of one submitted instruction set.

Rows are written before any order is sent and updated on every state change, so a crashed
run can be resumed: the stored plan and tags are reused, never recomputed from a new request.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, WriteOnlyMapped, mapped_column, relationship

from src.core.database import Base
from src.integrations.brokers.enums import BrokerName
from src.models.columns import enum_column
from src.models.execution.enums import ExecutionState

if TYPE_CHECKING:
    from src.models.execution.event import ExecutionEvent
    from src.models.execution.order import ExecutionOrder
    from src.models.notification.outbox import NotificationOutbox


class Execution(Base):
    __tablename__ = "executions"
    # Idempotency keys are scoped per user (as Stripe scopes them per account): one user's key
    # must never collide with, or replay, another user's execution.
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    broker: Mapped[BrokerName] = mapped_column(enum_column(BrokerName))
    state: Mapped[ExecutionState] = mapped_column(enum_column(ExecutionState), default=ExecutionState.RUNNING)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list["ExecutionOrder"]] = relationship(
        back_populates="execution", order_by="ExecutionOrder.position", lazy="selectin",
        cascade="all, delete-orphan",
    )
    # Write-only: events are appended without loading the history; read through the DAO.
    events: WriteOnlyMapped["ExecutionEvent"] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    # Notifications owed about this execution, appended by the state machine (transactional outbox).
    notifications: WriteOnlyMapped["NotificationOutbox"] = relationship(cascade="all, delete-orphan",
                                                                       passive_deletes=True)
