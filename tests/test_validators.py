from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.integrations.brokers.base import Holding
from src.modules.execution.exceptions import (
    InvalidInstructionsError,
    PortfolioNotEmptyError,
    UnconfiguredBrokerError,
)
from src.modules.execution.validators import ExecutionValidator
from src.schemas.execution import ExecutionCreate


def request(*instructions: dict, broker: str = "mock") -> ExecutionCreate:
    return ExecutionCreate(broker=broker, instructions=list(instructions))


@pytest.mark.parametrize("instructions, error", [
    ([{"action": "REBALANCE", "symbol": "INFY", "quantity": 0}], "REBALANCE quantity must be non-zero"),
    ([{"action": "SELL", "symbol": "INFY", "quantity": -3}], "SELL quantity must be positive"),
    ([{"action": "BUY", "symbol": "INFY", "quantity": 1}, {"action": "SELL", "symbol": "infy", "quantity": 1}],
     "instructions[1]: more than one entry for NSE:INFY"),
])
def test_invalid_instructions_are_rejected(instructions, error):
    with pytest.raises(InvalidInstructionsError) as exc:
        ExecutionValidator().validate(request(*instructions))
    assert any(error in e for e in exc.value.errors)


def test_every_instruction_error_is_reported_at_once():
    with pytest.raises(InvalidInstructionsError) as exc:
        ExecutionValidator().validate(request({"action": "BUY", "symbol": "INFY", "quantity": 0},
                                              {"action": "SELL", "symbol": "TCS", "quantity": -1}))
    assert len(exc.value.errors) == 2


def test_unconfigured_broker_is_rejected():
    with pytest.raises(UnconfiguredBrokerError):
        ExecutionValidator().validate(request({"action": "BUY", "symbol": "INFY", "quantity": 1}, broker="zerodha"))


def holding(symbol: str, quantity: int) -> Holding:
    return Holding(symbol=symbol, exchange="NSE", quantity=quantity, average_price=Decimal("100"))


HELD = [holding("INFY", 10), holding("TCS", 5)]


@pytest.mark.parametrize("instruction, error", [
    ({"action": "BUY", "symbol": "INFY", "quantity": 1}, "BUY is for new stocks"),
    ({"action": "SELL", "symbol": "WIPRO", "quantity": 1}, "cannot SELL WIPRO, it is not held"),
    ({"action": "SELL", "symbol": "INFY", "quantity": 7}, "use REBALANCE -7 to reduce it"),
    ({"action": "SELL", "symbol": "INFY", "quantity": 12}, "SELL the full holding to exit"),
    ({"action": "REBALANCE", "symbol": "WIPRO", "quantity": 2}, "WIPRO is not held; use BUY"),
    ({"action": "REBALANCE", "symbol": "TCS", "quantity": -6}, "cannot reduce TCS by 6, only 5 are held"),
])
def test_instruction_must_match_holdings(instruction, error):
    with pytest.raises(InvalidInstructionsError) as exc:
        ExecutionValidator().validate_against_holdings(request(instruction), HELD)
    assert error in exc.value.errors[0]


def test_valid_rebalance_passes_holdings_check():
    ExecutionValidator().validate_against_holdings(request(
        {"action": "SELL", "symbol": "INFY", "quantity": 10},    # full exit
        {"action": "REBALANCE", "symbol": "TCS", "quantity": -5},  # reduce to zero is allowed
        {"action": "BUY", "symbol": "WIPRO", "quantity": 3},
    ), HELD)


def test_target_portfolio_is_only_for_first_time():
    target = ExecutionCreate(broker="mock", target=[{"symbol": "WIPRO", "quantity": 3}])
    ExecutionValidator().validate_against_holdings(target, [])
    with pytest.raises(PortfolioNotEmptyError):
        ExecutionValidator().validate_against_holdings(target, HELD)


def test_duplicate_target_symbol_is_rejected():
    with pytest.raises(InvalidInstructionsError):
        ExecutionValidator().validate(ExecutionCreate(broker="mock", target=[
            {"symbol": "INFY", "quantity": 1}, {"symbol": "infy", "quantity": 2}]))


@pytest.mark.parametrize("body", [
    {"broker": "mock"},
    {"broker": "mock", "target": [{"symbol": "INFY", "quantity": 1}],
     "instructions": [{"action": "BUY", "symbol": "TCS", "quantity": 1}]},
])
def test_exactly_one_of_target_or_instructions(body):
    with pytest.raises(ValidationError):
        ExecutionCreate(**body)
