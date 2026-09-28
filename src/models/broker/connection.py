"""A user's connected broker account: the access token their broker login produced.

The token is stored encrypted (src/utils/encryption.py) and is never returned by the API.
Tokens are short-lived (most brokers expire them daily), so a connection is typically
refreshed once per trading day; a 401 from the broker marks it EXPIRED.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.integrations.brokers.enums import BrokerName
from src.models.columns import enum_column
from src.models.broker.enums import ConnectionStatus


class BrokerConnection(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (UniqueConstraint("user_id", "broker"),)  # one account per broker per user

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    broker: Mapped[BrokerName] = mapped_column(enum_column(BrokerName))
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(String(64))  # user's client code, where the broker needs it
    status: Mapped[ConnectionStatus] = mapped_column(enum_column(ConnectionStatus), default=ConnectionStatus.ACTIVE)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
