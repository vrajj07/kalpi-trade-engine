"""Domain errors of the broker module. The service layer converts them to HTTP errors."""
from src.integrations.brokers.enums import BrokerName
from src.utils.exceptions import AppError, ConflictError, ForbiddenError, InternalServerError, UnauthorizedError


class BrokerModuleError(Exception):
    """Base class for every broker module error."""

    def __init__(self, message: str = "Broker module error") -> None:
        super().__init__(message)
        self.message = message

    @classmethod
    def to_http_exception(cls, exc: "BrokerModuleError") -> AppError:
        exception_mapping: dict[type[BrokerModuleError], type[AppError]] = {
            BrokerNotConnectedError: ConflictError,
            BrokerConnectionExpiredError: UnauthorizedError,
            BrokerDisabledError: ForbiddenError,
        }
        error_cls = exception_mapping.get(type(exc), InternalServerError)
        return error_cls(exc.message, code=type(exc).__name__)


class BrokerNotConnectedError(BrokerModuleError):
    def __init__(self, broker: BrokerName) -> None:
        super().__init__(f"No '{broker}' account is connected: PUT /brokers/{broker}/connection first")


class BrokerConnectionExpiredError(BrokerModuleError):
    def __init__(self, broker: BrokerName) -> None:
        super().__init__(f"The '{broker}' session has expired: log in to the broker again and reconnect")


class BrokerDisabledError(BrokerModuleError):
    def __init__(self, broker: BrokerName) -> None:
        super().__init__(f"'{broker}' is disabled on this demo deployment: only the mock broker can be connected")


class TokenStorageError(BrokerModuleError):
    """The stored token cannot be encrypted or decrypted (key missing, rotated away, or tampered)."""
