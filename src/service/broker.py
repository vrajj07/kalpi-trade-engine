"""Broker use cases: which brokers are available, and a broker's holdings."""
from src.integrations.brokers.base import Holding
from src.integrations.brokers.enums import BrokerName
from src.integrations.brokers.registry import get_adapter, is_configured, supported_brokers
from src.schemas.broker import BrokerInfo


class BrokerService:
    def list_brokers(self) -> list[BrokerInfo]:
        return [BrokerInfo(name=b, configured=is_configured(b)) for b in supported_brokers()]

    async def get_holdings(self, broker: BrokerName) -> list[Holding]:
        async with get_adapter(broker) as adapter:
            return await adapter.get_holdings()
