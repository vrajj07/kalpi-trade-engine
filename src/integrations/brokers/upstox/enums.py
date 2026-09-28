"""Upstox vocabulary."""
from enum import StrEnum


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class Product(StrEnum):
    DELIVERY = "D"
    INTRADAY = "I"


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class OrderStatus(StrEnum):
    """Subset of Upstox statuses; all others are transient."""

    COMPLETE = "complete"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    OPEN = "open"
    OPEN_PENDING = "open pending"
    VALIDATION_PENDING = "validation pending"
    TRIGGER_PENDING = "trigger pending"
    PUT_ORDER_REQ_RECEIVED = "put order req received"


class ErrorCode(StrEnum):
    INVALID_TOKEN = "UDAPI100050"
    INVALID_CREDENTIALS = "UDAPI100016"


AUTH_ERRORS = frozenset({ErrorCode.INVALID_TOKEN, ErrorCode.INVALID_CREDENTIALS})
