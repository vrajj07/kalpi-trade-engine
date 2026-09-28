"""In-memory broker for demos and tests. No network, deterministic behaviour.

Behaviour is driven by `credentials.extra`, filled from MOCK_* settings by the registry:
    {
      "holdings": {"INFY": 10, "TCS": 5},   # starting demat holdings
      "cash": 50000,                        # available funds; omit for unlimited
      "fail": {"HDFCBANK": "reject"}        # per-symbol failure injection, see FailMode
    }
"""
import itertools
from decimal import Decimal
from typing import Literal

from ..base import BrokerAdapter, BrokerCredentials, BrokerOrder, Holding, OrderRequest
from ..enums import BrokerName, Exchange, OrderStatus, Side
from ..errors import (
    BrokerAuthError,
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerUnavailableError,
    OrderRejectedError,
    OrderStateUnknownError,
)

FailMode = Literal[
    "reject",       # broker refuses the order
    "unavailable",  # 503: never reached the broker
    "rate_limit",   # 429 on every attempt
    "unknown",      # order IS placed, but the response is lost (timeout after send)
    "lost",         # timeout after send, and the order never reached the book
    "open",         # accepted, never fills
    "partial",      # half filled, remainder cancelled by the exchange
    "auth",         # session expired
]


class MockBroker(BrokerAdapter):
    name = BrokerName.MOCK

    def __init__(self, credentials: BrokerCredentials) -> None:
        super().__init__(credentials)
        self._holdings: dict[str, int] = dict(credentials.extra.get("holdings", {}))
        cash = credentials.extra.get("cash")
        self._cash: Decimal | None = Decimal(str(cash)) if cash is not None else None
        self._fail: dict[str, str] = dict(credentials.extra.get("fail", {}))
        self._orders: dict[str, BrokerOrder] = {}
        self._tags: dict[str, str] = {}
        self._ids = itertools.count(1)

    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        mode = self._fail.get(order.symbol)
        if mode == "reject":
            raise OrderRejectedError("Order rejected by RMS (simulated)", broker=self.name)
        if mode == "unavailable":
            raise BrokerUnavailableError("Broker unavailable (simulated)", broker=self.name)
        if mode == "rate_limit":
            raise BrokerRateLimitError("Too many requests (simulated)", broker=self.name, retry_after=1)
        if mode == "auth":
            raise BrokerAuthError("Session expired (simulated)", broker=self.name)
        if mode == "lost":
            raise OrderStateUnknownError("Timed out after send (simulated)", broker=self.name)

        price = order.price or _price(order.symbol)
        held = self._holdings.get(order.symbol, 0)
        if order.side is Side.SELL and order.quantity > held:
            raise OrderRejectedError(f"Cannot sell {order.quantity} {order.symbol}: only {held} held",
                                     broker=self.name)
        if order.side is Side.BUY and self._cash is not None and order.quantity * price > self._cash:
            raise OrderRejectedError(f"Insufficient funds: need {order.quantity * price}, have {self._cash}",
                                     broker=self.name)

        filled = {"open": 0, "partial": order.quantity // 2}.get(mode or "", order.quantity)
        status = {"open": OrderStatus.OPEN, "partial": OrderStatus.CANCELLED}.get(mode or "", OrderStatus.COMPLETE)
        signed = filled if order.side is Side.BUY else -filled
        self._holdings[order.symbol] = held + signed
        if self._cash is not None:
            self._cash -= signed * price

        result = BrokerOrder(broker_order_id=f"MOCK-{next(self._ids)}", status=status, filled_quantity=filled,
                             average_price=price if filled else None)
        self._orders[result.broker_order_id] = result
        if order.tag:
            self._tags[order.tag] = result.broker_order_id
        if mode == "unknown":
            raise OrderStateUnknownError("Timed out after send (simulated)", broker=self.name)
        return result

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        try:
            return self._orders[broker_order_id]
        except KeyError:
            raise BrokerRequestError(f"Unknown order {broker_order_id}", broker=self.name) from None

    async def find_order(self, tag: str) -> BrokerOrder | None:
        order_id = self._tags.get(tag)
        return self._orders[order_id] if order_id else None

    async def get_holdings(self) -> list[Holding]:
        return [
            Holding(symbol=s, exchange=Exchange.NSE, quantity=q, average_price=_price(s))
            for s, q in self._holdings.items()
            if q > 0
        ]


def _price(symbol: str) -> Decimal:
    """Stable fake price per symbol, so runs are reproducible."""
    return Decimal(100 + sum(map(ord, symbol)) % 900)
