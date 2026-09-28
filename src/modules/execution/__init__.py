"""Execution module: plans, persists and runs a portfolio execution.

Layout:
    __init__.py   ExecutionModule, the entry point the service layer calls
    executor.py   drives planned orders through the broker (RELEASE, gate, SPEND)
    transitions.py the state machine and the audit log
    helpers/      planning, idempotency fingerprint, expiry, background task registry
    validators/   semantic checks on a request, called by the service before the module
    exceptions.py domain errors, converted to HTTP errors by the service
"""
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.dao.execution import ExecutionDAO
from src.integrations.brokers.errors import BrokerError
from src.integrations.brokers.registry import get_adapter
from src.models import Execution
from src.models.enums import ExecutionState
from src.modules.execution.executor import Executor
from src.modules.execution.helpers import lifecycle, runner
from src.modules.execution.helpers.idempotency import request_hash
from src.modules.execution.helpers.planner import instructions_for, plan
from src.modules.notification.base import get_notifier
from src.schemas.execution import ExecutionCreate, ExecutionReport

logger = logging.getLogger(__name__)


class ExecutionModule:
    """Orchestrates planning, the write-ahead record, the background run and its notification.
    Requests come pre-fetched and validated from the service layer."""

    def __init__(self, db: AsyncSession) -> None:
        self.dao = ExecutionDAO(db)

    @staticmethod
    def fingerprint(request: ExecutionCreate) -> str:
        return request_hash(request)

    async def create(self, idempotency_key: str, request: ExecutionCreate,
                     fingerprint: str) -> tuple[Execution, bool]:
        """Plans the orders and persists the whole plan before any order is sent (write-ahead).

        Returns (execution, created). created is False when a concurrent request with the same
        key won the insert: its execution is returned instead.
        """
        execution = Execution(id=uuid.uuid4(), idempotency_key=idempotency_key, request_hash=fingerprint,
                              broker=request.broker, state=ExecutionState.RUNNING,
                              expires_at=lifecycle.next_market_close(datetime.now(UTC)))
        execution.orders = plan(execution.id, instructions_for(request))
        try:
            await self.dao.create(execution)
        except IntegrityError:
            await self.dao.rollback()
            if (winner := await self.dao.get_by_idempotency_key(idempotency_key)) is None:
                raise
            return winner, False
        return execution, True

    async def start(self, execution: Execution) -> None:
        """Runs a new or interrupted execution in the background, unless the market has closed
        since. A finished one, or one already running in this process, is left alone."""
        if execution.state is not ExecutionState.RUNNING or runner.is_running(execution.id):
            return
        if lifecycle.is_expired(execution, datetime.now(UTC)):
            lifecycle.expire(execution)
            await self.dao.save()
            return
        execution_id = execution.id
        runner.start(execution_id, lambda session: ExecutionModule(session).run(execution_id))

    async def run(self, execution_id: uuid.UUID) -> None:
        """Background run: drives the execution to a final state, then sends the report."""
        if (execution := await self.dao.get_by_id(execution_id)) is None:
            return
        try:
            adapter = get_adapter(execution.broker)
        except BrokerError as exc:
            lifecycle.stop(execution, ExecutionState.ABORTED, exc.message, "Not sent, broker not available")
            await self.dao.save()
        else:
            try:
                async with adapter:
                    await Executor(adapter, self.dao.save, order_timeout=settings.order_timeout_seconds,
                                   poll_interval=settings.order_poll_interval_seconds).run(execution)
            except Exception:
                # Left RUNNING on purpose: resubmitting with the same key resumes it safely.
                logger.exception("Execution %s interrupted; resubmit with the same Idempotency-Key", execution_id)
                return
        await get_notifier().notify(ExecutionReport.model_validate(execution))


__all__ = ["ExecutionModule"]
