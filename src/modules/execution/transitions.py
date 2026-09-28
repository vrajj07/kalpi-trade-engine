"""The state machine: every legal state change, and the only functions allowed to make one.

Each change is checked against the table, applied, and recorded as an ExecutionEvent in the
same unit of work, so the audit log and the current state are committed together.
A final state has no outgoing transitions: a FILLED order can never become PLACED again.
"""
import logging
from datetime import UTC, datetime

from src.models import Execution, ExecutionEvent, ExecutionOrder

from src.models.enums import ExecutionState, OrderState
from .exceptions import IllegalTransitionError

logger = logging.getLogger(__name__)

O = OrderState
_BROKER_OUTCOMES = {O.PLACED, O.FILLED, O.PARTIALLY_FILLED, O.REJECTED, O.CANCELLED}

ORDER_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    O.PENDING: {O.SUBMITTING, O.SKIPPED},
    # Sent or about to be: the broker's answer, a failure before send, or no answer.
    O.SUBMITTING: _BROKER_OUTCOMES | {O.FAILED, O.UNKNOWN, O.UNCONFIRMED},
    O.UNKNOWN: _BROKER_OUTCOMES | {O.UNCONFIRMED},
    O.PLACED: _BROKER_OUTCOMES - {O.PLACED} | {O.STILL_OPEN, O.UNCONFIRMED},
    **{state: set() for state in OrderState if state.is_final},
}

EXECUTION_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.RUNNING: {ExecutionState.COMPLETED, ExecutionState.ABORTED, ExecutionState.EXPIRED},
    ExecutionState.COMPLETED: set(),
    ExecutionState.ABORTED: set(),
    ExecutionState.EXPIRED: set(),
}


def transition_order(order: ExecutionOrder, to: OrderState, message: str | None = None) -> None:
    """Staying in the same state is not a transition (e.g. a poll that finds the order still
    open, or re-marking SUBMITTING on resume): the message is updated, nothing is recorded."""
    if message:
        order.message = message
    if to is order.state:
        return
    if to not in ORDER_TRANSITIONS[order.state]:
        raise IllegalTransitionError(f"Order {order.tag} ({order.label}): {order.state} -> {to}")
    logger.info("execution=%s order=%s %s: %s -> %s", order.execution_id, order.position, order.label,
                order.state, to)
    order.events.add(ExecutionEvent(execution_id=order.execution_id, from_state=order.state, to_state=to,
                                    message=message))
    order.state = to


def transition_execution(execution: Execution, to: ExecutionState, reason: str | None = None) -> None:
    if to not in EXECUTION_TRANSITIONS[execution.state]:
        raise IllegalTransitionError(f"Execution {execution.id}: {execution.state} -> {to}")
    logger.info("execution=%s: %s -> %s", execution.id, execution.state, to)
    execution.events.add(ExecutionEvent(from_state=execution.state, to_state=to, message=reason))
    execution.state, execution.reason = to, reason
    execution.finished_at = datetime.now(UTC)
