import pytest

from src.models import ExecutionOrder
from src.models.enums import OrderState
from src.modules.execution.exceptions import IllegalTransitionError
from src.modules.execution.transitions import ORDER_TRANSITIONS, transition_order


def order(state: OrderState) -> ExecutionOrder:
    return ExecutionOrder(position=0, symbol="INFY", side="BUY", quantity=1, tag="t", state=state)


def test_final_states_have_no_way_out():
    assert all(not ORDER_TRANSITIONS[s] for s in OrderState if s.is_final)


@pytest.mark.parametrize("start, to", [
    (OrderState.FILLED, OrderState.PLACED),        # a fill never un-happens
    (OrderState.PENDING, OrderState.FILLED),       # nothing fills without being sent
    (OrderState.PENDING, OrderState.UNCONFIRMED),  # never sent means provably not placed
    (OrderState.UNKNOWN, OrderState.SUBMITTING),   # an unknown outcome is never re-sent
])
def test_illegal_transition_is_refused_and_state_unchanged(start, to):
    o = order(start)
    with pytest.raises(IllegalTransitionError):
        transition_order(o, to)
    assert o.state is start


def test_same_state_updates_message_without_a_transition():
    o = order(OrderState.PLACED)
    transition_order(o, OrderState.PLACED, "still open")
    assert (o.state, o.message) == (OrderState.PLACED, "still open")
