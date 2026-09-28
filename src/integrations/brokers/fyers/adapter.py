"""Fyers implementation of the BrokerAdapter port: builder -> client -> mappers."""
import httpx

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, OrderStatus
from . import mappers
from .builder import FyersOrderBuilder
from .client import FyersClient


class FyersBroker(BrokerAdapter):
    name = BrokerName.FYERS

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None) -> None:
        super().__init__(credentials)
        self.client = FyersClient(credentials, http)

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        placed = await self.client.place_order(FyersOrderBuilder.build_from(order))
        return BrokerOrder(broker_order_id=placed.id, status=OrderStatus.OPEN, message=placed.message)

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        return mappers.to_broker_order(await self.client.get_order(broker_order_id))

    async def get_holdings(self) -> list[Holding]:
        return mappers.to_holdings((await self.client.holdings()).holdings)

    async def aclose(self) -> None:
        await self.client.aclose()
