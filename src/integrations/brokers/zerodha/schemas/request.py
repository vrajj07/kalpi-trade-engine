from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from ...enums import Exchange
from ..enums import OrderType, Product, TransactionType, Validity


class PlaceOrderRequest(BaseModel):
    """Form body of POST /orders/regular."""

    model_config = ConfigDict(extra="forbid")

    tradingsymbol: str
    exchange: Exchange
    transaction_type: TransactionType
    order_type: OrderType
    quantity: PositiveInt
    product: Product
    validity: Validity
    price: Decimal | None = None
    tag: str | None = Field(default=None, max_length=20)
