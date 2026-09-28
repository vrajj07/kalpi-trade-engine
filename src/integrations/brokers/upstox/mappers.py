"""Translations between domain enums/types and Upstox's vocabulary."""
from .. import enums as domain
from ..base import BrokerOrder, Holding
from . import enums as upstox
from .schemas import HoldingResponse, OrderDetailsResponse

SIDE = {domain.Side.BUY: upstox.TransactionType.BUY, domain.Side.SELL: upstox.TransactionType.SELL}
ORDER_TYPE = {domain.OrderType.MARKET: upstox.OrderType.MARKET, domain.OrderType.LIMIT: upstox.OrderType.LIMIT}
# Every other status (open, *pending, "put order req received"...) is still open.
STATUS = {
    upstox.OrderStatus.COMPLETE: domain.OrderStatus.COMPLETE,
    upstox.OrderStatus.REJECTED: domain.OrderStatus.REJECTED,
    upstox.OrderStatus.CANCELLED: domain.OrderStatus.CANCELLED,
}


def to_status(status: str) -> domain.OrderStatus:
    return STATUS.get(status.lower(), domain.OrderStatus.OPEN)


def to_broker_order(order_id: str, order: OrderDetailsResponse) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order_id,
        status=to_status(order.status),
        filled_quantity=order.filled_quantity,
        average_price=order.average_price or None,
        message=order.status_message or None,
    )


def to_holdings(rows: list[HoldingResponse]) -> list[Holding]:
    return [
        Holding(symbol=h.trading_symbol, exchange=domain.Exchange(h.exchange), quantity=h.quantity,
                average_price=h.average_price)
        for h in rows
        if h.exchange in domain.Exchange.__members__
    ]
