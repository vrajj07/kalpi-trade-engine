"""BrokerAdapter port: the contract every broker adapter implements.

The execution core only sees this interface and these types. Each adapter translates
broker vocabulary (symbol formats, status codes, error envelopes) into them, so nothing
broker-specific leaks outside src/integrations/brokers/.

Scope: equity cash segment, delivery (CNC) product only — this is a portfolio engine,
not an intraday one, so product type is not part of the contract.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from types import TracebackType
from typing import Any, ClassVar, Self

from pydantic import BaseModel, Field, PositiveInt, SecretStr, model_validator

from .enums import BrokerName, Exchange, OrderStatus, OrderType, Side


class BrokerCredentials(BaseModel):
    """Session credentials for one broker account.

    Built from src/core/config/<broker>.py by the registry; adapters never
    read configuration themselves. Obtaining tokens (OAuth/TOTP login) is out of scope.
    """

    access_token: SecretStr
    api_key: SecretStr | None = None
    client_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class OrderRequest(BaseModel):
    symbol: str = Field(description="Exchange trading symbol, e.g. INFY")
    exchange: Exchange = Exchange.NSE
    side: Side
    quantity: PositiveInt
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = Field(default=None, gt=0)
    tag: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9]{8,20}$",
        description="Client reference sent to the broker, used to reconcile an order whose "
        "placement outcome is unknown. 8-20 alphanumerics: the intersection of broker limits "
        "(Groww needs 8-20, Kite allows at most 20 alphanumeric).",
    )

    @model_validator(mode="after")
    def _price_matches_type(self) -> Self:
        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("price is required for LIMIT orders")
        if self.order_type is OrderType.MARKET and self.price is not None:
            raise ValueError("price must be omitted for MARKET orders")
        return self


class BrokerOrder(BaseModel):
    broker_order_id: str
    status: OrderStatus
    filled_quantity: int = 0
    average_price: Decimal | None = None
    message: str | None = None


class Holding(BaseModel):
    symbol: str
    exchange: Exchange
    quantity: int
    average_price: Decimal


class BrokerAdapter(ABC):
    """Port implemented once per broker (see <broker>/adapter.py).

    Failures surface as `BrokerError` subclasses (see errors.py). Each broker's client
    already retries what is provably safe to retry (throttled, unavailable, never sent);
    anything that still escapes — notably OrderStateUnknownError — is the caller's to handle.
    """

    name: ClassVar[BrokerName]

    def __init__(self, credentials: BrokerCredentials) -> None:
        self.credentials = credentials

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> BrokerOrder:
        """Submit an order. Returns the broker's order id and its initial status."""

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        """Fetch the current state of a previously placed order."""

    @abstractmethod
    async def get_holdings(self) -> list[Holding]:
        """Delivery holdings in the user's demat account."""

    async def aclose(self) -> None:
        """Release network resources. Override if the adapter owns any."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
