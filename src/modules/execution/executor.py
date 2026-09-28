"""Places planned orders through a BrokerAdapter and drives each one to a final state.

Rules (see README, "Rebalance logic"):

1. RELEASE phase (SELL, REBALANCE down) runs in parallel; SPEND phase (REBALANCE up, BUY)
   runs one order at a time in input order, each tracked to a final state before the next.
2. Gate: if any RELEASE order is unresolved (STILL_OPEN / UNCONFIRMED), no SPEND order is
   sent — the money it would use is not proven to exist.
3. SPEND stops at the first order that is not FILLED or FAILED (never placed): a rejection
   may mean no funds, an unknown outcome may have used them. The rest are SKIPPED.
4. Write-ahead: an order is marked SUBMITTING and saved before it is sent. On resume, a
   SUBMITTING order is looked up by its tag first and only re-sent if the broker has none.
5. An expired session aborts the run; everything not yet sent is SKIPPED.

The executor mutates the ORM rows it is given and calls `save` after every transition;
it knows nothing about sessions or HTTP.
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from src.integrations.brokers.base import BrokerAdapter, BrokerOrder
from src.integrations.brokers.enums import OrderStatus
from src.integrations.brokers.errors import (
    BrokerAuthError,
    BrokerError,
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerUnavailableError,
    InstrumentNotFoundError,
)
from src.models import Execution, ExecutionOrder

from src.models.enums import ExecutionState, OrderState, Phase
from .transitions import transition_execution, transition_order

logger = logging.getLogger(__name__)

Save = Callable[[], Awaitable[None]]

# SPEND continues past these only: FILLED used exactly the money planned, FAILED used none.
_SPEND_CONTINUES = {OrderState.FILLED, OrderState.FAILED}


class SessionExpired(Exception):
    """Broker rejected our credentials: nothing further can be sent or tracked."""


class Executor:
    def __init__(self, adapter: BrokerAdapter, save: Save, *, order_timeout: float = 30.0,
                 poll_interval: float = 1.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._adapter = adapter
        self._save_fn = save
        self._timeout = order_timeout
        self._poll = poll_interval
        self._clock = clock
        # Parallel RELEASE orders share one DB session, which is not safe for concurrent use.
        self._lock = asyncio.Lock()

    async def run(self, execution: Execution) -> None:
        orders = sorted(execution.orders, key=lambda o: o.position)
        release = [o for o in orders if o.phase is Phase.RELEASE]
        spend = [o for o in orders if o.phase is Phase.SPEND]
        try:
            results = await asyncio.gather(*(self._execute(o) for o in release), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(result, SessionExpired):
                    raise result
            if expired := next((r for r in results if isinstance(r, SessionExpired)), None):
                raise expired
            await self._spend(spend, release)
        except SessionExpired as exc:
            await self._abort(execution, str(exc))
            return
        transition_execution(execution, ExecutionState.COMPLETED)
        await self._save()

    # --- phases -----------------------------------------------------------------------

    async def _spend(self, spend: list[ExecutionOrder], release: list[ExecutionOrder]) -> None:
        blocked: str | None = None
        if unresolved := next((o for o in release if o.state.is_unresolved), None):
            blocked = f"funding unconfirmed: {unresolved.label} is {unresolved.state}"

        for order in spend:
            if blocked and order.state is OrderState.PENDING:
                self._set(order, OrderState.SKIPPED, f"Not sent, {blocked}")
                await self._save()
                continue
            # In-flight orders (resumed run) are resolved even when blocked: they may exist.
            if not order.state.is_final:
                await self._execute(order)
            if blocked is None and order.state not in _SPEND_CONTINUES | {OrderState.SKIPPED}:
                blocked = f"blocked by {order.label} ({order.state})"

    async def _abort(self, execution: Execution, reason: str) -> None:
        for order in execution.orders:
            if order.state is OrderState.PENDING:
                self._set(order, OrderState.SKIPPED, "Not sent, broker session expired")
            elif order.state is OrderState.PLACED:
                self._set(order, OrderState.STILL_OPEN, "Tracking stopped, broker session expired")
            elif not order.state.is_final:
                self._set(order, OrderState.UNCONFIRMED, "Not reconciled, broker session expired")
        transition_execution(execution, ExecutionState.ABORTED,
                             f"Broker session expired ({reason}). Log in to the broker again, then resubmit.")
        await self._save()

    # --- one order ----------------------------------------------------------------------

    async def _execute(self, order: ExecutionOrder) -> None:
        deadline = self._clock() + self._timeout
        if order.state is OrderState.PENDING:
            await self._place(order)
        elif order.state is OrderState.SUBMITTING:
            await self._check_then_place(order)
        if order.state is OrderState.UNKNOWN:
            await self._reconcile(order, deadline)
        if order.state is OrderState.PLACED:
            await self._track(order, deadline)

    async def _place(self, order: ExecutionOrder) -> None:
        self._set(order, OrderState.SUBMITTING)
        await self._save()  # write-ahead: from here on the order may exist at the broker
        try:
            placed = await self._adapter.place_order(order.to_request())
        except BrokerAuthError as exc:
            self._set(order, OrderState.FAILED, f"Not placed: {exc.message}")
            await self._save()
            raise SessionExpired(exc.message) from exc
        except (InstrumentNotFoundError, ValidationError) as exc:
            self._set(order, OrderState.FAILED, f"Not placed: {_message(exc)}")
        except BrokerRequestError as exc:
            self._set(order, OrderState.REJECTED, exc.message)
        except (BrokerUnavailableError, BrokerRateLimitError) as exc:
            self._set(order, OrderState.FAILED, f"Not placed, broker unreachable after retries: {exc.message}")
        except BrokerError as exc:
            # OrderStateUnknownError, or anything unexpected after send: fail closed.
            self._set(order, OrderState.UNKNOWN, exc.message)
        else:
            self._adopt(order, placed)
        await self._save()

    async def _check_then_place(self, order: ExecutionOrder) -> None:
        """Resume after a crash between the write-ahead record and knowing the outcome."""
        try:
            found = await self._adapter.find_order(order.tag)
        except BrokerAuthError as exc:
            self._set(order, OrderState.UNCONFIRMED, f"Could not check order book: {exc.message}")
            await self._save()
            raise SessionExpired(exc.message) from exc
        except BrokerError as exc:
            self._set(order, OrderState.UNKNOWN, f"Could not check order book: {exc.message}")
            await self._save()
            return
        if found is not None:
            self._adopt(order, found)
            await self._save()
        else:
            await self._place(order)

    async def _reconcile(self, order: ExecutionOrder, deadline: float) -> None:
        """Look for the order by tag until found or the deadline passes. Never re-sends."""
        while True:
            try:
                found = await self._adapter.find_order(order.tag)
            except BrokerAuthError as exc:
                self._set(order, OrderState.UNCONFIRMED, f"Not reconciled: {exc.message}")
                await self._save()
                raise SessionExpired(exc.message) from exc
            except BrokerError as exc:
                logger.warning("Order book lookup failed for %s: %s", order.tag, exc.message)
                found = None
            if found is not None:
                self._adopt(order, found)
                await self._save()
                return
            if self._clock() >= deadline:
                self._set(order, OrderState.UNCONFIRMED,
                          f"No order with tag {order.tag} found within {self._timeout:g}s")
                await self._save()
                return
            await asyncio.sleep(self._poll)

    async def _track(self, order: ExecutionOrder, deadline: float) -> None:
        while self._clock() < deadline:
            await asyncio.sleep(self._poll)
            try:
                latest = await self._adapter.get_order(order.broker_order_id or "")
            except BrokerAuthError as exc:
                self._set(order, OrderState.STILL_OPEN, f"Tracking stopped: {exc.message}")
                await self._save()
                raise SessionExpired(exc.message) from exc
            except BrokerError as exc:
                logger.warning("Status poll failed for %s: %s", order.broker_order_id, exc.message)
                continue
            self._adopt(order, latest)
            if order.state is not OrderState.PLACED:
                await self._save()
                return
        self._set(order, OrderState.STILL_OPEN, f"Not complete within {self._timeout:g}s")
        await self._save()

    # --- helpers ----------------------------------------------------------------------

    def _adopt(self, order: ExecutionOrder, broker_order: BrokerOrder) -> None:
        order.broker_order_id = broker_order.broker_order_id
        order.filled_quantity = broker_order.filled_quantity
        order.average_price = broker_order.average_price
        status = broker_order.status
        if status is OrderStatus.COMPLETE:
            order.filled_quantity = broker_order.filled_quantity or order.quantity
            self._set(order, OrderState.FILLED, broker_order.message)
        elif status.is_terminal and broker_order.filled_quantity > 0:
            # Fills count, not the status: a CANCELLED order may still have sold shares.
            self._set(order, OrderState.PARTIALLY_FILLED, broker_order.message)
        elif status is OrderStatus.REJECTED:
            self._set(order, OrderState.REJECTED, broker_order.message)
        elif status is OrderStatus.CANCELLED:
            self._set(order, OrderState.CANCELLED, broker_order.message)
        else:
            self._set(order, OrderState.PLACED, broker_order.message)

    @staticmethod
    def _set(order: ExecutionOrder, state: OrderState, message: str | None = None) -> None:
        transition_order(order, state, message)

    async def _save(self) -> None:
        async with self._lock:
            await self._save_fn()


def _message(exc: Exception) -> str:
    return exc.message if isinstance(exc, BrokerError) else str(exc).splitlines()[0]
