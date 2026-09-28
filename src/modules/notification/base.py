"""Notifier interface + implementations (webhook, console).

A notification is best effort: it must never change an execution's outcome, so failures
are logged, not raised. Consumers should dedupe on `id` — a resumed or retried delivery can
send the same report twice (at-least-once delivery).
"""
import logging
from abc import ABC, abstractmethod

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.schemas.execution import ExecutionReport

logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    async def notify(self, report: ExecutionReport) -> None: ...


class ConsoleNotifier(Notifier):
    async def notify(self, report: ExecutionReport) -> None:
        counts = ", ".join(f"{state}={n}" for state, n in report.summary.items())
        lines = [f"Execution {report.id} on {report.broker}: {report.state} ({counts})"]
        lines += [f"  #{o.position} {o.side} {o.quantity} {o.symbol}: {o.state}"
                  + (f" - {o.message}" if o.message else "") for o in report.orders]
        lines += [f"  ! {item}" for item in report.needs_attention]
        logger.info("\n".join(lines))


class WebhookNotifier(Notifier):
    def __init__(self, url: str, http: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._http = http

    async def notify(self, report: ExecutionReport) -> None:
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(httpx.HTTPError),
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, max=4),
                reraise=True,
            ):
                with attempt:
                    await self._post(report)
        except httpx.HTTPError as exc:
            logger.error("Webhook delivery failed for execution %s: %s", report.id, exc)

    async def _post(self, report: ExecutionReport) -> None:
        headers = {"Content-Type": "application/json", "X-Event-Type": "execution.finished"}
        body = report.model_dump_json()
        if self._http is not None:  # injected (tests): caller owns its lifecycle
            response = await self._http.post(self._url, content=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=5) as http:
                response = await http.post(self._url, content=body, headers=headers)
        response.raise_for_status()


def get_notifier() -> Notifier:
    if settings.notification_webhook_url:
        return WebhookNotifier(settings.notification_webhook_url)
    return ConsoleNotifier()
