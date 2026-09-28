"""Translations between domain enums/types and Fyers' vocabulary."""
from .. import enums as domain
from ..base import BrokerOrder, Holding
from ..errors import InstrumentNotFoundError
from . import enums as fyers
from .schemas import HoldingResponse, OrderResponse

SIDE = {domain.Side.BUY: fyers.Side.BUY, domain.Side.SELL: fyers.Side.SELL}
ORDER_TYPE = {domain.OrderType.LIMIT: fyers.OrderType.LIMIT, domain.OrderType.MARKET: fyers.OrderType.MARKET}
# TRANSIT, PENDING, or a code not yet listed: still open.
STATUS = {
    fyers.OrderStatus.CANCELLED: domain.OrderStatus.CANCELLED,
    fyers.OrderStatus.TRADED: domain.OrderStatus.COMPLETE,
    fyers.OrderStatus.REJECTED: domain.OrderStatus.REJECTED,
    fyers.OrderStatus.EXPIRED: domain.OrderStatus.CANCELLED,
}


def to_status(code: int) -> domain.OrderStatus:
    return STATUS.get(code, domain.OrderStatus.OPEN)


def to_fyers_symbol(symbol: str, exchange: domain.Exchange) -> str:
    if exchange is domain.Exchange.NSE:
        return f"NSE:{symbol}-EQ"
    # BSE symbols carry the scrip group as suffix (-A, -B, -T...), which needs the Fyers
    # symbol master to resolve. Not supported yet.
    raise InstrumentNotFoundError("BSE orders are not supported by the Fyers adapter", broker=domain.BrokerName.FYERS)


def has_tag(order: OrderResponse, tag: str) -> bool:
    # UNVERIFIED: the order book has been seen to return the tag with a numeric prefix.
    return order.orderTag is not None and (order.orderTag == tag or order.orderTag.endswith(f":{tag}"))


def to_broker_order(order: OrderResponse) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order.id,
        status=to_status(order.status),
        filled_quantity=order.filledQty,
        average_price=order.tradedPrice or None,
        message=order.message,
    )


def to_holdings(rows: list[HoldingResponse]) -> list[Holding]:
    holdings = []
    for h in rows:
        exchange, _, rest = h.symbol.partition(":")
        if exchange in domain.Exchange.__members__:
            holdings.append(Holding(symbol=rest.removesuffix("-EQ"), exchange=domain.Exchange(exchange),
                                    quantity=h.quantity, average_price=h.costPrice))
    return holdings
