"""One planned broker order of an execution, with its progress."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, WriteOnlyMapped, mapped_column, relationship

from src.core.database import Base
from src.integrations.brokers.base import OrderRequest
from src.integrations.brokers.enums import Exchange, OrderType, Side
from src.models.columns import enum_column
from src.models.execution.enums import Action, OrderState, Phase

if TYPE_CHECKING:
    from src.models.execution.execution import Execution
    from src.models.execution.event import ExecutionEvent


class ExecutionOrder(Base):
    __tablename__ = "execution_orders"
    __table_args__ = (UniqueConstraint("execution_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    position: Mapped[int]  # index in the submitted instruction list: priority within a phase
    action: Mapped[Action] = mapped_column(enum_column(Action))
    phase: Mapped[Phase] = mapped_column(enum_column(Phase))
    symbol: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[Exchange] = mapped_column(enum_column(Exchange))
    side: Mapped[Side] = mapped_column(enum_column(Side))
    quantity: Mapped[int]
    order_type: Mapped[OrderType] = mapped_column(enum_column(OrderType))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tag: Mapped[str] = mapped_column(String(20), unique=True)

    state: Mapped[OrderState] = mapped_column(enum_column(OrderState), default=OrderState.PENDING)
    broker_order_id: Mapped[str | None] = mapped_column(String(64))
    filled_quantity: Mapped[int] = mapped_column(default=0)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

    execution: Mapped["Execution"] = relationship(back_populates="orders")
    events: WriteOnlyMapped["ExecutionEvent"] = relationship(cascade="all, delete-orphan", passive_deletes=True)

    @property
    def label(self) -> str:
        return f"{self.side} {self.quantity} {self.symbol}"

    def to_request(self) -> OrderRequest:
        return OrderRequest(symbol=self.symbol, exchange=self.exchange, side=self.side, quantity=self.quantity,
                            order_type=self.order_type, price=self.price, tag=self.tag)
