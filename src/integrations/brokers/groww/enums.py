"""Groww Trade API vocabulary (order status list from the SDK's protobuf definitions)."""
from enum import StrEnum


class Segment(StrEnum):
    CASH = "CASH"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class Product(StrEnum):
    CNC = "CNC"  # delivery


class Validity(StrEnum):
    DAY = "DAY"


class OrderStatus(StrEnum):
    NEW = "NEW"
    ACKED = "ACKED"
    TRIGGER_PENDING = "TRIGGER_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    EXECUTED = "EXECUTED"
    DELIVERY_AWAITED = "DELIVERY_AWAITED"
    CANCELLED = "CANCELLED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
    COMPLETED = "COMPLETED"


class ErrorCode(StrEnum):
    THROTTLED = "GA003"      # unable to serve request currently
    UNAUTHORISED = "GA005"   # user not authorised
