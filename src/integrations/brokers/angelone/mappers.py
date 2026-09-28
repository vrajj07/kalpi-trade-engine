"""Translations between domain enums/types and SmartAPI's vocabulary."""
from .. import enums as domain
from ..base import BrokerOrder, Holding
from . import enums as angel
from .schemas import HoldingResponse, OrderDetailsResponse

SIDE = {domain.Side.BUY: angel.TransactionType.BUY, domain.Side.SELL: angel.TransactionType.SELL}
ORDER_TYPE = {domain.OrderType.MARKET: angel.OrderType.MARKET, domain.OrderType.LIMIT: angel.OrderType.LIMIT}
# Every other status (open, *pending, modified, or one not yet listed) is still open.
STATUS = {
    angel.OrderStatus.COMPLETE: domain.OrderStatus.COMPLETE,
    angel.OrderStatus.REJECTED: domain.OrderStatus.REJECTED,
    angel.OrderStatus.CANCELLED: domain.OrderStatus.CANCELLED,
}


def to_status(status: str) -> domain.OrderStatus:
    return STATUS.get(status.lower(), domain.OrderStatus.OPEN)


def to_trading_symbol(symbol: str, exchange: domain.Exchange) -> str:
    return f"{symbol}-EQ" if exchange is domain.Exchange.NSE else symbol


def to_broker_order(order_id: str, order: OrderDetailsResponse) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order_id,
        status=to_status(order.orderstatus),
        filled_quantity=order.filledshares,
        average_price=order.averageprice or None,
        message=order.text or None,
    )


def to_holdings(rows: list[HoldingResponse]) -> list[Holding]:
    return [
        Holding(symbol=h.tradingsymbol.removesuffix("-EQ"), exchange=domain.Exchange(h.exchange),
                quantity=h.quantity, average_price=h.averageprice)
        for h in rows
        if h.exchange in domain.Exchange.__members__
    ]
