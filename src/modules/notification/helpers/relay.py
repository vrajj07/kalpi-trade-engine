"""In-process outbox relay: one background loop that delivers due notifications.

It polls on an interval, and wakes early when an execution finishes (wake()), so a report
goes out within moments without a tight poll. The poll is the guarantee, wake() only cuts
latency: a missed wake (another replica, a restart) is picked up by the next poll.

Known limitation: it runs in the API process. At scale the same loop moves to a worker, or
publishes to a queue instead of POSTing (see README, "Path to production").
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None
_wake: asyncio.Event | None = None
_stopping = False


def start(dispatch: Callable[[AsyncSession], Awaitable[int]]) -> None:
    """dispatch(session) delivers one batch of due rows and returns how many it claimed."""
    global _task, _wake, _stopping
    _wake, _stopping = asyncio.Event(), False
    _task = asyncio.create_task(_loop(dispatch, _wake), name="notification-relay")


def wake() -> None:
    if _wake is not None:
        _wake.set()


async def shutdown() -> None:
    """Graceful: the batch in flight finishes and records its outcomes, then the loop exits.
    Past the grace period it is cancelled, which is still safe: the claimed rows' lease runs
    out and they are delivered again (at-least-once)."""
    global _task, _wake, _stopping
    if _task is not None:
        _stopping = True
        wake()
        try:
            await asyncio.wait_for(_task, timeout=settings.notification_timeout_seconds + 1)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            logger.exception("Notification relay failed during shutdown")
    _task = _wake = None


async def _loop(dispatch: Callable[[AsyncSession], Awaitable[int]], wake_event: asyncio.Event) -> None:
    while not _stopping:
        wake_event.clear()
        try:
            async with AsyncSessionLocal() as session:
                while await dispatch(session) >= settings.notification_batch_size and not _stopping:
                    pass  # a full batch: more may be due
        except Exception:  # a bad batch must not kill the relay; its rows are retried after the lease
            logger.exception("Notification relay batch failed")
        try:
            await asyncio.wait_for(wake_event.wait(), timeout=settings.notification_poll_interval_seconds)
        except TimeoutError:
            pass
