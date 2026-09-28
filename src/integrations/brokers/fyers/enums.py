"""Fyers API v3 vocabulary. Fyers encodes most of it as integers."""
from enum import IntEnum, StrEnum


class Side(IntEnum):
    BUY = 1
    SELL = -1


class OrderType(IntEnum):
    LIMIT = 1
    MARKET = 2
    STOP = 3         # SL-M
    STOP_LIMIT = 4   # SL-L


class ProductType(StrEnum):
    CNC = "CNC"  # delivery


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class OrderStatus(IntEnum):
    CANCELLED = 1
    TRADED = 2
    TRANSIT = 4
    REJECTED = 5
    PENDING = 6
    EXPIRED = 7


class ErrorCode(IntEnum):
    """Token/authentication failures (Fyers v3 docs; not encoded in the SDK)."""

    TOKEN_EXPIRED = -8
    INVALID_TOKEN = -15
    AUTH_FAILED = -16
    TOKEN_INVALID_OR_EXPIRED = -17


AUTH_ERRORS = frozenset(ErrorCode)
