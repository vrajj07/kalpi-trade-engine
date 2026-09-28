"""Builds the Groww place-order body from a generic OrderRequest."""
import uuid
from decimal import Decimal
from typing import Self

from ..common.builder import OrderPayloadBuilder
from ..enums import Exchange, OrderType, Side
from . import enums as groww
from . import mappers
from .schemas import PlaceOrderRequest


class GrowwOrderBuilder(OrderPayloadBuilder[PlaceOrderRequest]):
    schema = PlaceOrderRequest

    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        return self._set(trading_symbol=symbol, exchange=exchange)

    def side(self, side: Side) -> Self:
        return self._set(transaction_type=mappers.SIDE[side])

    def quantity(self, quantity: int) -> Self:
        return self._set(quantity=quantity)

    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        return self._set(order_type=mappers.ORDER_TYPE[order_type],
                         price=float(price) if order_type is OrderType.LIMIT else 0)

    def tag(self, tag: str | None) -> Self:
        # Groww requires a reference id; it doubles as our reconciliation key. Without a
        # caller-supplied tag a random one is used, which cannot be reconciled later.
        return self._set(order_reference_id=tag or uuid.uuid4().hex[:20])

    def delivery_defaults(self) -> Self:
        return self._set(validity=groww.Validity.DAY, segment=groww.Segment.CASH, product=groww.Product.CNC)
