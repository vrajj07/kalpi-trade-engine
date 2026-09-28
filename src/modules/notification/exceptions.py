"""Domain errors of the notification module.

They never reach an HTTP response: delivery runs in the relay, off the request path, and an
error only decides whether the outbox row is retried or dead-lettered.
"""


class NotificationModuleError(Exception):
    """Base class for every notification module error."""

    def __init__(self, message: str = "Notification module error") -> None:
        super().__init__(message)
        self.message = message


class DeliveryError(NotificationModuleError):
    """One delivery attempt failed. retryable: a later attempt may succeed (timeout, 5xx, 429);
    otherwise the consumer refused it (4xx) and retrying would only repeat the refusal."""

    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
