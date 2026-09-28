"""Builds the Fyers place-order body from a generic OrderRequest."""
from decimal import Decimal
from typing import Self

from ..common.builder import OrderPayloadBuilder
from ..enums import Exchange, OrderType, Side
from . import enums as fyers
from . import mappers
from .schemas import PlaceOrderRequest


class FyersOrderBuilder(OrderPayloadBuilder[PlaceOrderRequest]):
    schema = PlaceOrderRequest

    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        return self._set(symbol=mappers.to_fyers_symbol(symbol, exchange))

    def side(self, side: Side) -> Self:
        return self._set(side=mappers.SIDE[side])

    def quantity(self, quantity: int) -> Self:
        return self._set(qty=quantity)

    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        # Fyers expresses "no price" as 0, not as an absent field.
        return self._set(type=mappers.ORDER_TYPE[order_type],
                         limitPrice=float(price) if order_type is OrderType.LIMIT else 0)

    def tag(self, tag: str | None) -> Self:
        return self._set(orderTag=tag)

    def delivery_defaults(self) -> Self:
        return self._set(productType=fyers.ProductType.CNC, validity=fyers.Validity.DAY,
                         stopPrice=0, disclosedQty=0, offlineOrder=False)
