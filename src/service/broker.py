"""Broker use cases: connect / inspect / disconnect a user's account, and read holdings."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.brokers.base import Holding
from src.integrations.brokers.enums import BrokerName
from src.integrations.brokers.errors import BrokerAuthError
from src.integrations.brokers.registry import get_adapter, supported_brokers
from src.models import BrokerConnection
from src.modules.broker import BrokerModule
from src.modules.broker.exceptions import BrokerConnectionExpiredError, BrokerModuleError
from src.schemas.broker import BrokerConnect, BrokerInfo

logger = logging.getLogger(__name__)


class BrokerService:
    def __init__(self, db: AsyncSession) -> None:
        self.broker_module = BrokerModule(db)

    async def list_brokers(self, user_id: str) -> list[BrokerInfo]:
        connected = {c.broker: c for c in await self.broker_module.list_connections(user_id)}
        return [BrokerInfo(name=b, connection=connected[b].status if b in connected else None)
                for b in supported_brokers()]

    async def connect(self, user_id: str, broker: BrokerName, data: BrokerConnect) -> BrokerConnection:
        try:
            return await self.broker_module.connect(user_id, broker, data.access_token, data.client_id,
                                                    data.expires_at)
        except BrokerModuleError as exc:
            logger.error("Broker connect failed for %s: %s", broker, exc.message)
            raise BrokerModuleError.to_http_exception(exc) from exc

    async def get_connection(self, user_id: str, broker: BrokerName) -> BrokerConnection:
        try:
            return await self.broker_module.get(user_id, broker)
        except BrokerModuleError as exc:
            raise BrokerModuleError.to_http_exception(exc) from exc

    async def disconnect(self, user_id: str, broker: BrokerName) -> None:
        try:
            await self.broker_module.disconnect(user_id, broker)
        except BrokerModuleError as exc:
            raise BrokerModuleError.to_http_exception(exc) from exc

    async def get_holdings(self, user_id: str, broker: BrokerName) -> list[Holding]:
        try:
            credentials = await self.broker_module.credentials(user_id, broker)
            try:
                async with get_adapter(broker, credentials) as adapter:
                    return await adapter.get_holdings()
            except BrokerAuthError as exc:
                await self.broker_module.mark_expired(user_id, broker)
                raise BrokerConnectionExpiredError(broker) from exc
        except BrokerModuleError as exc:
            raise BrokerModuleError.to_http_exception(exc) from exc
