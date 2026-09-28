"""Builds the SmartAPI place-order body from a generic OrderRequest."""
from decimal import Decimal
from typing import Self

from ..common.builder import OrderPayloadBuilder
from ..enums import Exchange, OrderType, Side
from . import enums as angel
from . import mappers
from .schemas import PlaceOrderRequest


class AngelOneOrderBuilder(OrderPayloadBuilder[PlaceOrderRequest]):
    schema = PlaceOrderRequest

    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        if instrument_id is None:
            raise ValueError("AngelOne orders need a symboltoken")
        return self._set(tradingsymbol=mappers.to_trading_symbol(symbol, exchange),
                         symboltoken=instrument_id, exchange=exchange)

    def side(self, side: Side) -> Self:
        return self._set(transactiontype=mappers.SIDE[side])

    def quantity(self, quantity: int) -> Self:
        return self._set(quantity=str(quantity))

    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        return self._set(ordertype=mappers.ORDER_TYPE[order_type],
                         price=str(price) if order_type is OrderType.LIMIT else "0")

    def tag(self, tag: str | None) -> Self:
        return self._set(ordertag=tag)

    def delivery_defaults(self) -> Self:
        return self._set(variety=angel.Variety.NORMAL, producttype=angel.ProductType.DELIVERY,
                         duration=angel.Duration.DAY)
