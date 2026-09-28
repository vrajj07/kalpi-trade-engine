import uuid
from datetime import UTC, datetime

import pytest

from src.integrations.brokers.base import BrokerCredentials
from src.integrations.brokers.mock import MockBroker
from src.models import Execution
from src.models.enums import ExecutionState, OrderState
from src.modules.execution.executor import Executor
from src.modules.execution.helpers.planner import order_tag, plan
from src.schemas.execution import ExecutionCreate


def make_execution(*instructions: tuple) -> Execution:
    request = ExecutionCreate(broker="mock", instructions=[
        {"action": a, "symbol": s, "quantity": q} for a, s, q in instructions
    ])
    execution_id = uuid.uuid4()
    return Execution(id=execution_id, idempotency_key="k", request_hash="h", broker="mock",
                     state=ExecutionState.RUNNING, expires_at=datetime.now(UTC),
                     orders=plan(execution_id, request.instructions))


def broker(**extra) -> MockBroker:
    return MockBroker(BrokerCredentials(access_token="t", extra=extra))


async def run(execution: Execution, adapter: MockBroker, **kw) -> dict[str, OrderState]:
    async def save() -> None: ...
    await Executor(adapter, save, order_timeout=kw.get("timeout", 0.05), poll_interval=0.01).run(execution)
    return {o.symbol: o.state for o in execution.orders}


async def test_first_time_portfolio_all_buys_fill():
    execution = make_execution(("BUY", "INFY", 5), ("BUY", "TCS", 2))
    assert await run(execution, broker()) == {"INFY": OrderState.FILLED, "TCS": OrderState.FILLED}
    assert execution.state is ExecutionState.COMPLETED


async def test_sells_run_before_buys_and_fund_them():
    # Cash covers the BUY only with the SELL proceeds: order of execution matters.
    adapter = broker(holdings={"INFY": 10}, cash=0)
    execution = make_execution(("BUY", "TCS", 1), ("SELL", "INFY", 10))
    assert await run(execution, adapter) == {"TCS": OrderState.FILLED, "INFY": OrderState.FILLED}


async def test_rebalance_direction_decides_phase():
    execution = make_execution(("REBALANCE", "INFY", -4), ("REBALANCE", "TCS", 3))
    infy, tcs = execution.orders
    assert (infy.side, infy.quantity, infy.phase) == ("SELL", 4, "RELEASE")
    assert (tcs.side, tcs.quantity, tcs.phase) == ("BUY", 3, "SPEND")


async def test_spend_stops_at_first_rejection_strict_priority():
    # WIPRO (first) is unaffordable; the cheaper TCS after it must not jump the queue.
    execution = make_execution(("BUY", "WIPRO", 1000), ("BUY", "TCS", 1))
    states = await run(execution, broker(cash=1000))
    assert states == {"WIPRO": OrderState.REJECTED, "TCS": OrderState.SKIPPED}
    assert "blocked by BUY 1000 WIPRO" in execution.orders[1].message


async def test_failed_before_send_does_not_block_spend():
    execution = make_execution(("BUY", "NOPE", 1), ("BUY", "TCS", 1))
    assert await run(execution, broker(fail={"NOPE": "unavailable"})) == {
        "NOPE": OrderState.FAILED, "TCS": OrderState.FILLED}


async def test_unknown_outcome_is_reconciled_by_tag_not_resent():
    adapter = broker(holdings={"INFY": 10}, fail={"INFY": "unknown"})
    execution = make_execution(("SELL", "INFY", 10), ("BUY", "TCS", 1))
    assert await run(execution, adapter) == {"INFY": OrderState.FILLED, "TCS": OrderState.FILLED}
    assert len(adapter._orders) == 2  # no duplicate SELL


async def test_unconfirmed_sell_gates_every_buy():
    execution = make_execution(("SELL", "INFY", 1), ("BUY", "TCS", 1), ("REBALANCE", "HDFC", 2))
    states = await run(execution, broker(holdings={"INFY": 1}, fail={"INFY": "lost"}))
    assert states == {"INFY": OrderState.UNCONFIRMED, "TCS": OrderState.SKIPPED, "HDFC": OrderState.SKIPPED}
    assert "funding unconfirmed" in execution.orders[1].message


async def test_open_order_at_deadline_is_still_open_not_failed():
    execution = make_execution(("BUY", "INFY", 1), ("BUY", "TCS", 1))
    states = await run(execution, broker(fail={"INFY": "open"}))
    assert states == {"INFY": OrderState.STILL_OPEN, "TCS": OrderState.SKIPPED}


async def test_partial_fill_counts_filled_quantity():
    execution = make_execution(("SELL", "INFY", 10))
    await run(execution, broker(holdings={"INFY": 10}, fail={"INFY": "partial"}))
    (order,) = execution.orders
    assert (order.state, order.filled_quantity) == (OrderState.PARTIALLY_FILLED, 5)


async def test_expired_session_aborts_and_skips_the_rest():
    execution = make_execution(("BUY", "INFY", 1), ("BUY", "TCS", 1))
    states = await run(execution, broker(fail={"INFY": "auth"}))
    assert states == {"INFY": OrderState.FAILED, "TCS": OrderState.SKIPPED}
    assert execution.state is ExecutionState.ABORTED


async def test_resume_adopts_order_a_crashed_run_already_placed():
    adapter = broker(holdings={"INFY": 10})
    execution = make_execution(("SELL", "INFY", 10))
    (order,) = execution.orders
    # Simulate the crash: the order reached the broker, but we only saved SUBMITTING.
    await adapter.place_order(order.to_request())
    order.state = OrderState.SUBMITTING
    assert await run(execution, adapter) == {"INFY": OrderState.FILLED}
    assert len(adapter._orders) == 1


async def test_resume_sends_submitting_order_the_broker_never_got():
    execution = make_execution(("BUY", "INFY", 1))
    execution.orders[0].state = OrderState.SUBMITTING
    assert await run(execution, broker()) == {"INFY": OrderState.FILLED}


def test_tags_are_deterministic_and_fit_every_broker():
    execution_id = uuid.uuid4()
    assert order_tag(execution_id, 0) == order_tag(execution_id, 0) != order_tag(execution_id, 1)
    assert len(order_tag(execution_id, 0)) == 20 and order_tag(execution_id, 0).isalnum()
