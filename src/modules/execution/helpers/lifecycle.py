"""Execution-level state transitions that are not driven by an order: expiry and abort."""
from datetime import UTC, datetime, timedelta, timezone

from src.core.config import settings
from src.models import Execution
from src.models.enums import ExecutionState, OrderState
from src.modules.execution.transitions import transition_execution, transition_order

IST = timezone(timedelta(hours=5, minutes=30))  # no DST, so a fixed offset is exact


def next_market_close(now: datetime) -> datetime:
    """Order books only cover the current day, so an execution cannot be resumed past this."""
    local = now.astimezone(IST)
    close = datetime.combine(local.date(), settings.market_close_ist, IST)
    return close if local < close else close + timedelta(days=1)


def is_expired(execution: Execution, now: datetime) -> bool:
    expires_at = execution.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive datetimes
        expires_at = expires_at.replace(tzinfo=UTC)
    return now >= expires_at


def expire(execution: Execution) -> None:
    stop(execution, ExecutionState.EXPIRED, "Market closed before the interrupted run was resumed",
         "Not sent, market closed")


def stop(execution: Execution, state: ExecutionState, reason: str, skipped_message: str) -> None:
    """Ends the execution: unsent orders are SKIPPED, in-flight ones UNCONFIRMED (never guessed)."""
    for order in execution.orders:
        if order.state is OrderState.PENDING:
            transition_order(order, OrderState.SKIPPED, skipped_message)
        elif not order.state.is_final:
            transition_order(order, OrderState.UNCONFIRMED, f"Not reconciled: {reason}")
    transition_execution(execution, state, reason)
