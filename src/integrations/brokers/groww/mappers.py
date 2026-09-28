"""Translations between domain enums/types and Groww's vocabulary."""
from .. import enums as domain
from ..base import BrokerOrder, Holding
from . import enums as groww
from .schemas import HoldingResponse, OrderDetailsResponse

SIDE = {domain.Side.BUY: groww.TransactionType.BUY, domain.Side.SELL: groww.TransactionType.SELL}
ORDER_TYPE = {domain.OrderType.MARKET: groww.OrderType.MARKET, domain.OrderType.LIMIT: groww.OrderType.LIMIT}
# NEW, ACKED, TRIGGER_PENDING, APPROVED, *_REQUESTED -> still open.
# EXECUTED / DELIVERY_AWAITED mean fully traded; COMPLETED is after settlement.
STATUS = {
    groww.OrderStatus.EXECUTED: domain.OrderStatus.COMPLETE,
    groww.OrderStatus.DELIVERY_AWAITED: domain.OrderStatus.COMPLETE,
    groww.OrderStatus.COMPLETED: domain.OrderStatus.COMPLETE,
    groww.OrderStatus.REJECTED: domain.OrderStatus.REJECTED,
    groww.OrderStatus.FAILED: domain.OrderStatus.REJECTED,
    groww.OrderStatus.CANCELLED: domain.OrderStatus.CANCELLED,
}


def to_status(order_status: str) -> domain.OrderStatus:
    return STATUS.get(order_status, domain.OrderStatus.OPEN)


def to_broker_order(order_id: str, order: OrderDetailsResponse) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order_id,
        status=to_status(order.order_status),
        filled_quantity=order.filled_quantity,
        average_price=order.average_fill_price or None,
        message=order.remark,
    )


def to_holdings(rows: list[HoldingResponse]) -> list[Holding]:
    # Demat holdings are exchange-agnostic; reported as NSE by convention.
    return [Holding(symbol=h.trading_symbol, exchange=domain.Exchange.NSE, quantity=h.quantity,
                    average_price=h.average_price) for h in rows]
