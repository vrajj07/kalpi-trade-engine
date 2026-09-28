from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from ...enums import Exchange
from ..enums import OrderType, Product, Segment, TransactionType, Validity


class PlaceOrderRequest(BaseModel):
    """JSON body of POST /order/create."""

    model_config = ConfigDict(extra="forbid")

    trading_symbol: str             # plain "INFY", not "INFY-EQ"
    quantity: PositiveInt
    price: float = 0
    validity: Validity
    exchange: Exchange
    segment: Segment
    product: Product
    order_type: OrderType
    transaction_type: TransactionType
    order_reference_id: str = Field(pattern=r"^[A-Za-z0-9]{8,20}$")
