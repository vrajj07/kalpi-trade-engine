"""Upstox implementation of the BrokerAdapter port: instruments -> builder -> client -> mappers."""
import httpx

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, OrderStatus
from ..common.instruments import InstrumentMaster, load_upstox_index
from . import mappers
from .builder import UpstoxOrderBuilder
from .client import UpstoxClient

_default_instruments = InstrumentMaster(BrokerName.UPSTOX, load_upstox_index)


class UpstoxBroker(BrokerAdapter):
    name = BrokerName.UPSTOX

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None,
                 instruments: InstrumentMaster | None = None) -> None:
        super().__init__(credentials)
        self.client = UpstoxClient(credentials, http)
        self.instruments = instruments or _default_instruments

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        key = await self.instruments.resolve(order.exchange, order.symbol)
        placed = await self.client.place_order(UpstoxOrderBuilder.build_from(order, instrument_id=key))
        return BrokerOrder(broker_order_id=placed.order_ids[0], status=OrderStatus.OPEN)

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        return mappers.to_broker_order(broker_order_id, await self.client.order_details(broker_order_id))

    async def get_holdings(self) -> list[Holding]:
        return mappers.to_holdings(await self.client.holdings())

    async def aclose(self) -> None:
        await self.client.aclose()
