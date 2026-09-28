import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from src.core.config import settings
from src.core.database import AsyncSessionLocal, close_db_connections, init_db
from src.dao.notification import NotificationDAO
from src.models import Execution
from src.models.execution.enums import ExecutionState
from src.models.notification.enums import NotificationEvent, NotificationStatus
from src.modules.execution.transitions import transition_execution
from src.modules.notification import NotificationModule
from src.modules.notification.exceptions import DeliveryError
from src.modules.notification.helpers import retry
from src.modules.notification.helpers.notifiers import Notifier, WebhookNotifier
from src.schemas.execution import ExecutionReport

HOOK = "https://hooks.test/kalpi"


def report() -> ExecutionReport:
    return ExecutionReport.model_validate({
        "id": uuid.uuid4(), "broker": "mock", "state": "COMPLETED", "reason": None, "created_at": None,
        "expires_at": "2026-09-28T10:00:00Z", "finished_at": None, "orders": []})


# --- retry policy ---

@pytest.mark.parametrize("status, retryable", [
    (500, True), (503, True), (429, True), (408, True),  # the consumer may accept a later attempt
    (400, False), (401, False), (404, False), (410, False), (301, False),  # a refusal: retrying repeats it
])
@respx.mock
async def test_webhook_classifies_failures(status, retryable):
    respx.post(HOOK).mock(return_value=httpx.Response(status))
    async with httpx.AsyncClient() as http:
        with pytest.raises(DeliveryError) as exc:
            await WebhookNotifier(HOOK, http).notify(NotificationEvent.EXECUTION_FINISHED, report())
    assert exc.value.retryable is retryable


@respx.mock
async def test_webhook_network_error_is_retryable_and_sends_dedupe_headers():
    route = respx.post(HOOK).mock(side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(204)])
    r = report()
    async with httpx.AsyncClient() as http:
        notifier = WebhookNotifier(HOOK, http)
        with pytest.raises(DeliveryError) as exc:
            await notifier.notify(NotificationEvent.EXECUTION_FINISHED, r)
        assert exc.value.retryable
        await notifier.notify(NotificationEvent.EXECUTION_FINISHED, r)
    assert route.calls.last.request.headers["X-Delivery-Id"] == f"{r.id}:execution.finished"


@respx.mock
async def test_retry_after_is_parsed():
    respx.post(HOOK).mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(DeliveryError) as exc:
            await WebhookNotifier(HOOK, http).notify(NotificationEvent.EXECUTION_FINISHED, report())
    assert exc.value.retry_after == 120


def test_backoff_is_capped_and_honours_retry_after():
    assert all(0 <= retry.next_delay(n) <= retry.MAX_DELAY_SECONDS for n in range(1, 30))
    assert retry.next_delay(1, retry_after=90) >= 90
    assert retry.next_delay(1, retry_after=10_000) == retry.MAX_DELAY_SECONDS


# --- outbox, against the database ---

class Scripted(Notifier):
    """Fails with the given errors in turn, then succeeds."""

    def __init__(self, *errors: DeliveryError) -> None:
        self.errors = list(errors)
        self.delivered: list[uuid.UUID] = []  # the SQLite file is shared: other tests' rows may be due too

    async def notify(self, event, report):
        self.delivered.append(report.id)
        if self.errors:
            raise self.errors.pop(0)

    def calls(self, execution: Execution) -> int:
        return self.delivered.count(execution.id)


@pytest.fixture
async def db():
    await init_db()
    async with AsyncSessionLocal() as session:
        yield session
    await close_db_connections()  # each test has its own event loop


async def finished_execution(db) -> Execution:
    """An execution driven to COMPLETED through the state machine, committed with its outbox row."""
    execution = Execution(id=uuid.uuid4(), user_id=f"u-{uuid.uuid4().hex[:8]}", idempotency_key="k",
                          request_hash="h", broker="mock", expires_at=datetime.now(UTC) + timedelta(hours=1),
                          orders=[])
    db.add(execution)
    await db.commit()
    transition_execution(execution, ExecutionState.COMPLETED)
    await db.commit()
    return execution


async def outbox(db, execution):
    [row] = await NotificationDAO(db).list_for_execution(execution.id)
    await db.refresh(row)
    return row


async def test_final_state_writes_exactly_one_outbox_row(db):
    row = await outbox(db, await finished_execution(db))
    assert (row.event, row.status, row.attempts) == (NotificationEvent.EXECUTION_FINISHED,
                                                     NotificationStatus.PENDING, 0)


async def test_due_row_is_delivered_and_marked_sent(db):
    execution = await finished_execution(db)
    notifier = Scripted()
    assert await NotificationModule(db, notifier).dispatch_due() >= 1
    row = await outbox(db, execution)
    assert (row.status, row.attempts) == (NotificationStatus.SENT, 1)
    await NotificationModule(db, notifier).dispatch_due()
    assert notifier.calls(execution) == 1  # sent once, not again


async def test_retryable_failure_is_rescheduled_not_lost(db):
    execution = await finished_execution(db)
    await NotificationModule(db, Scripted(DeliveryError("HTTP 503", retryable=True, retry_after=60))).dispatch_due()
    row = await outbox(db, execution)
    assert (row.status, row.attempts, row.last_error) == (NotificationStatus.PENDING, 1, "HTTP 503")
    assert row.next_attempt_at.replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(seconds=50)


async def test_refusal_is_dead_lettered_at_once(db):
    execution = await finished_execution(db)
    await NotificationModule(db, Scripted(DeliveryError("HTTP 404", retryable=False))).dispatch_due()
    assert (await outbox(db, execution)).status is NotificationStatus.FAILED


async def test_retries_stop_after_max_attempts(db, monkeypatch):
    monkeypatch.setattr(settings, "notification_max_attempts", 2)
    monkeypatch.setattr(retry, "next_delay", lambda *_: 0)  # due again at once
    execution = await finished_execution(db)
    down = Scripted(*[DeliveryError("HTTP 500", retryable=True)] * 5)
    for _ in range(3):
        await NotificationModule(db, down).dispatch_due()
    row = await outbox(db, execution)
    assert (row.status, row.attempts, down.calls(execution)) == (NotificationStatus.FAILED, 2, 2)


async def test_claim_is_a_lease(db):
    """A relay that dies after claiming leaves the row to be retried once the lease runs out."""
    execution = await finished_execution(db)
    now = datetime.now(UTC)
    await NotificationDAO(db).claim_due(now, 100, lease_until=now + timedelta(seconds=60))
    notifier = Scripted()
    await NotificationModule(db, notifier).dispatch_due()
    assert notifier.calls(execution) == 0  # leased: not due yet
    later = now + timedelta(seconds=61)
    claimed = await NotificationDAO(db).claim_due(later, 100, lease_until=later + timedelta(seconds=60))
    assert execution.id in {row.execution_id for row in claimed}
