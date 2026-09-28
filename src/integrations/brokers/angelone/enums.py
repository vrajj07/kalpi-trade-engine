"""SmartAPI vocabulary."""
from enum import StrEnum


class Variety(StrEnum):
    NORMAL = "NORMAL"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ProductType(StrEnum):
    DELIVERY = "DELIVERY"


class Duration(StrEnum):
    DAY = "DAY"


class OrderStatus(StrEnum):
    """Order details report status in lower case."""

    COMPLETE = "complete"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    OPEN = "open"
    OPEN_PENDING = "open pending"
    VALIDATION_PENDING = "validation pending"
    TRIGGER_PENDING = "trigger pending"
    MODIFIED = "modified"


AUTH_ERROR_PREFIX = "AG80"  # AG8001 invalid token, AG8002 token expired, ...
TOKEN_EXCEPTION = "TokenException"
