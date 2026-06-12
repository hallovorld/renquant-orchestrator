#!/usr/bin/env python3
"""G2 agent-breaker prototype (#108 Week-0 disaster guard).

Adapter-level, BELOW all pipeline logic: hard daily order-count cap, daily
notional cap, and a manual TRADING_OFF file. A runaway agent/pipeline loop
cannot exceed these no matter what upstream decides. Pure logic + property
tests; the production wiring goes into the broker adapter as S0-PR-G2.
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path


class BreakerTripped(Exception):
    pass


class AgentBreaker:
    def __init__(self, *, max_orders_per_day: int = 25,
                 max_notional_per_day: float = 5_000.0,
                 off_flag: Path = Path("/tmp/TRADING_OFF")):
        self.max_orders = max_orders_per_day
        self.max_notional = max_notional_per_day
        self.off_flag = off_flag
        self._day: dt.date | None = None
        self._orders = 0
        self._notional = 0.0

    def _roll(self, today: dt.date):
        if self._day != today:
            self._day, self._orders, self._notional = today, 0, 0.0

    def admit(self, *, today: dt.date, notional: float) -> None:
        """Call ONCE per order, immediately before broker submission.
        Raises BreakerTripped — caller must NOT retry-loop."""
        if self.off_flag.exists():
            raise BreakerTripped(f"manual TRADING_OFF present: {self.off_flag}")
        self._roll(today)
        if self._orders + 1 > self.max_orders:
            raise BreakerTripped(f"daily order cap {self.max_orders} reached")
        if self._notional + abs(notional) > self.max_notional:
            raise BreakerTripped(
                f"daily notional cap {self.max_notional} would be exceeded "
                f"({self._notional:.0f}+{abs(notional):.0f})")
        self._orders += 1
        self._notional += abs(notional)


if __name__ == "__main__":
    random.seed(11)
    # P1: runaway loop is bounded — admit() can never succeed more than cap times/day
    b = AgentBreaker(max_orders_per_day=25, max_notional_per_day=5_000,
                     off_flag=Path("/tmp/_no_such_flag_"))
    today = dt.date(2026, 6, 12)
    ok = 0
    for _ in range(10_000):
        try:
            b.admit(today=today, notional=random.uniform(1, 300))
            ok += 1
        except BreakerTripped:
            pass
    assert ok <= 25, ok
    # P2: notional cap binds even under tiny order counts
    b2 = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=5_000,
                      off_flag=Path("/tmp/_no_such_flag_"))
    tot = 0.0
    for _ in range(10_000):
        try:
            b2.admit(today=today, notional=400)
            tot += 400
        except BreakerTripped:
            break
    assert tot <= 5_000, tot
    # P3: day roll resets; P4: TRADING_OFF dominates everything
    b.admit(today=dt.date(2026, 6, 13), notional=10)
    flag = Path("/tmp/_trading_off_test_")
    flag.touch()
    b3 = AgentBreaker(off_flag=flag)
    try:
        b3.admit(today=today, notional=1)
        raise SystemExit("P4 FAILED")
    except BreakerTripped:
        pass
    finally:
        flag.unlink()
    print(f"P1 runaway bounded at {ok}/10000 attempts; P2 notional bound {tot:.0f}<=5000; "
          "P3 day-roll OK; P4 TRADING_OFF dominates. ALL PROOFS PASS")
