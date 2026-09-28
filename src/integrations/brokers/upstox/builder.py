"""Builds the Upstox v3 place-order body from a generic OrderRequest."""
from decimal import Decimal
from typing import Self

from ..common.builder import OrderPayloadBuilder
from ..enums import Exchange, OrderType, Side
from . import enums as upstox
from . import mappers
from .schemas import PlaceOrderRequest


class UpstoxOrderBuilder(OrderPayloadBuilder[PlaceOrderRequest]):
    schema = PlaceOrderRequest

    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        if instrument_id is None:
            raise ValueError("Upstox orders need an instrument_key")
        return self._set(instrument_token=instrument_id)

    def side(self, side: Side) -> Self:
        return self._set(transaction_type=mappers.SIDE[side])

    def quantity(self, quantity: int) -> Self:
        return self._set(quantity=quantity)

    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        return self._set(order_type=mappers.ORDER_TYPE[order_type],
                         price=float(price) if order_type is OrderType.LIMIT else 0)

    def tag(self, tag: str | None) -> Self:
        return self._set(tag=tag)

    def delivery_defaults(self) -> Self:
        return self._set(product=upstox.Product.DELIVERY, validity=upstox.Validity.DAY,
                         disclosed_quantity=0, trigger_price=0, is_amo=False, slice=False)
