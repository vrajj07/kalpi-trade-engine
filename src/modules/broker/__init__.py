"""Broker module: users' broker connections and the credentials built from them.

Layout:
    __init__.py    BrokerModule, the entry point services (and the execution module) call
    exceptions.py  domain errors, converted to HTTP errors by the service
"""
from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.dao.broker_connection import BrokerConnectionDAO
from src.integrations.brokers.base import BrokerCredentials
from src.integrations.brokers.enums import BrokerName
from src.integrations.brokers.registry import credentials_for
from src.models import BrokerConnection
from src.models.broker.enums import ConnectionStatus
from src.modules.broker.exceptions import (
    BrokerConnectionExpiredError,
    BrokerDisabledError,
    BrokerNotConnectedError,
    TokenStorageError,
)
from src.utils.encryption import EncryptionNotConfiguredError, InvalidToken, TokenCipher


class BrokerModule:
    """Stores users' broker sessions (encrypted) and turns them into adapter credentials."""

    def __init__(self, db: AsyncSession) -> None:
        self.dao = BrokerConnectionDAO(db)

    async def connect(self, user_id: str, broker: BrokerName, access_token: SecretStr,
                      client_id: str | None, expires_at: datetime | None) -> BrokerConnection:
        """Stores or replaces the user's session for this broker; a reconnect reactivates it."""
        # The single gate: without a stored connection, no real broker can be reached.
        if settings.mock_only and broker != BrokerName.MOCK:
            raise BrokerDisabledError(broker)
        encrypted = self._cipher().encrypt(access_token)
        connection = await self.dao.get(user_id, broker)
        if connection is None:
            return await self.dao.create(BrokerConnection(
                user_id=user_id, broker=broker, encrypted_access_token=encrypted, client_id=client_id,
                status=ConnectionStatus.ACTIVE, expires_at=expires_at))
        connection.encrypted_access_token, connection.client_id = encrypted, client_id
        connection.status, connection.expires_at = ConnectionStatus.ACTIVE, expires_at
        await self.dao.save()
        return await self.dao.refresh(connection)  # updated_at is set by the database

    async def get(self, user_id: str, broker: BrokerName) -> BrokerConnection:
        if (connection := await self.dao.get(user_id, broker)) is None:
            raise BrokerNotConnectedError(broker)
        await self._apply_expiry([connection])
        return connection

    async def list_connections(self, user_id: str) -> list[BrokerConnection]:
        connections = await self.dao.list_for_user(user_id)
        await self._apply_expiry(connections)
        return connections

    async def disconnect(self, user_id: str, broker: BrokerName) -> None:
        await self.dao.delete(await self.get(user_id, broker))

    async def credentials(self, user_id: str, broker: BrokerName) -> BrokerCredentials:
        """The user's live session for this broker, or an error telling them to (re)connect."""
        connection = await self.get(user_id, broker)
        if connection.status is ConnectionStatus.EXPIRED:
            raise BrokerConnectionExpiredError(broker)
        try:
            token = self._cipher().decrypt(connection.encrypted_access_token)
        except InvalidToken as exc:  # tampered, or encrypted with a key no longer configured
            raise TokenStorageError(f"Stored '{broker}' token cannot be decrypted; reconnect the broker") from exc
        return credentials_for(broker, token, connection.client_id)

    async def mark_expired(self, user_id: str, broker: BrokerName) -> None:
        """The broker rejected the session (401): stop using it until the user reconnects."""
        if (connection := await self.dao.get(user_id, broker)) is not None:
            connection.status = ConnectionStatus.EXPIRED
            await self.dao.save()

    async def _apply_expiry(self, connections: list[BrokerConnection]) -> None:
        """Lazy expiry: a token whose known expiry has passed is marked EXPIRED when next read,
        so callers see the real status without a background job."""
        now, changed = datetime.now(UTC), False
        for c in connections:
            expires_at = c.expires_at
            if expires_at is not None and expires_at.tzinfo is None:  # SQLite returns naive datetimes
                expires_at = expires_at.replace(tzinfo=UTC)
            if c.status is ConnectionStatus.ACTIVE and expires_at is not None and now >= expires_at:
                c.status, changed = ConnectionStatus.EXPIRED, True
        if changed:
            await self.dao.save()

    @staticmethod
    def _cipher() -> TokenCipher:
        try:
            return TokenCipher()
        except EncryptionNotConfiguredError as exc:
            raise TokenStorageError(str(exc)) from exc
