"""Tests for ``gtc_catastrophe_planner`` (#108 G1) — the catastrophe-stop plan.

Hermetic: every case builds its own in-memory holdings / live_state dict (or a
tmp file), so the suite never touches the live ``RenQuant`` state tree or a
broker. The two ``__main__`` proof obligations of the prototype are pinned as
proper cases:

  * every PLACE carries a strictly positive ``stop_price`` (sizing fail-closed);
  * re-planning after the plan is applied yields no new PLACE (idempotency).

Plus: REPLACE only on real drift, CANCEL on closed positions, sorted/stable
output, and the live_state extraction + file loader.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.gtc_catastrophe_planner import (
    CATASTROPHE_DD,
    catastrophe_stop_price,
    holdings_from_live_state,
    plan,
    plan_from_live_state,
    plan_from_live_state_file,
    stops_from_live_state,
)


def _apply(plan_actions: list[dict], existing_stops: dict) -> dict:
    """Fold a plan's PLACE/REPLACE/CANCEL actions onto the broker stop book."""
    book = dict(existing_stops)
    for a in plan_actions:
        if a["action"] == "PLACE":
            book[a["ticker"]] = a["stop_price"]
        elif a["action"] == "REPLACE":
            book[a["ticker"]] = a["to"]
        elif a["action"] == "CANCEL":
            book.pop(a["ticker"], None)
    return book


# --- price ---------------------------------------------------------------

def test_catastrophe_stop_price_is_20pct_below_entry():
    assert catastrophe_stop_price(100.0) == 80.0
    assert CATASTROPHE_DD == 0.20


def test_catastrophe_stop_price_rounds_to_cents():
    # 33.333 * 0.8 = 26.6664 -> 26.67
    assert catastrophe_stop_price(33.333) == 26.67


def test_custom_drawdown_is_honoured():
    assert catastrophe_stop_price(100.0, catastrophe_dd=0.10) == 90.0


# --- PLACE ---------------------------------------------------------------

def test_place_for_holding_with_no_existing_stop():
    p = plan({"AAPL": {"entry_price": 100.0, "shares": 7}}, {})
    assert p == [{
        "action": "PLACE", "ticker": "AAPL", "type": "stop", "tif": "gtc",
        "stop_price": 80.0, "qty": 7,
    }]


def test_every_place_has_strictly_positive_stop_price():
    """Prototype invariant #1: a PLACE never submits a non-positive stop."""
    holdings = {f"T{i}": {"entry_price": price, "shares": 1}
                for i, price in enumerate([0.05, 1.0, 12.34, 999.99])}
    p = plan(holdings, {})
    places = [a for a in p if a["action"] == "PLACE"]
    assert len(places) == len(holdings)
    assert all(a["stop_price"] > 0 for a in places)


# --- REPLACE (tolerance band) -------------------------------------------

def test_no_replace_when_existing_stop_is_within_tolerance():
    # want = 80.0; 80.4 drifts 0.5% < 1% -> leave it alone (no churn).
    p = plan({"AAPL": {"entry_price": 100.0, "shares": 1}}, {"AAPL": 80.4})
    assert p == []


def test_replace_when_existing_stop_drifts_beyond_tolerance():
    # want = 80.0; 70.0 drifts 12.5% > 1% -> REPLACE.
    p = plan({"AAPL": {"entry_price": 100.0, "shares": 1}}, {"AAPL": 70.0})
    assert p == [{"action": "REPLACE", "ticker": "AAPL", "from": 70.0, "to": 80.0}]


def test_tolerance_is_configurable():
    # 70.0 vs want 80.0 = 12.5% drift; a 20% tolerance suppresses the REPLACE.
    p = plan({"AAPL": {"entry_price": 100.0, "shares": 1}}, {"AAPL": 70.0},
             tolerance=0.20)
    assert p == []


# --- CANCEL --------------------------------------------------------------

def test_cancel_stop_for_closed_position():
    p = plan({}, {"AAPL": 80.0})
    assert p == [{"action": "CANCEL", "ticker": "AAPL", "reason": "position closed"}]


def test_mixed_place_replace_cancel_sorted():
    holdings = {
        "MSFT": {"entry_price": 200.0, "shares": 1},   # no stop -> PLACE
        "AAPL": {"entry_price": 100.0, "shares": 1},   # drifted -> REPLACE
    }
    existing = {"AAPL": 70.0, "GOOG": 50.0}            # GOOG not held -> CANCEL
    p = plan(holdings, existing)
    # holdings handled in sorted order (AAPL, MSFT), then cancels (GOOG).
    assert [a["action"] for a in p] == ["REPLACE", "PLACE", "CANCEL"]
    assert [a["ticker"] for a in p] == ["AAPL", "MSFT", "GOOG"]


# --- idempotency (prototype invariant #2) --------------------------------

def test_replanning_after_apply_yields_no_new_place():
    holdings = {
        "AAPL": {"entry_price": 100.0, "shares": 1},
        "MSFT": {"entry_price": 200.0, "shares": 3},
    }
    existing: dict = {}
    first = plan(holdings, existing)
    book = _apply(first, existing)
    again = plan(holdings, book)
    assert [a for a in again if a["action"] == "PLACE"] == []
    assert again == []  # fully converged: no churn on a stable book


def test_plan_is_order_independent():
    holdings = {
        "MSFT": {"entry_price": 200.0, "shares": 1},
        "AAPL": {"entry_price": 100.0, "shares": 1},
        "ZZZZ": {"entry_price": 10.0, "shares": 1},
    }
    reordered = {k: holdings[k] for k in ("ZZZZ", "AAPL", "MSFT")}
    assert plan(holdings, {}) == plan(reordered, {})


# --- live_state extraction ----------------------------------------------

def _live_state() -> dict:
    return {
        "entry_dates": {"AAPL": "2026-06-01", "MSFT": "2026-06-02",
                        "NOHWM": "2026-06-03"},
        "position_hwm": {"AAPL": 150.0, "MSFT": 300.0},  # NOHWM absent
        "stop_orders": {
            "AAPL": {"stop_price": 120.0},
            "GOOG": {"stop_price": 40.0},                # closed position
            "BAD": {"note": "no stop_price key"},        # ignored
        },
    }


def test_holdings_from_live_state_uses_hwm_and_skips_unanchored():
    holdings = holdings_from_live_state(_live_state())
    assert set(holdings) == {"AAPL", "MSFT"}             # NOHWM dropped
    assert holdings["AAPL"] == {"entry_price": 150.0, "shares": 1}


def test_stops_from_live_state_only_keeps_priced_orders():
    stops = stops_from_live_state(_live_state())
    assert stops == {"AAPL": 120.0, "GOOG": 40.0}        # BAD dropped


def test_plan_from_live_state_end_to_end():
    p = plan_from_live_state(_live_state())
    by_ticker = {a["ticker"]: a for a in p}
    # AAPL: want 120.0 == existing 120.0 -> no action.
    assert "AAPL" not in by_ticker
    # MSFT: no stop -> PLACE at 300*0.8 = 240.0.
    assert by_ticker["MSFT"] == {
        "action": "PLACE", "ticker": "MSFT", "type": "stop", "tif": "gtc",
        "stop_price": 240.0, "qty": 1,
    }
    # GOOG: held no longer -> CANCEL.
    assert by_ticker["GOOG"]["action"] == "CANCEL"


def test_plan_from_live_state_file(tmp_path: Path):
    f = tmp_path / "live_state.alpaca.json"
    f.write_text(json.dumps(_live_state()))
    assert plan_from_live_state_file(f) == plan_from_live_state(_live_state())


def test_empty_live_state_yields_empty_plan():
    assert plan_from_live_state({}) == []


def test_division_safe_on_zero_priced_existing_handled_via_want():
    # want is derived from entry (always > 0 for a real holding), so the
    # tolerance division denominator is never zero.
    p = plan({"AAPL": {"entry_price": 50.0, "shares": 1}}, {"AAPL": 0.0})
    assert p == [{"action": "REPLACE", "ticker": "AAPL", "from": 0.0, "to": 40.0}]


@pytest.mark.parametrize("entry", [1.0, 7.5, 123.45, 9999.99])
def test_place_then_replan_converges_for_arbitrary_entries(entry):
    holdings = {"X": {"entry_price": entry, "shares": 1}}
    first = plan(holdings, {})
    book = _apply(first, {})
    assert plan(holdings, book) == []
