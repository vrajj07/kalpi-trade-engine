"""Semantic validation of an execution request: rules about what the request means.

The schema (src/schemas/execution.py) only checks shape: types, ranges, lengths. Rules that
depend on the action, on other instructions, or on configuration live here.
"""
from src.integrations.brokers.enums import BrokerName, Exchange
from src.integrations.brokers.registry import is_configured
from src.models import Execution
from src.models.enums import Action
from src.modules.execution.exceptions import (
    IdempotencyKeyReusedError,
    InvalidInstructionsError,
    UnconfiguredBrokerError,
)
from src.schemas.execution import ExecutionCreate, Instruction


class ExecutionValidator:
    def validate(self, request: ExecutionCreate) -> None:
        """Checks a new request. Instruction errors are collected and raised together."""
        errors = [*self.validate_quantities(request.instructions),
                  *self.validate_one_instruction_per_symbol(request.instructions)]
        if errors:
            raise InvalidInstructionsError(errors)
        self.validate_broker_configured(request.broker)

    def validate_quantities(self, instructions: list[Instruction]) -> list[str]:
        """BUY/SELL carry a positive quantity; REBALANCE a signed, non-zero change."""
        errors = []
        for position, i in enumerate(instructions):
            if i.action is Action.REBALANCE and i.quantity == 0:
                errors.append(f"instructions[{position}]: REBALANCE quantity must be non-zero")
            elif i.action is not Action.REBALANCE and i.quantity <= 0:
                errors.append(f"instructions[{position}]: {i.action} quantity must be positive")
        return errors

    def validate_one_instruction_per_symbol(self, instructions: list[Instruction]) -> list[str]:
        """Two instructions for one symbol would race each other and make the intent ambiguous."""
        errors = []
        seen: set[tuple[Exchange, str]] = set()
        for position, i in enumerate(instructions):
            if (i.exchange, i.symbol) in seen:
                errors.append(f"instructions[{position}]: more than one instruction for {i.exchange}:{i.symbol}")
            seen.add((i.exchange, i.symbol))
        return errors

    def validate_broker_configured(self, broker: BrokerName) -> None:
        """Fail at submission, not later in the background run."""
        if not is_configured(broker):
            raise UnconfiguredBrokerError(broker)

    def validate_replay(self, existing: Execution, request_hash: str) -> None:
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError()
