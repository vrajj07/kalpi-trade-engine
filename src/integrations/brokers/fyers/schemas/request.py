from pydantic import BaseModel, ConfigDict, PositiveInt

from ..enums import OrderType, ProductType, Side, Validity


class PlaceOrderRequest(BaseModel):
    """JSON body of POST /orders/sync."""

    model_config = ConfigDict(extra="forbid")

    symbol: str                     # "NSE:INFY-EQ"
    qty: PositiveInt
    type: OrderType
    side: Side
    productType: ProductType
    limitPrice: float = 0
    stopPrice: float = 0
    validity: Validity
    disclosedQty: int = 0
    offlineOrder: bool = False
    orderTag: str | None = None
