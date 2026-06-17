"""Tests for ``agent_breaker`` (#108 Week-0 disaster guard).

The four proof obligations the G2 prototype asserted in its ``__main__`` are
pinned here as hermetic cases (``tmp_path`` for the kill-switch flag, in-memory
counters, no sibling repos and no live paths):

  * P1 — a runaway loop is bounded by ``max_orders_per_day``;
  * P2 — cumulative admitted notional never exceeds ``max_notional_per_day``;
  * P3 — a new day resets both counters;
  * P4 — the TRADING_OFF flag dominates everything.

Boundary cases, the count-only-on-success contract, and constructor validation
round out the suite. A seeded randomized trial re-proves P1+P2 jointly.
"""
from __future__ import annotations

import datetime as dt
import random

import pytest

from renquant_orchestrator.agent_breaker import (
    AgentBreaker,
    BreakerTripped,
)

DAY = dt.date(2026, 6, 12)
NEXT_DAY = dt.date(2026, 6, 13)


def _absent_flag(tmp_path):
    """A flag path guaranteed not to exist (hermetic, per-test tmp dir)."""
    return tmp_path / "TRADING_OFF_absent"


# --------------------------------------------------------------------------- P1
def test_p1_runaway_loop_is_bounded_by_order_cap(tmp_path):
    b = AgentBreaker(max_orders_per_day=25, max_notional_per_day=1e12,
                     off_flag=_absent_flag(tmp_path))
    rng = random.Random(11)
    ok = 0
    for _ in range(10_000):
        try:
            b.admit(today=DAY, notional=rng.uniform(1, 300))
            ok += 1
        except BreakerTripped:
            pass
    assert ok == 25
    assert b.orders_today == 25


def test_order_cap_boundary_is_inclusive(tmp_path):
    b = AgentBreaker(max_orders_per_day=3, max_notional_per_day=1e9,
                     off_flag=_absent_flag(tmp_path))
    for _ in range(3):
        b.admit(today=DAY, notional=1.0)  # 3 admits succeed
    with pytest.raises(BreakerTripped, match="order cap 3"):
        b.admit(today=DAY, notional=1.0)  # the 4th trips


# --------------------------------------------------------------------------- P2
def test_p2_notional_cap_binds_under_tiny_order_counts(tmp_path):
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=5_000,
                     off_flag=_absent_flag(tmp_path))
    tot = 0.0
    for _ in range(10_000):
        try:
            b.admit(today=DAY, notional=400)
            tot += 400
        except BreakerTripped:
            break
    assert tot <= 5_000
    assert b.notional_today <= 5_000


def test_notional_cap_boundary_exact_fill_then_trip(tmp_path):
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=1_000,
                     off_flag=_absent_flag(tmp_path))
    b.admit(today=DAY, notional=600)
    b.admit(today=DAY, notional=400)  # fills to exactly 1000 — allowed
    assert b.notional_today == 1_000
    with pytest.raises(BreakerTripped, match="notional cap"):
        b.admit(today=DAY, notional=1)  # any further notional trips


def test_notional_uses_absolute_value(tmp_path):
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=1_000,
                     off_flag=_absent_flag(tmp_path))
    b.admit(today=DAY, notional=-600)
    b.admit(today=DAY, notional=-400)
    assert b.notional_today == 1_000
    with pytest.raises(BreakerTripped):
        b.admit(today=DAY, notional=-1)


# --------------------------------------------------------------------------- P3
def test_p3_day_roll_resets_both_counters(tmp_path):
    b = AgentBreaker(max_orders_per_day=2, max_notional_per_day=100,
                     off_flag=_absent_flag(tmp_path))
    b.admit(today=DAY, notional=50)
    b.admit(today=DAY, notional=50)
    with pytest.raises(BreakerTripped):
        b.admit(today=DAY, notional=1)  # day is full
    # New day -> fresh budget.
    b.admit(today=NEXT_DAY, notional=50)
    assert b.orders_today == 1
    assert b.notional_today == 50


# --------------------------------------------------------------------------- P4
def test_p4_trading_off_flag_dominates_everything(tmp_path):
    flag = tmp_path / "TRADING_OFF"
    flag.touch()
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=1e9,
                     off_flag=flag)
    # Headroom on both counters, yet the very first admit is refused.
    with pytest.raises(BreakerTripped, match="TRADING_OFF"):
        b.admit(today=DAY, notional=1)
    assert b.trading_off is True


def test_trading_off_is_rechecked_every_admit(tmp_path):
    flag = tmp_path / "TRADING_OFF"
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=1e9,
                     off_flag=flag)
    b.admit(today=DAY, notional=1)        # flag absent -> allowed
    assert b.trading_off is False
    flag.touch()                          # operator flips the kill switch
    with pytest.raises(BreakerTripped, match="TRADING_OFF"):
        b.admit(today=DAY, notional=1)
    flag.unlink()                         # operator clears it
    b.admit(today=DAY, notional=1)        # allowed again
    assert b.orders_today == 2            # the refused admit consumed nothing


# ------------------------------------------------------- count-only-on-success
def test_rejected_admit_consumes_no_budget(tmp_path):
    b = AgentBreaker(max_orders_per_day=1000, max_notional_per_day=100,
                     off_flag=_absent_flag(tmp_path))
    b.admit(today=DAY, notional=90)
    for _ in range(50):
        with pytest.raises(BreakerTripped):
            b.admit(today=DAY, notional=50)  # each over-cap attempt is refused
    # None of the refused attempts ate budget; the 10 of headroom remains.
    assert b.notional_today == 90
    assert b.orders_today == 1
    b.admit(today=DAY, notional=10)          # fits in the preserved headroom
    assert b.notional_today == 100


# ------------------------------------------------------------- initial state
def test_initial_counters_are_zero(tmp_path):
    b = AgentBreaker(off_flag=_absent_flag(tmp_path))
    assert b.orders_today == 0
    assert b.notional_today == 0.0
    assert b.trading_off is False


# ------------------------------------------------------- constructor validation
@pytest.mark.parametrize("orders", [0, -1, -25])
def test_non_positive_order_cap_rejected(orders, tmp_path):
    with pytest.raises(ValueError, match="max_orders_per_day"):
        AgentBreaker(max_orders_per_day=orders, off_flag=_absent_flag(tmp_path))


@pytest.mark.parametrize("notional", [0, -1.0, -5_000])
def test_non_positive_notional_cap_rejected(notional, tmp_path):
    with pytest.raises(ValueError, match="max_notional_per_day"):
        AgentBreaker(max_notional_per_day=notional, off_flag=_absent_flag(tmp_path))


# ------------------------------------------------ joint property (P1 + P2), seeded
def test_caps_jointly_bound_admissions_over_randomized_trials(tmp_path):
    rng = random.Random(7)
    for trial in range(500):
        max_orders = rng.randint(1, 40)
        max_notional = rng.uniform(100, 10_000)
        b = AgentBreaker(max_orders_per_day=max_orders,
                         max_notional_per_day=max_notional,
                         off_flag=_absent_flag(tmp_path / f"t{trial}"))
        admitted = 0
        notional = 0.0
        for _ in range(2_000):
            amt = rng.uniform(0.5, max_notional)
            try:
                b.admit(today=DAY, notional=amt)
                admitted += 1
                notional += amt
            except BreakerTripped:
                pass
        # P1: never more than the order cap.
        assert admitted <= max_orders
        # P2: never more than the notional cap (allowing fp slack).
        assert notional <= max_notional + 1e-9
        assert b.orders_today == admitted
        assert b.notional_today == pytest.approx(notional)
