"""AgentBreaker (#108 Week-0 disaster guard, graduated from G2 prototype).

An adapter-level circuit breaker that sits **below all pipeline logic**, the last
line of defence between a (possibly runaway) autonomous agent/pipeline loop and
the broker. No matter what upstream strategy, model, or agent decides, a single
trading day cannot exceed:

  * a hard **order-count cap** (``max_orders_per_day``), and
  * a hard **notional cap** (``max_notional_per_day``, summed over ``abs``).

and a manual **TRADING_OFF kill switch** (``off_flag`` file) dominates both: if
that file exists, every admission is refused regardless of the counters.

Design contract (the proofs the prototype carried, now pinned by the test suite):

  * **P1 — runaway bounded.** ``admit`` can succeed at most ``max_orders_per_day``
    times within one ``today``, no matter how many times it is called.
  * **P2 — notional bound.** The cumulative admitted notional within one ``today``
    never exceeds ``max_notional_per_day``.
  * **P3 — day roll resets.** A new ``today`` resets both counters; nothing
    carries across days.
  * **P4 — TRADING_OFF dominates.** While ``off_flag`` exists, ``admit`` always
    raises, even when both counters have headroom and even on the first call.

Usage (one call per order, immediately before broker submission)::

    breaker = AgentBreaker(max_orders_per_day=25, max_notional_per_day=5_000)
    try:
        breaker.admit(today=date.today(), notional=order.notional)
    except BreakerTripped as exc:
        # MUST NOT retry-loop — log, halt the order, surface the reason.
        ...
    else:
        broker.submit(order)

``admit`` is fail-closed and **counts only on success**: a rejected order does
not consume order-count or notional budget, so a tripped breaker does not eat the
day's remaining headroom. The caller must never wrap ``admit`` in a retry loop —
a tripped breaker is a stop, not a transient error.

The breaker holds in-process counters only; it is intentionally not persisted.
A process restart starts the day fresh. The TRADING_OFF flag is the durable,
out-of-band control surface and is re-checked on every ``admit``.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

# Default kill-switch location. Injected explicitly in tests so the suite never
# touches a shared/live path; production wiring (S0-PR-G2) supplies the real one.
DEFAULT_OFF_FLAG = Path("/tmp/TRADING_OFF")


class BreakerTripped(Exception):
    """Raised by :meth:`AgentBreaker.admit` when an order must NOT be submitted.

    A stop, not a transient error: the caller must surface the reason and halt
    the order, never retry-loop.
    """


class AgentBreaker:
    """Hard per-day order/notional caps plus a manual TRADING_OFF kill switch.

    Parameters
    ----------
    max_orders_per_day:
        Maximum number of orders that may be admitted within a single ``today``.
        Must be a positive integer.
    max_notional_per_day:
        Maximum cumulative ``abs(notional)`` that may be admitted within a single
        ``today``. Must be a positive number.
    off_flag:
        Path to the manual kill-switch file. While it exists, every admission is
        refused. Defaults to :data:`DEFAULT_OFF_FLAG`; inject an isolated path in
        tests so the suite is hermetic.
    """

    def __init__(
        self,
        *,
        max_orders_per_day: int = 25,
        max_notional_per_day: float = 5_000.0,
        off_flag: Path = DEFAULT_OFF_FLAG,
    ) -> None:
        if max_orders_per_day <= 0:
            raise ValueError(
                f"max_orders_per_day must be positive, got {max_orders_per_day!r}"
            )
        if max_notional_per_day <= 0:
            raise ValueError(
                f"max_notional_per_day must be positive, got {max_notional_per_day!r}"
            )
        self.max_orders = int(max_orders_per_day)
        self.max_notional = float(max_notional_per_day)
        self.off_flag = Path(off_flag)
        self._day: dt.date | None = None
        self._orders = 0
        self._notional = 0.0

    def _roll(self, today: dt.date) -> None:
        """Reset the day's counters when ``today`` advances (P3)."""
        if self._day != today:
            self._day, self._orders, self._notional = today, 0, 0.0

    def admit(self, *, today: dt.date, notional: float) -> None:
        """Admit one order, or raise :class:`BreakerTripped`.

        Call exactly once per order, immediately before broker submission. On a
        rejection nothing is consumed (counts only on success), so a tripped
        breaker does not eat the remaining daily budget.

        Order of checks — TRADING_OFF first (it dominates), then order count,
        then notional:

          * TRADING_OFF file present        -> raise (P4)
          * order-count cap would be passed  -> raise (P1)
          * notional cap would be passed     -> raise (P2)

        Raises
        ------
        BreakerTripped
            If any of the three guards bind. The caller MUST NOT retry-loop.
        """
        if self.off_flag.exists():
            raise BreakerTripped(f"manual TRADING_OFF present: {self.off_flag}")
        self._roll(today)
        if self._orders + 1 > self.max_orders:
            raise BreakerTripped(f"daily order cap {self.max_orders} reached")
        amount = abs(notional)
        if self._notional + amount > self.max_notional:
            raise BreakerTripped(
                f"daily notional cap {self.max_notional:.0f} would be exceeded "
                f"({self._notional:.0f}+{amount:.0f})"
            )
        self._orders += 1
        self._notional += amount

    @property
    def orders_today(self) -> int:
        """Orders admitted so far for the current day (0 before any admit)."""
        return self._orders

    @property
    def notional_today(self) -> float:
        """Cumulative admitted notional for the current day (0.0 before any)."""
        return self._notional

    @property
    def trading_off(self) -> bool:
        """Whether the manual TRADING_OFF kill switch is currently engaged."""
        return self.off_flag.exists()
