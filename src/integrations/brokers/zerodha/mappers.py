"""Translations between domain enums/types and Kite's vocabulary."""
from .. import enums as domain
from ..base import BrokerOrder, Holding
from . import enums as kite
from .schemas import HoldingResponse, OrderHistoryEntry

SIDE = {domain.Side.BUY: kite.TransactionType.BUY, domain.Side.SELL: kite.TransactionType.SELL}
ORDER_TYPE = {domain.OrderType.MARKET: kite.OrderType.MARKET, domain.OrderType.LIMIT: kite.OrderType.LIMIT}
# Every other Kite status (OPEN, *_PENDING, MODIFIED, or one not yet listed) is still open.
STATUS = {
    kite.OrderStatus.COMPLETE: domain.OrderStatus.COMPLETE,
    kite.OrderStatus.REJECTED: domain.OrderStatus.REJECTED,
    kite.OrderStatus.CANCELLED: domain.OrderStatus.CANCELLED,
}


def to_status(status: str) -> domain.OrderStatus:
    return STATUS.get(status, domain.OrderStatus.OPEN)


def to_broker_order(order_id: str, latest: OrderHistoryEntry) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order_id,
        status=to_status(latest.status),
        filled_quantity=latest.filled_quantity,
        average_price=latest.average_price or None,
        message=latest.status_message,
    )


def to_holdings(rows: list[HoldingResponse]) -> list[Holding]:
    return [
        Holding(symbol=h.tradingsymbol, exchange=domain.Exchange(h.exchange), quantity=h.quantity,
                average_price=h.average_price)
        for h in rows
        if h.exchange in domain.Exchange.__members__
    ]
