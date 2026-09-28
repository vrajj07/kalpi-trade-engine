"""Delivery outcome policy: which failures are retried, when, and when a row is dead-lettered."""
import logging
import random
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from src.core.config import settings
from src.models import NotificationOutbox
from src.models.notification.enums import NotificationStatus
from src.modules.notification.exceptions import DeliveryError

logger = logging.getLogger(__name__)

# 408 timeout, 425 too early, 429 rate limited: the consumer asks for a later attempt.
# Every other 4xx is a refusal (bad URL, auth, validation). Redirects are not followed,
# so a 3xx is a refusal too: a webhook URL that moves must be updated, not chased.
RETRYABLE_STATUSES = {408, 425, 429}
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 300.0


def check_response(response: httpx.Response) -> None:
    if response.is_success:
        return
    status = response.status_code
    raise DeliveryError(f"HTTP {status} from {response.request.url.host}",
                        retryable=status in RETRYABLE_STATUSES or status >= 500,
                        retry_after=parse_retry_after(response.headers.get("Retry-After")))


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After is either delay-seconds or an HTTP-date (RFC 9110)."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def next_delay(attempts: int, retry_after: float | None = None) -> float:
    """Exponential backoff with full jitter, so rows that failed together (one consumer outage)
    do not retry in lockstep. A Retry-After is honoured as a floor, within the same cap."""
    delay = random.uniform(0, min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (attempts - 1)))
    if retry_after is not None:
        delay = max(delay, min(retry_after, MAX_DELAY_SECONDS))
    return delay


def record(row: NotificationOutbox, error: DeliveryError | None, now: datetime) -> None:
    """Applies one attempt's outcome. The attempt was already counted when the row was claimed."""
    if error is None:
        row.status, row.sent_at, row.last_error = NotificationStatus.SENT, now, None
        return
    row.last_error = error.message
    if error.retryable and row.attempts < settings.notification_max_attempts:
        row.next_attempt_at = now + timedelta(seconds=next_delay(row.attempts, error.retry_after))
        logger.warning("Notification %s for execution %s failed (attempt %s), retrying: %s",
                       row.event, row.execution_id, row.attempts, error.message)
        return
    row.status = NotificationStatus.FAILED
    logger.error("Notification %s for execution %s dead-lettered after %s attempt(s): %s",
                 row.event, row.execution_id, row.attempts, error.message)
