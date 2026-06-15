"""Tests for ``live_state_v2`` (#108 S1) — typed live state + lossless migration.

Hermetic: a representative v1 fixture mirrors the real
``live_state.alpaca.json`` shape (incl. sparse per-holding dicts and unmodelled
operational keys), so the suite never reads the live file.

Pins:
- parse() builds typed holdings from the flat v1 dicts
- **lossless** round-trip: to_v1_dict(parse(v1)) == v1 (the safety property)
- unmodelled keys (monitor_state/regime_state/stop_orders/recent_sell_orders)
  are quarantined and re-emitted verbatim — never dropped
- entry_signal preserved in full (rank_score/panel_score/kelly_target_pct)
- entry_regime is derived from entry_signal
- a per-holding entry with no entry_date fails loud (no silent loss)
- extra="forbid" rejects unknown holding fields
- canonical round-trip
"""
from __future__ import annotations

import copy

import pytest

from renquant_orchestrator.live_state_v2 import HoldingV2, LiveStateV2


def _v1_fixture() -> dict:
    """Mirrors the real live_state.alpaca.json shape (2 holdings: MU, EQIX)."""
    return {
        "regime": "BULL_CALM",
        "regime_confidence": 0.734,
        "high_water_mark": 11079.22,
        "skip_buys": False,
        "entry_dates": {"MU": "2026-04-27", "EQIX": "2026-05-17"},
        "sell_streaks": {"MU": 0, "EQIX": 1},
        "protection_breaches": {"MU": 0, "EQIX": 2},
        "position_hwm": {"MU": 1094.495, "EQIX": 980.1},
        "entry_signals": {
            "MU": {"rank_score": 0.32513821903305495, "panel_score": None,
                   "kelly_target_pct": None},
            "EQIX": {"rank_score": 0.11, "panel_score": 0.4,
                     "kelly_target_pct": 0.05, "regime": "BULL_CALM"},
        },
        "last_sell_dates": {"GE": "2026-06-15", "BA": "2026-06-01", "F": "2026-05-20"},
        "last_stop_exit_dates": {"BA": "2026-05-15", "MU": "2026-03-02"},
        # unmodelled operational keys -> must be quarantined + re-emitted
        "monitor_state": {"no_trade_streak": 2, "last_run": "2026-06-15"},
        "regime_state": {"regime": "BULL_CALM", "confidence": 0.734},
        "stop_orders": {},
        "recent_sell_orders": {},
    }


def test_parse_builds_typed_holdings():
    s = LiveStateV2.parse(_v1_fixture())
    assert set(s.holdings) == {"MU", "EQIX"}
    assert s.holdings["MU"].entry_date == "2026-04-27"
    assert s.holdings["EQIX"].sell_streak == 1
    assert s.holdings["EQIX"].protection_breaches == 2
    assert s.holdings["MU"].position_hwm == 1094.495
    assert s.regime == "BULL_CALM"
    assert s.high_water_mark == 11079.22


def test_lossless_round_trip():
    """The safety property that lets the runner adopt v2: v1 -> v2 -> v1 is
    byte-identical (modulo key order)."""
    v1 = _v1_fixture()
    rebuilt = LiveStateV2.parse(v1).to_v1_dict()
    assert rebuilt == v1


def test_unmodelled_keys_quarantined_and_reemitted():
    s = LiveStateV2.parse(_v1_fixture())
    assert set(s.extra_quarantine) == {
        "monitor_state", "regime_state", "stop_orders", "recent_sell_orders"}
    out = s.to_v1_dict()
    assert out["monitor_state"] == {"no_trade_streak": 2, "last_run": "2026-06-15"}
    assert out["regime_state"]["confidence"] == 0.734


def test_entry_signal_preserved_in_full():
    s = LiveStateV2.parse(_v1_fixture())
    sig = s.holdings["MU"].entry_signal
    assert sig == {"rank_score": 0.32513821903305495, "panel_score": None,
                   "kelly_target_pct": None}


def test_entry_regime_derived():
    s = LiveStateV2.parse(_v1_fixture())
    assert s.holdings["EQIX"].entry_regime == "BULL_CALM"  # carried in signal
    assert s.holdings["MU"].entry_regime is None           # absent -> None


def test_orphan_per_holding_entry_fails_loud():
    v1 = _v1_fixture()
    v1["sell_streaks"]["ZZZZ"] = 3  # ticker with no entry_date
    with pytest.raises(ValueError, match="no entry_date"):
        LiveStateV2.parse(v1)


def test_unknown_holding_field_forbidden():
    with pytest.raises(Exception):  # pydantic ValidationError (extra=forbid)
        HoldingV2(entry_date="2026-01-01", bogus_field=1)


def test_one_line_field_add_is_live():
    """protection_breaches is the worked example of the 1-line per-holding add."""
    s = LiveStateV2.parse(_v1_fixture())
    assert s.holdings["EQIX"].protection_breaches == 2
    # field flows back out to v1 unchanged
    assert s.to_v1_dict()["protection_breaches"] == {"MU": 0, "EQIX": 2}


def test_canonical_round_trip():
    import json
    s = LiveStateV2.parse(_v1_fixture())
    again = LiveStateV2(**json.loads(s.canonical_json()))
    assert again == s


def test_minimal_state_parses():
    s = LiveStateV2.parse({"regime": "UNKNOWN"})
    assert s.holdings == {}
    assert s.to_v1_dict()["entry_dates"] == {}


def test_round_trip_does_not_mutate_input():
    v1 = _v1_fixture()
    snapshot = copy.deepcopy(v1)
    LiveStateV2.parse(v1).to_v1_dict()
    assert v1 == snapshot
