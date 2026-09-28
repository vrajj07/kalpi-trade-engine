"""AngelOne implementation of the BrokerAdapter port: instruments -> builder -> client -> mappers."""
import httpx

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, OrderStatus
from ..common.instruments import InstrumentMaster, load_angelone_index
from . import mappers
from .builder import AngelOneOrderBuilder
from .client import AngelOneClient

_default_instruments = InstrumentMaster(BrokerName.ANGELONE, load_angelone_index)


class AngelOneBroker(BrokerAdapter):
    name = BrokerName.ANGELONE

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None,
                 instruments: InstrumentMaster | None = None) -> None:
        super().__init__(credentials)
        self.client = AngelOneClient(credentials, http)
        self.instruments = instruments or _default_instruments

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        token = await self.instruments.resolve(order.exchange, order.symbol)
        placed = await self.client.place_order(AngelOneOrderBuilder.build_from(order, instrument_id=token))
        return BrokerOrder(broker_order_id=placed.uniqueorderid, status=OrderStatus.OPEN)

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        return mappers.to_broker_order(broker_order_id, await self.client.order_details(broker_order_id))

    async def find_order(self, tag: str) -> BrokerOrder | None:
        match = next((o for o in await self.client.order_book() if o.ordertag == tag), None)
        return mappers.to_broker_order(match.uniqueorderid, match) if match else None

    async def get_holdings(self) -> list[Holding]:
        return mappers.to_holdings(await self.client.holdings())

    async def aclose(self) -> None:
        await self.client.aclose()
