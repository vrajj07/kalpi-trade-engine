from decimal import Decimal

from pydantic import BaseModel, Field


class PlaceOrderResponse(BaseModel):
    order_ids: list[str] = Field(min_length=1)


class OrderDetailsResponse(BaseModel):
    status: str = ""  # kept as str: an unlisted status must not fail parsing (see mappers)
    filled_quantity: int = 0
    average_price: Decimal | None = None
    status_message: str | None = None


class OrderBookEntry(OrderDetailsResponse):
    order_id: str
    tag: str | None = None


class HoldingResponse(BaseModel):
    trading_symbol: str
    exchange: str
    quantity: int
    average_price: Decimal
