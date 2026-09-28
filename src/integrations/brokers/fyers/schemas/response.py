from decimal import Decimal

from pydantic import BaseModel

from .helpers import FyersStatus


class PlaceOrderResponse(FyersStatus):
    id: str


class OrderResponse(BaseModel):
    id: str
    status: int  # kept as int: an unlisted code must not fail parsing (see mappers)
    filledQty: int = 0
    tradedPrice: Decimal | None = None
    message: str | None = None


class OrderBookResponse(FyersStatus):
    orderBook: list[OrderResponse] = []


class HoldingResponse(BaseModel):
    symbol: str                     # "NSE:INFY-EQ"
    quantity: int
    costPrice: Decimal


class HoldingsResponse(FyersStatus):
    holdings: list[HoldingResponse] = []
