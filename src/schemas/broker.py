from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.integrations.brokers.enums import BrokerName
from src.models.broker.enums import ConnectionStatus


class BrokerConnect(BaseModel):
    """The session a user's broker login produced. Stored encrypted; never returned."""
    model_config = ConfigDict(extra="forbid")

    access_token: SecretStr = Field(min_length=1)
    client_id: str | None = Field(default=None, max_length=64,
                                  description="The user's client code, where the broker needs it (AngelOne).")
    expires_at: datetime | None = Field(default=None, description="When the broker expires the token, if known.")


class BrokerConnectionStatus(BaseModel):
    """A connection as the API shows it: status only, never the token."""
    model_config = ConfigDict(from_attributes=True)

    broker: BrokerName
    status: ConnectionStatus
    client_id: str | None
    expires_at: datetime | None
    connected_at: datetime
    updated_at: datetime


class BrokerInfo(BaseModel):
    name: BrokerName
    connection: ConnectionStatus | None  # None: not connected
