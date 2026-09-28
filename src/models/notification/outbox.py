"""Transactional outbox: one row per notification owed, written in the same transaction as the
state change it reports (see execution transitions.py). A crash after the commit cannot lose
the notification: the relay finds the row and delivers it.

The row is a claim check: it holds the execution id, not the report. The report is built at
delivery time from the execution, which is final and therefore no longer changes.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models.columns import enum_column
from src.models.notification.enums import NotificationEvent, NotificationStatus


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("execution_id", "event"),  # an event is owed once, however often it is re-derived
        Index("ix_notification_outbox_due", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(64))
    event: Mapped[NotificationEvent] = mapped_column(enum_column(NotificationEvent))
    status: Mapped[NotificationStatus] = mapped_column(enum_column(NotificationStatus),
                                                       default=NotificationStatus.PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    # When the row is next due. A claim pushes it out by the lease, so a relay that dies
    # mid-delivery leaves the row to be picked up again once the lease runs out.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
