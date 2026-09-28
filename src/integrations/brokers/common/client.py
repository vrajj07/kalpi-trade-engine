"""Shared transport for broker REST clients: HTTP, rate limiting, retries, error mapping.

Each broker's client.py subclasses BaseBrokerClient and adds its endpoints, auth headers
and error-envelope parsing. Nothing here knows about orders or domain types.
"""
import hashlib
from typing import Any, ClassVar, TypeVar

import httpx
from aiolimiter import AsyncLimiter
from pydantic import TypeAdapter, ValidationError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from ..base import BrokerCredentials
from ..errors import (
    BrokerAuthError,
    BrokerError,
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerResponseError,
    BrokerUnavailableError,
    OrderStateUnknownError,
)

T = TypeVar("T")

# Brokers rate-limit per API key / user, so the limiter must be shared by every client
# for the same account — not created per request. In-process only: several replicas
# would need a distributed limiter (e.g. a Redis token bucket).
_limiters: dict[tuple[str, str], AsyncLimiter] = {}

_NON_IDEMPOTENT = {"POST", "PUT", "PATCH"}
_MAX_RETRY_AFTER = 5.0


def _backoff(state: RetryCallState) -> float:
    exc = state.outcome.exception() if state.outcome else None
    if isinstance(exc, BrokerRateLimitError) and exc.retry_after is not None:
        return min(exc.retry_after, _MAX_RETRY_AFTER)
    return wait_exponential_jitter(initial=0.5, max=4)(state)


def _is_retryable(exc: BaseException) -> bool:
    # Safe for POST too: only errors proving the broker did not execute the request are
    # retryable (429, 503, connection never established). OrderStateUnknownError is not.
    return isinstance(exc, BrokerError) and exc.retryable


class BaseBrokerClient:
    broker: ClassVar[str]
    base_url: ClassVar[str]
    # (max requests, period in seconds) — the broker's published limit for order placement
    rate_limit: ClassVar[tuple[int, float]] = (10, 1.0)
    timeout: ClassVar[float] = 10.0
    max_attempts: ClassVar[int] = 3
    retry_wait: ClassVar[Any] = staticmethod(_backoff)

    def __init__(self, credentials: BrokerCredentials, http: httpx.AsyncClient | None = None) -> None:
        self.credentials = credentials
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    @property
    def api_key(self) -> str:
        return self.credentials.api_key.get_secret_value() if self.credentials.api_key else ""

    # --- hooks for broker clients -------------------------------------------------

    def headers(self) -> dict[str, str]:
        """Auth + broker-specific headers for every request."""
        raise NotImplementedError

    def check_body(self, response: httpx.Response, body: Any) -> None:
        """Raise for brokers that report errors inside a 2xx body. Default: nothing."""

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        """Map a broker error envelope onto a precise BrokerError, or None to use the status code."""
        return None

    # --- transport ----------------------------------------------------------------

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self.max_attempts),
            wait=self.retry_wait,
            reraise=True,
        ):
            with attempt:
                return await self._send(method, url, **kwargs)

    async def _send(self, method: str, url: str, **kwargs: Any) -> Any:
        async with self._limiter:
            try:
                response = await self._http.request(method, url, headers=self.headers(), **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                # Never reached the broker: always safe to retry.
                raise BrokerUnavailableError(str(exc) or type(exc).__name__, broker=self.broker) from exc
            except httpx.TransportError as exc:
                # Sent, but no reliable answer. For an order that is the dangerous case.
                message = str(exc) or type(exc).__name__
                if method.upper() in _NON_IDEMPOTENT:
                    raise OrderStateUnknownError(message, broker=self.broker) from exc
                raise BrokerUnavailableError(message, broker=self.broker) from exc

        body = _json(response)
        if response.is_success:
            self.check_body(response, body)
            return body
        # Auth and throttling are decided by status alone; a broker's body mapping must not
        # turn a 429 into a non-retryable rejection.
        if response.status_code not in (401, 403, 429) and (error := self.error_from_body(response, body)):
            raise error
        raise self._error_from_status(method, response, body)

    def parse(self, schema: type[T], data: Any, *, after_write: bool = False) -> T:
        """Validate a response against the broker's response schema.

        after_write: the request was an order placement that the broker accepted. If we
        cannot read its response we do not know the order id, so the state is unknown.
        """
        try:
            return TypeAdapter(schema).validate_python(data)
        except ValidationError as exc:
            error = OrderStateUnknownError if after_write else BrokerResponseError
            raise error(f"Unexpected response shape: {exc}", broker=self.broker) from exc

    @staticmethod
    def try_parse(schema: type[T], data: Any) -> T | None:
        """Lenient parse for error envelopes: a malformed error body must not mask the error."""
        try:
            return TypeAdapter(schema).validate_python(data)
        except ValidationError:
            return None

    def _error_from_status(self, method: str, response: httpx.Response, body: Any) -> BrokerError:
        status = response.status_code
        message = _message(body) or response.reason_phrase or f"HTTP {status}"
        if status in (401, 403):
            return BrokerAuthError(message, broker=self.broker)
        if status == 429:
            return BrokerRateLimitError(message, broker=self.broker, retry_after=_retry_after(response))
        if status == 503:
            return BrokerUnavailableError(message, broker=self.broker)
        if status >= 500:
            # A gateway error on an order POST does not prove the order was not placed.
            if method.upper() in _NON_IDEMPOTENT:
                return OrderStateUnknownError(message, broker=self.broker)
            return BrokerUnavailableError(message, broker=self.broker)
        return BrokerRequestError(message, broker=self.broker)

    @property
    def _limiter(self) -> AsyncLimiter:
        creds = self.credentials
        # Hash the account identity so no credential is kept in plain text as a dict key.
        identity = self.api_key or creds.client_id or creds.access_token.get_secret_value()
        account = hashlib.sha256(identity.encode()).hexdigest()
        key = (self.broker, account)
        if key not in _limiters:
            _limiters[key] = AsyncLimiter(*self.rate_limit)
        return _limiters[key]

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _message(body: Any) -> str | None:
    if isinstance(body, dict):
        for key in ("message", "error", "errors"):
            if isinstance(body.get(key), str):
                return body[key]
    return None


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
