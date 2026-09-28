"""Turns an execution request into planned order rows: side, phase and idempotency tag."""
import hashlib
import uuid

from src.integrations.brokers.enums import OrderType, Side
from src.models import ExecutionOrder
from src.schemas.execution import ExecutionCreate, Instruction

from src.models.execution.enums import Action, OrderState, Phase


def order_tag(execution_id: uuid.UUID, position: int) -> str:
    """Deterministic client tag: the same instruction of the same execution always gets the
    same tag, so a resumed run can find orders a crashed run already placed.

    20 hex chars (80 bits) fits every broker's limit (8-20 alphanumerics).
    """
    return hashlib.sha256(f"{execution_id}:{position}".encode()).hexdigest()[:20]


def instructions_for(request: ExecutionCreate) -> list[Instruction]:
    """A first-time target portfolio is all BUYs; a rebalance brings its own instructions."""
    if request.target is not None:
        return [Instruction(action=Action.BUY, symbol=t.symbol, exchange=t.exchange, quantity=t.quantity)
                for t in request.target]
    return request.instructions


def plan(execution_id: uuid.UUID, instructions: list[Instruction]) -> list[ExecutionOrder]:
    return [_plan_one(execution_id, position, i) for position, i in enumerate(instructions)]


def _plan_one(execution_id: uuid.UUID, position: int, i: Instruction) -> ExecutionOrder:
    side = _side(i)
    return ExecutionOrder(
        execution_id=execution_id,
        position=position,
        action=i.action,
        # Phases follow the direction of money, not the instruction type: a REBALANCE
        # can release money (reduce) or spend it (increase).
        phase=Phase.RELEASE if side is Side.SELL else Phase.SPEND,
        symbol=i.symbol,
        exchange=i.exchange,
        side=side,
        quantity=abs(i.quantity),
        order_type=OrderType.LIMIT if i.price is not None else OrderType.MARKET,
        price=i.price,
        tag=order_tag(execution_id, position),
        state=OrderState.PENDING,
        filled_quantity=0,
    )


def _side(i: Instruction) -> Side:
    if i.action is Action.REBALANCE:
        return Side.BUY if i.quantity > 0 else Side.SELL
    return Side.BUY if i.action is Action.BUY else Side.SELL
