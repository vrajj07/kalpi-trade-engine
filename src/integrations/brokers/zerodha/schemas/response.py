from decimal import Decimal

from pydantic import BaseModel


class PlaceOrderResponse(BaseModel):
    order_id: str


class OrderHistoryEntry(BaseModel):
    status: str  # kept as str: an unlisted status must not fail parsing (see mappers)
    filled_quantity: int = 0
    average_price: Decimal | None = None
    status_message: str | None = None


class HoldingResponse(BaseModel):
    tradingsymbol: str
    exchange: str
    quantity: int
    average_price: Decimal
