"""Semantic validation of an execution request: rules about what the request means.

The schema (src/schemas/execution.py) only checks shape: types, ranges, lengths, and that exactly
one of `target` / `instructions` is sent. Rules that depend on the action, on other instructions,
on configuration or on the user's holdings live here.

Holdings checks are a fail-fast guard, not a guarantee: holdings are read at submission and can
change before the orders are sent (time-of-check to time-of-use), and settled holdings are not
exactly the sellable quantity (today's buys, shares blocked by open orders, pledged shares).
The broker's rejection stays the source of truth.
"""
from collections.abc import Sequence

from src.integrations.brokers.base import Holding
from src.integrations.brokers.enums import BrokerName, Exchange
from src.integrations.brokers.registry import is_configured
from src.models import Execution
from src.models.enums import Action
from src.modules.execution.exceptions import (
    IdempotencyKeyReusedError,
    InvalidInstructionsError,
    PortfolioNotEmptyError,
    UnconfiguredBrokerError,
)
from src.schemas.execution import ExecutionCreate, Instruction, TargetHolding


class ExecutionValidator:
    def validate(self, request: ExecutionCreate) -> None:
        """Checks that need no data: collected and raised together, then the broker."""
        if request.target is not None:
            errors = self.validate_one_per_symbol(request.target, field="target")
        else:
            errors = [*self.validate_quantities(request.instructions),
                      *self.validate_one_per_symbol(request.instructions, field="instructions")]
        if errors:
            raise InvalidInstructionsError(errors)
        self.validate_broker_configured(request.broker)

    def validate_against_holdings(self, request: ExecutionCreate, holdings: list[Holding]) -> None:
        held = {(h.exchange, h.symbol): h.quantity for h in holdings if h.quantity > 0}
        if request.target is not None:
            self.validate_first_time(held)
        elif errors := self.validate_instructions_against_holdings(request.instructions, held):
            raise InvalidInstructionsError(errors)

    def validate_quantities(self, instructions: list[Instruction]) -> list[str]:
        """BUY/SELL carry a positive quantity; REBALANCE a signed, non-zero change."""
        errors = []
        for position, i in enumerate(instructions):
            if i.action is Action.REBALANCE and i.quantity == 0:
                errors.append(f"instructions[{position}]: REBALANCE quantity must be non-zero")
            elif i.action is not Action.REBALANCE and i.quantity <= 0:
                errors.append(f"instructions[{position}]: {i.action} quantity must be positive")
        return errors

    def validate_one_per_symbol(self, items: Sequence[Instruction | TargetHolding], field: str) -> list[str]:
        """Two entries for one symbol would race each other and make the intent ambiguous."""
        errors = []
        seen: set[tuple[Exchange, str]] = set()
        for position, i in enumerate(items):
            if (i.exchange, i.symbol) in seen:
                errors.append(f"{field}[{position}]: more than one entry for {i.exchange}:{i.symbol}")
            seen.add((i.exchange, i.symbol))
        return errors

    def validate_broker_configured(self, broker: BrokerName) -> None:
        """Fail at submission, not later in the background run."""
        if not is_configured(broker):
            raise UnconfiguredBrokerError(broker)

    def validate_first_time(self, held: dict[tuple[Exchange, str], int]) -> None:
        """A target portfolio is all BUYs, which is only right when nothing is held yet."""
        if held:
            raise PortfolioNotEmptyError(len(held))

    def validate_instructions_against_holdings(self, instructions: list[Instruction],
                                               held: dict[tuple[Exchange, str], int]) -> list[str]:
        """Each action keeps its meaning: BUY adds a new stock, SELL exits a held stock completely,
        REBALANCE adjusts a held stock. A partial exit is a REBALANCE, so the model's view and the
        broker's view of the portfolio cannot silently drift apart."""
        errors = []
        for position, i in enumerate(instructions):
            at, quantity = f"instructions[{position}]", held.get((i.exchange, i.symbol), 0)
            if i.action is Action.BUY and quantity:
                errors.append(f"{at}: BUY is for new stocks, but {quantity} {i.symbol} are held; "
                              f"use REBALANCE +{i.quantity} to add to it")
            elif i.action is Action.SELL and not quantity:
                errors.append(f"{at}: cannot SELL {i.symbol}, it is not held")
            elif i.action is Action.SELL and i.quantity != quantity:
                hint = (f"use REBALANCE -{i.quantity} to reduce it" if i.quantity < quantity
                        else "SELL the full holding to exit")
                errors.append(f"{at}: SELL exits the whole position: {quantity} {i.symbol} are held, "
                              f"not {i.quantity}; {hint}")
            elif i.action is Action.REBALANCE and not quantity:
                errors.append(f"{at}: REBALANCE adjusts a held stock, but {i.symbol} is not held; use BUY")
            elif i.action is Action.REBALANCE and -i.quantity > quantity:
                errors.append(f"{at}: cannot reduce {i.symbol} by {-i.quantity}, only {quantity} are held")
        return errors

    def validate_replay(self, existing: Execution, request_hash: str) -> None:
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReusedError()
