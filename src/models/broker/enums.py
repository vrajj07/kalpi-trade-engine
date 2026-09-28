from enum import StrEnum


class ConnectionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"  # the broker rejected the token (or its expiry passed): reconnect
