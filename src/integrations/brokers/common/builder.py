"""Builder for broker order payloads.

Our API speaks one generic OrderRequest; every broker wants a differently shaped body
(numeric codes, suffixed symbols, form vs JSON...). Each broker supplies a concrete
builder whose steps translate one aspect of the order; `build()` validates the result
against that broker's request schema, so a malformed payload fails before it is sent.

`build_from` is the director: it fixes the order of steps for every broker, so adding a
broker means implementing steps, never re-deciding the sequence.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, ClassVar, Generic, Self, TypeVar

from pydantic import BaseModel

from ..base import OrderRequest
from ..enums import Exchange, OrderType, Side

Payload = TypeVar("Payload", bound=BaseModel)


class OrderPayloadBuilder(ABC, Generic[Payload]):
    schema: ClassVar[type[BaseModel]]

    def __init__(self) -> None:
        self._fields: dict[str, Any] = {}

    def _set(self, **fields: Any) -> Self:
        self._fields.update({k: v for k, v in fields.items() if v is not None})
        return self

    # --- steps: one aspect of the order each ---------------------------------------

    @abstractmethod
    def instrument(self, symbol: str, exchange: Exchange, instrument_id: str | None = None) -> Self:
        """Broker's instrument identification (symbol format, token, instrument key)."""

    @abstractmethod
    def side(self, side: Side) -> Self: ...

    @abstractmethod
    def quantity(self, quantity: int) -> Self: ...

    @abstractmethod
    def pricing(self, order_type: OrderType, price: Decimal | None) -> Self:
        """Order type plus price fields (brokers differ on how MARKET is expressed)."""

    @abstractmethod
    def tag(self, tag: str | None) -> Self: ...

    def delivery_defaults(self) -> Self:
        """Product = delivery, validity = DAY, and any fields the broker requires."""
        return self

    def build(self) -> Payload:
        return self.schema.model_validate(self._fields)  # type: ignore[return-value]

    # --- director --------------------------------------------------------------------

    @classmethod
    def build_from(cls, order: OrderRequest, instrument_id: str | None = None) -> Payload:
        return (
            cls()
            .instrument(order.symbol, order.exchange, instrument_id)
            .side(order.side)
            .quantity(order.quantity)
            .pricing(order.order_type, order.price)
            .tag(order.tag)
            .delivery_defaults()
            .build()
        )
