"""Broker failure taxonomy.

Every adapter maps its broker's errors onto these classes. The executor decides what to
do from the class alone — chiefly the `retryable` flag — never from broker error codes.
These deliberately do not extend AppError: the integration layer knows nothing about HTTP.
"""


class BrokerError(Exception):
    retryable: bool = False

    def __init__(self, message: str, *, broker: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.broker = broker
        self.code = code  # broker's own error code, kept for logs / reports


class BrokerAuthError(BrokerError):
    """Access token missing, invalid or expired. The user must log in again."""


class BrokerNotConfiguredError(BrokerError):
    """No credentials configured for this broker (see src/core/config/<broker>.py)."""


class BrokerRateLimitError(BrokerError):
    retryable = True

    def __init__(self, message: str, *, broker: str, code: str | None = None,
                 retry_after: float | None = None) -> None:
        super().__init__(message, broker=broker, code=code)
        self.retry_after = retry_after


class BrokerUnavailableError(BrokerError):
    """The request definitely did not take effect (connection refused, 503...)."""

    retryable = True


class BrokerRequestError(BrokerError):
    """The broker understood the request and refused it (bad input, not found...)."""


class OrderRejectedError(BrokerRequestError):
    """The broker refused the order itself (insufficient funds, invalid quantity...)."""


class InstrumentNotFoundError(BrokerRequestError):
    """The symbol could not be mapped to this broker's instrument identifier."""


class OrderStateUnknownError(BrokerError):
    """The order request may or may not have reached the broker (e.g. read timeout).

    Not retryable: blindly re-sending could place a duplicate order. The caller must
    reconcile first, for example by looking the order up by its tag.
    """


class BrokerResponseError(BrokerError):
    """A response did not match the broker's documented schema (API drift or a bug)."""
