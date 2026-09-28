from decimal import Decimal

from pydantic import BaseModel


class PlaceOrderResponse(BaseModel):
    orderid: str
    uniqueorderid: str              # the key the order-details endpoint expects


class OrderDetailsResponse(BaseModel):
    orderstatus: str = ""  # kept as str: an unlisted status must not fail parsing (see mappers)
    filledshares: int = 0
    averageprice: Decimal | None = None
    text: str | None = None


class OrderBookEntry(OrderDetailsResponse):
    uniqueorderid: str
    ordertag: str | None = None


class HoldingResponse(BaseModel):
    tradingsymbol: str
    exchange: str
    quantity: int
    averageprice: Decimal
