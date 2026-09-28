"""Public API shapes for executions: the request we accept and the report we return/notify."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.integrations.brokers.enums import BrokerName, Exchange, Side
from src.models.enums import Action, ExecutionState, OrderState, Phase


class Instruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    symbol: str = Field(min_length=1, max_length=32, examples=["INFY"])
    exchange: Exchange = Exchange.NSE
    quantity: int = Field(description="Shares. BUY/SELL: positive. REBALANCE: signed change, "
                                      "e.g. -4 reduces the position by 4, +4 adds 4.")
    price: Decimal | None = Field(default=None, gt=0, description="Set for a LIMIT order; omit for MARKET.")

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class TargetHolding(BaseModel):
    """One stock of a first-time portfolio: the quantity to end up holding."""
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32, examples=["INFY"])
    exchange: Exchange = Exchange.NSE
    quantity: int = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class ExecutionCreate(BaseModel):
    """Exactly one of:
    - `target`: a first-time portfolio (the user holds nothing yet); every stock becomes a BUY.
    - `instructions`: an explicit rebalance of an existing portfolio (SELL / BUY / REBALANCE).
    """
    model_config = ConfigDict(extra="forbid")

    broker: BrokerName
    target: list[TargetHolding] | None = Field(default=None, min_length=1, max_length=100)
    instructions: list[Instruction] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _exactly_one_mode(self) -> Self:
        if (self.target is None) == (self.instructions is None):
            raise ValueError("Send exactly one of 'target' (first-time portfolio) or 'instructions' (rebalance)")
        return self


class OrderReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    action: Action
    phase: Phase
    symbol: str
    exchange: Exchange
    side: Side
    quantity: int
    price: Decimal | None
    tag: str
    state: OrderState
    broker_order_id: str | None
    filled_quantity: int
    average_price: Decimal | None
    message: str | None


class ExecutionReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker: BrokerName
    state: ExecutionState
    reason: str | None
    created_at: datetime | None
    expires_at: datetime
    finished_at: datetime | None
    summary: dict[OrderState, int] = {}
    needs_attention: list[str] = Field(default=[], description="Orders the investor must check at the broker.")
    orders: list[OrderReport]

    @model_validator(mode="after")
    def _derive(self) -> Self:
        self.summary = {}
        for o in self.orders:
            self.summary[o.state] = self.summary.get(o.state, 0) + 1
        self.needs_attention = [_attention(o) for o in self.orders if _attention(o)]
        return self


def _attention(o: OrderReport) -> str:
    label = f"{o.side} {o.quantity} {o.symbol}"
    if o.state is OrderState.UNCONFIRMED:
        return f"{label} (tag {o.tag}): placement not confirmed; check the broker's order book before retrying"
    if o.state is OrderState.STILL_OPEN:
        return f"{label} (order {o.broker_order_id}): still open at the broker; {o.filled_quantity} filled so far"
    if o.state is OrderState.PARTIALLY_FILLED:
        return f"{label}: only {o.filled_quantity} filled"
    return ""


class ExecutionEventReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int | None  # None: a change of the execution itself
    from_state: str
    to_state: str
    message: str | None
    created_at: datetime
