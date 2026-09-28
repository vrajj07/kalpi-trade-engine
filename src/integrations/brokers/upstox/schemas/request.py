from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from ..enums import OrderType, Product, TransactionType, Validity


class PlaceOrderRequest(BaseModel):
    """JSON body of POST /v3/order/place."""

    model_config = ConfigDict(extra="forbid")

    instrument_token: str           # "NSE_EQ|INE009A01021"
    quantity: PositiveInt
    product: Literal[Product.DELIVERY]
    validity: Validity
    price: float = 0
    order_type: OrderType
    transaction_type: TransactionType
    disclosed_quantity: int = 0
    trigger_price: float = 0
    is_amo: bool = False
    # Auto-slicing would split one order into several broker orders; the port assumes
    # one request -> one broker order id.
    slice: Literal[False] = False
    tag: str | None = Field(default=None, max_length=40)
