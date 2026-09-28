from enum import StrEnum


class Action(StrEnum):
    BUY = "BUY"              # new position (all BUYs for a first-time portfolio)
    SELL = "SELL"            # exit a position
    REBALANCE = "REBALANCE"  # adjust a position by a signed quantity


class Phase(StrEnum):
    RELEASE = "RELEASE"  # frees money: SELL, REBALANCE down. Parallel.
    SPEND = "SPEND"      # uses money: REBALANCE up, BUY. Sequential, input order.


class OrderState(StrEnum):
    # in flight
    PENDING = "PENDING"          # planned, never sent
    SUBMITTING = "SUBMITTING"    # write-ahead marker: about to send, may have been sent
    PLACED = "PLACED"            # accepted by the broker, not yet terminal
    UNKNOWN = "UNKNOWN"          # sent, outcome unknown; reconciling by tag
    # final
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # terminal at the broker with 0 < filled < quantity
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"        # the broker refused it
    FAILED = "FAILED"            # provably never placed (bad symbol, broker unreachable)
    SKIPPED = "SKIPPED"          # deliberately not attempted; see message
    STILL_OPEN = "STILL_OPEN"    # placed, not terminal when tracking stopped
    UNCONFIRMED = "UNCONFIRMED"  # placement outcome never established

    @property
    def is_final(self) -> bool:
        return self not in _IN_FLIGHT

    @property
    def is_unresolved(self) -> bool:
        """Final for this run, but the investor must check the broker."""
        return self in (OrderState.STILL_OPEN, OrderState.UNCONFIRMED)


_IN_FLIGHT = {OrderState.PENDING, OrderState.SUBMITTING, OrderState.PLACED, OrderState.UNKNOWN}


class ExecutionState(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"  # every order reached a final state (not necessarily FILLED)
    ABORTED = "ABORTED"      # stopped early, e.g. broker session expired
    EXPIRED = "EXPIRED"      # market closed before an interrupted run was resumed
