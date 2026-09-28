"""In-memory broker for demos and tests. No network, deterministic behaviour.

Behaviour is driven by `credentials.extra`, filled from MOCK_* settings by the registry:
    {
      "holdings": {"INFY": 10, "TCS": 5},        # starting demat holdings
      "fail": {"HDFCBANK": "reject",             # per-symbol failure injection:
               "WIPRO": "unavailable"}           # reject | unavailable | rate_limit | unknown
    }
"""
import itertools
from decimal import Decimal

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, Exchange, OrderStatus, Side
from ..errors import (
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerUnavailableError,
    OrderRejectedError,
    OrderStateUnknownError,
)

_FAILURES = {
    "reject": lambda b: OrderRejectedError("Insufficient funds (simulated)", broker=b),
    "unavailable": lambda b: BrokerUnavailableError("Broker unavailable (simulated)", broker=b),
    "rate_limit": lambda b: BrokerRateLimitError("Too many requests (simulated)", broker=b, retry_after=1),
    "unknown": lambda b: OrderStateUnknownError("Timed out after send (simulated)", broker=b),
}


class MockBroker(BrokerAdapter):
    name = BrokerName.MOCK

    def __init__(self, credentials: BrokerCredentials) -> None:
        super().__init__(credentials)
        self._holdings: dict[str, int] = dict(credentials.extra.get("holdings", {}))
        self._fail: dict[str, str] = dict(credentials.extra.get("fail", {}))
        self._orders: dict[str, BrokerOrder] = {}
        self._ids = itertools.count(1)

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        if kind := self._fail.get(order.symbol):
            raise _FAILURES[kind](self.name)

        held = self._holdings.get(order.symbol, 0)
        if order.side is Side.SELL and order.quantity > held:
            raise OrderRejectedError(
                f"Cannot sell {order.quantity} {order.symbol}: only {held} held", broker=self.name
            )

        self._holdings[order.symbol] = held + (order.quantity if order.side is Side.BUY else -order.quantity)
        result = BrokerOrder(
            broker_order_id=f"MOCK-{next(self._ids)}",
            status=OrderStatus.COMPLETE,
            filled_quantity=order.quantity,
            average_price=order.price or _price(order.symbol),
        )
        self._orders[result.broker_order_id] = result
        return result

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        try:
            return self._orders[broker_order_id]
        except KeyError:
            raise BrokerRequestError(f"Unknown order {broker_order_id}", broker=self.name) from None

    async def get_holdings(self) -> list[Holding]:
        return [
            Holding(symbol=s, exchange=Exchange.NSE, quantity=q, average_price=_price(s))
            for s, q in self._holdings.items()
            if q > 0
        ]


def _price(symbol: str) -> Decimal:
    """Stable fake price per symbol, so runs are reproducible."""
    return Decimal(100 + sum(map(ord, symbol)) % 900)
