"""Domain errors of the execution module. The service layer converts them to HTTP errors."""
import uuid

from src.integrations.brokers.enums import BrokerName
from src.utils.exceptions import (
    AppError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)


class ExecutionModuleError(Exception):
    """Base class for every execution module error."""

    def __init__(self, message: str = "Execution module error") -> None:
        super().__init__(message)
        self.message = message

    @classmethod
    def to_http_exception(cls, exc: "ExecutionModuleError") -> AppError:
        exception_mapping: dict[type[ExecutionModuleError], type[AppError]] = {
            ExecutionNotFoundError: NotFoundError,
            IdempotencyKeyReusedError: ConflictError,
            InvalidInstructionsError: UnprocessableEntityError,
            PortfolioNotEmptyError: ConflictError,
            HoldingsUnavailableError: ServiceUnavailableError,
        }
        error_cls = exception_mapping.get(type(exc), InternalServerError)
        return error_cls(exc.message, code=type(exc).__name__, details=getattr(exc, "errors", None))


class ExecutionNotFoundError(ExecutionModuleError):
    def __init__(self, execution_id: uuid.UUID) -> None:
        super().__init__(f"Execution {execution_id} not found")


class IdempotencyKeyReusedError(ExecutionModuleError):
    """Same Idempotency-Key, different body: a new intent must use a new key."""

    def __init__(self) -> None:
        super().__init__("Idempotency-Key was already used with a different request body")


class InvalidInstructionsError(ExecutionModuleError):
    """Every failed rule is reported at once, so the client can fix the request in one go."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class PortfolioNotEmptyError(ExecutionModuleError):
    """A target portfolio is only for a first-time investor; a rebalance needs explicit instructions."""

    def __init__(self, held: int) -> None:
        super().__init__(f"A target portfolio is for a first-time portfolio, but {held} stock(s) are already "
                         "held. Send explicit SELL / BUY / REBALANCE instructions instead.")


class HoldingsUnavailableError(ExecutionModuleError):
    """Fail closed: without current holdings the request cannot be checked, so nothing is placed."""

    def __init__(self, broker: BrokerName, details: str) -> None:
        super().__init__(f"Could not read holdings from '{broker}', nothing was placed; retry later: {details}")


class IllegalTransitionError(ExecutionModuleError):
    """A state change the state machine does not allow: a bug, never a broker outcome."""
