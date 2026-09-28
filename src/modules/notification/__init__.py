"""Notification module: delivers the report of every finished execution.

Layout:
    __init__.py   NotificationModule, the entry point
    helpers/      notifiers (webhook, console), retry policy, the in-process relay
    exceptions.py delivery errors, deciding retry vs dead-letter

Delivery is a transactional outbox: the state machine writes an outbox row in the same
transaction as the final state (execution transitions.py), and the relay delivers it after
the commit. So a crash can delay a report but not lose it, and delivery is at-least-once.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.dao.execution import ExecutionDAO
from src.dao.notification import NotificationDAO
from src.models import NotificationOutbox
from src.modules.notification.exceptions import DeliveryError
from src.modules.notification.helpers import relay, retry
from src.modules.notification.helpers.notifiers import Notifier, get_notifier
from src.schemas.execution import ExecutionReport

logger = logging.getLogger(__name__)


class NotificationModule:
    def __init__(self, db: AsyncSession, notifier: Notifier | None = None) -> None:
        self.dao = NotificationDAO(db)
        self.execution_dao = ExecutionDAO(db)
        self.notifier = notifier or get_notifier()

    @staticmethod
    def start_relay() -> None:
        relay.start(lambda session: NotificationModule(session).dispatch_due())

    @staticmethod
    async def stop_relay() -> None:
        await relay.shutdown()

    @staticmethod
    def wake() -> None:
        """A notification was just committed: deliver it now rather than at the next poll."""
        relay.wake()

    async def dispatch_due(self) -> int:
        """Claims one batch of due rows, delivers them concurrently, records each outcome.
        Returns how many rows were claimed."""
        now = datetime.now(UTC)
        rows = await self.dao.claim_due(now, settings.notification_batch_size,
                                        lease_until=now + timedelta(seconds=settings.notification_lease_seconds))
        if not rows:
            return 0
        # Reports are built from the DB first (one session, sequential); only the HTTP calls run
        # concurrently, so one slow consumer does not hold up the rest of the batch.
        reports = [ExecutionReport.model_validate(await self.execution_dao.get_by_id(row.execution_id))
                   for row in rows]
        errors = await asyncio.gather(*(self._deliver(row, report) for row, report in zip(rows, reports)))
        finished = datetime.now(UTC)
        for row, error in zip(rows, errors):
            retry.record(row, error, finished)
        await self.dao.save()
        return len(rows)

    async def _deliver(self, row: NotificationOutbox, report: ExecutionReport) -> DeliveryError | None:
        try:
            await self.notifier.notify(row.event, report)
        except DeliveryError as exc:
            return exc
        except Exception as exc:  # a notifier bug: retry it, but loudly
            logger.exception("Notifier crashed delivering %s for execution %s", row.event, row.execution_id)
            return DeliveryError(f"{type(exc).__name__}: {exc}", retryable=True)
        return None


__all__ = ["NotificationModule"]
