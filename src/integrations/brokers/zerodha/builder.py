"""Builds the Kite place-order form from a generic OrderRequest."""
from decimal import Decimal
from typing import Self

from ..common.builder import OrderPayloadBuilder
from ..enums import Exchange, OrderType, Side
from . import enums as kite
from . import mappers
from .schemas import PlaceOrderRequest


class ZerodhaOrderBuilder(OrderPayloadBuilder[PlaceOrderRequest]):
    schema = PlaceOrderRequest

    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        return self._set(tradingsymbol=symbol, exchange=exchange)

    def side(self, side: Side) -> Self:
        return self._set(transaction_type=mappers.SIDE[side])

    def quantity(self, quantity: int) -> Self:
        return self._set(quantity=quantity)

    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        return self._set(order_type=mappers.ORDER_TYPE[order_type],
                         price=price if order_type is OrderType.LIMIT else None)

    def tag(self, tag: str | None) -> Self:
        return self._set(tag=tag)

    def delivery_defaults(self) -> Self:
        return self._set(product=kite.Product.CNC, validity=kite.Validity.DAY)
