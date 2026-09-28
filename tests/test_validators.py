import pytest

from src.modules.execution.exceptions import InvalidInstructionsError, UnconfiguredBrokerError
from src.modules.execution.validators import ExecutionValidator
from src.schemas.execution import ExecutionCreate


def request(*instructions: dict, broker: str = "mock") -> ExecutionCreate:
    return ExecutionCreate(broker=broker, instructions=list(instructions))


@pytest.mark.parametrize("instructions, error", [
    ([{"action": "REBALANCE", "symbol": "INFY", "quantity": 0}], "REBALANCE quantity must be non-zero"),
    ([{"action": "SELL", "symbol": "INFY", "quantity": -3}], "SELL quantity must be positive"),
    ([{"action": "BUY", "symbol": "INFY", "quantity": 1}, {"action": "SELL", "symbol": "infy", "quantity": 1}],
     "instructions[1]: more than one instruction for NSE:INFY"),
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
