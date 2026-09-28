"""Zerodha implementation of the BrokerAdapter port: builder -> client -> mappers."""
import httpx

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, OrderStatus
from . import mappers
from .builder import ZerodhaOrderBuilder
from .client import ZerodhaClient


class ZerodhaBroker(BrokerAdapter):
    name = BrokerName.ZERODHA

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None) -> None:
        super().__init__(credentials)
        self.client = ZerodhaClient(credentials, http)

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        placed = await self.client.place_order(ZerodhaOrderBuilder.build_from(order))
        return BrokerOrder(broker_order_id=placed.order_id, status=OrderStatus.OPEN)

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        history = await self.client.order_history(broker_order_id)
        return mappers.to_broker_order(broker_order_id, history[-1])

    async def find_order(self, tag: str) -> BrokerOrder | None:
        match = next((o for o in await self.client.order_book() if o.tag == tag), None)
        return mappers.to_broker_order(match.order_id, match) if match else None

    async def get_holdings(self) -> list[Holding]:
        return mappers.to_holdings(await self.client.holdings())

    async def aclose(self) -> None:
        await self.client.aclose()
