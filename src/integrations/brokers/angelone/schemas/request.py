from pydantic import BaseModel, ConfigDict, Field

from ...enums import Exchange
from ..enums import Duration, OrderType, ProductType, TransactionType, Variety


class PlaceOrderRequest(BaseModel):
    """JSON body of POST /order/v1/placeOrder. SmartAPI sends numbers as strings."""

    model_config = ConfigDict(extra="forbid")

    variety: Variety
    tradingsymbol: str              # "INFY-EQ" on NSE, "INFY" on BSE
    symboltoken: str                # numeric token from the scrip master
    transactiontype: TransactionType
    exchange: Exchange
    ordertype: OrderType
    producttype: ProductType
    duration: Duration
    price: str
    quantity: str
    ordertag: str | None = Field(default=None, max_length=20)
