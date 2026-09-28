"""Where a report is delivered: the webhook if configured, otherwise the log.

A notifier makes one attempt and raises DeliveryError on failure; retries belong to the
outbox (helpers/retry.py), so they survive a restart instead of living in one process's memory.
A queue publisher (SQS) would be one more Notifier: the relay would hand it the row and a
separate consumer would POST (see README, "Path to production").
"""
import logging
from abc import ABC, abstractmethod

import httpx

from src.core.config import settings
from src.models.notification.enums import NotificationEvent
from src.modules.notification.exceptions import DeliveryError
from src.modules.notification.helpers.retry import check_response
from src.schemas.execution import ExecutionReport

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    async def notify(self, event: NotificationEvent, report: ExecutionReport) -> None: ...


class ConsoleNotifier(Notifier):
    async def notify(self, event: NotificationEvent, report: ExecutionReport) -> None:
        counts = ", ".join(f"{state}={n}" for state, n in report.summary.items())
        lines = [f"[{event}] Execution {report.id} on {report.broker}: {report.state} ({counts})"]
        lines += [f"  #{o.position} {o.side} {o.quantity} {o.symbol}: {o.state}"
                  + (f" - {o.message}" if o.message else "") for o in report.orders]
        lines += [f"  ! {item}" for item in report.needs_attention]
        logger.info("\n".join(lines))


class WebhookNotifier(Notifier):
    def __init__(self, url: str, http: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._http = http

    async def notify(self, event: NotificationEvent, report: ExecutionReport) -> None:
        # Consumers dedupe on X-Delivery-Id: delivery is at-least-once (a lease can run out
        # mid-delivery, a response can be lost after the consumer processed it).
        headers = {"Content-Type": "application/json", "X-Event-Type": event,
                   "X-Delivery-Id": f"{report.id}:{event}"}
        body = report.model_dump_json()
        try:
            if self._http is not None:  # injected (tests): caller owns its lifecycle
                response = await self._http.post(self._url, content=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=settings.notification_timeout_seconds) as http:
                    response = await http.post(self._url, content=body, headers=headers)
        except httpx.TransportError as exc:  # connect error, timeout: the consumer may be back later
            raise DeliveryError(f"{type(exc).__name__}: {exc}", retryable=True) from exc
        check_response(response)


def get_notifier() -> Notifier:
    if settings.notification_webhook_url:
        return WebhookNotifier(settings.notification_webhook_url)
    return ConsoleNotifier()
