from decimal import Decimal

from pydantic import BaseModel


class PlaceOrderResponse(BaseModel):
    groww_order_id: str
    order_status: str = ""  # kept as str: an unlisted status must not fail parsing (see mappers)
    remark: str | None = None


class OrderDetailsResponse(BaseModel):
    order_status: str = ""
    filled_quantity: int = 0
    average_fill_price: Decimal | None = None
    remark: str | None = None


class HoldingResponse(BaseModel):
    trading_symbol: str
    quantity: int
    average_price: Decimal


class HoldingsResponse(BaseModel):
    holdings: list[HoldingResponse] = []
