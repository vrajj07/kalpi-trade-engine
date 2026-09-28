"""Groww implementation of the BrokerAdapter port: builder -> client -> mappers."""
import httpx

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName
from . import mappers
from .builder import GrowwOrderBuilder
from .client import GrowwClient


class GrowwBroker(BrokerAdapter):
    name = BrokerName.GROWW

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None) -> None:
        super().__init__(credentials)
        self.client = GrowwClient(credentials, http)

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        placed = await self.client.place_order(GrowwOrderBuilder.build_from(order))
        return BrokerOrder(broker_order_id=placed.groww_order_id, status=mappers.to_status(placed.order_status),
                           message=placed.remark)

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        return mappers.to_broker_order(broker_order_id, await self.client.order_details(broker_order_id))

    async def find_order(self, tag: str) -> BrokerOrder | None:
        found = await self.client.order_by_reference(tag)
        if found is None:
            return None
        return BrokerOrder(broker_order_id=found.groww_order_id, status=mappers.to_status(found.order_status),
                           filled_quantity=found.filled_quantity, message=found.remark)

    async def get_holdings(self) -> list[Holding]:
        return mappers.to_holdings((await self.client.holdings()).holdings)

    async def aclose(self) -> None:
        await self.client.aclose()
