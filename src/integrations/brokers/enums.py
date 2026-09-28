"""Domain enums: the broker-agnostic vocabulary the execution core speaks.

Each broker package has its own enums.py for that broker's vocabulary; its mappers.py
translates between the two.
"""
from enum import StrEnum


class BrokerName(StrEnum):
    ZERODHA = "zerodha"
    FYERS = "fyers"
    ANGELONE = "angelone"
    UPSTOX = "upstox"
    GROWW = "groww"
    MOCK = "mock"


class Exchange(StrEnum):
    """Reused as-is in broker request schemas whose wire values match (Zerodha, AngelOne, Groww).

    Keep this a closed set every broker supports. Adding a member here makes those brokers
    accept it on the wire; a broker that doesn't support it must reject it explicitly
    (as Fyers does for BSE in fyers/mappers.py).
    """

    NSE = "NSE"
    BSE = "BSE"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    OPEN = "OPEN"            # accepted by the broker, not yet terminal
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self is not OrderStatus.OPEN
