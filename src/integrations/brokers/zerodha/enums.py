"""Kite Connect vocabulary."""
from enum import StrEnum


class Variety(StrEnum):
    REGULAR = "regular"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class Product(StrEnum):
    CNC = "CNC"  # cash and carry (delivery)


class Validity(StrEnum):
    DAY = "DAY"


class OrderStatus(StrEnum):
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    OPEN = "OPEN"
    OPEN_PENDING = "OPEN PENDING"
    VALIDATION_PENDING = "VALIDATION PENDING"
    TRIGGER_PENDING = "TRIGGER PENDING"
    CANCEL_PENDING = "CANCEL PENDING"
    MODIFIED = "MODIFIED"


class ErrorType(StrEnum):
    TOKEN = "TokenException"
    PERMISSION = "PermissionException"
    ORDER = "OrderException"
    INPUT = "InputException"
    NETWORK = "NetworkException"
    DATA = "DataException"
    GENERAL = "GeneralException"
