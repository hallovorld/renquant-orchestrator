"""Tests for the attribution decomposition identity (107 sprint D3).

The decomposition is a pure arithmetic identity over per-decision records;
tests verify the sum-check, censoring discipline, and edge cases without
touching a database.
"""
from __future__ import annotations

import math

import pytest

from renquant_orchestrator.attribution.decompose import (
    CENSOR_ENTRY_FILL,
    CENSOR_EXIT_FILL,
    CENSOR_NO_BENCH,
    CENSOR_NO_INTENDED,
    CENSOR_NO_REF_ENTRY,
    CENSOR_NO_REF_EXIT,
    CENSOR_SHARES_CONFLICT,
    CENSOR_UNMATCHED_EXIT,
    LEG_NAMES,
    SUM_CHECK_ABS_TOL,
    assert_identity,
    decompose_round_trip,
)


def _make_rec(**overrides) -> dict:
    """A fully populated closed round-trip record."""
    base = {
        "decision_id": "test-001",
        "date": "2026-06-01",
        "exit_date": "2026-06-15",
        "ticker": "AAPL",
        "status": "closed",
        "regime": "BULL_CALM",
        "run_type": "live",
        "mu": 0.05,
        "rank_score": 0.8,
        "blocked_by": None,
        "exit_reason": "panel_exit",
        "shares": 10,
        "entry_px": 200.0,
        "exit_px": 210.0,
        "ref_entry_px": 199.0,
        "ref_exit_px": 209.0,
        "spy_entry_px": 550.0,
        "spy_exit_px": 555.0,
        "entry_fill_confirmed": True,
        "exit_fill_confirmed": True,
        "intended_notional": 2000.0,
        "realized_notional": 2000.0,
        "fees": 0.0,
    }
    base.update(overrides)
    return base


class TestFullyPopulatedRecord:
    """With all inputs present the identity must hold exactly."""

    def test_all_legs_present(self):
        result = decompose_round_trip(_make_rec())
        for name in LEG_NAMES:
            assert result["legs"][name] is not None, f"{name} is None"
        assert result["censored"] == {}

    def test_sum_check_ok(self):
        result = decompose_round_trip(_make_rec())
        sc = result["sum_check"]
        assert sc is not None
        assert sc["ok"] is True
        assert abs(sc["residual"]) <= SUM_CHECK_ABS_TOL

    def test_total_equals_legs_sum(self):
        result = decompose_round_trip(_make_rec())
        legs_sum = sum(result["legs"][n] for n in LEG_NAMES)
        assert abs(result["total_pnl"] - legs_sum) < 1e-10

    def test_market_leg(self):
        rec = _make_rec()
        result = decompose_round_trip(rec)
        r_spy = rec["spy_exit_px"] / rec["spy_entry_px"] - 1.0
        expected = rec["intended_notional"] * r_spy
        assert abs(result["legs"]["market"] - expected) < 1e-10

    def test_signal_leg(self):
        rec = _make_rec()
        result = decompose_round_trip(rec)
        r_ref = rec["ref_exit_px"] / rec["ref_entry_px"] - 1.0
        r_spy = rec["spy_exit_px"] / rec["spy_entry_px"] - 1.0
        expected = rec["intended_notional"] * (r_ref - r_spy)
        assert abs(result["legs"]["signal"] - expected) < 1e-10

    def test_sizing_leg(self):
        rec = _make_rec(intended_notional=1800.0, realized_notional=2000.0)
        result = decompose_round_trip(rec)
        r_ref = rec["ref_exit_px"] / rec["ref_entry_px"] - 1.0
        expected = (2000.0 - 1800.0) * r_ref
        assert abs(result["legs"]["sizing"] - expected) < 1e-10

    def test_timing_leg(self):
        rec = _make_rec()
        result = decompose_round_trip(rec)
        r_real = rec["exit_px"] / rec["entry_px"] - 1.0
        r_ref = rec["ref_exit_px"] / rec["ref_entry_px"] - 1.0
        expected = rec["realized_notional"] * (r_real - r_ref)
        assert abs(result["legs"]["timing"] - expected) < 1e-10

    def test_cost_leg_zero_fees(self):
        result = decompose_round_trip(_make_rec(fees=0.0))
        assert result["legs"]["cost"] == 0.0

    def test_cost_leg_nonzero_fees(self):
        result = decompose_round_trip(_make_rec(fees=2.50))
        assert result["legs"]["cost"] == -2.50

    def test_total_pnl_computed(self):
        rec = _make_rec()
        result = decompose_round_trip(rec)
        r_real = rec["exit_px"] / rec["entry_px"] - 1.0
        expected = rec["realized_notional"] * r_real + result["legs"]["cost"]
        assert abs(result["total_pnl"] - expected) < 1e-10


class TestSpreadProxy:
    """half_spread_bps adds an estimated cost component."""

    def test_spread_added_to_cost(self):
        rec = _make_rec()
        result = decompose_round_trip(rec, half_spread_bps=5.0)
        assert result["legs"]["cost"] < 0
        assert result["diagnostics"]["cost_is_estimate"] is True

    def test_sum_check_still_holds_with_spread(self):
        result = decompose_round_trip(_make_rec(), half_spread_bps=10.0)
        assert result["sum_check"]["ok"] is True


class TestCensoringEntryFill:
    """Unconfirmed entry fills censor legs that need N_r or r_real."""

    def test_unconfirmed_entry_censors_sizing_timing_cost(self):
        rec = _make_rec(entry_fill_confirmed=False)
        result = decompose_round_trip(rec)
        for leg in ("sizing", "timing", "cost"):
            assert result["legs"][leg] is None
            assert leg in result["censored"]
            assert CENSOR_ENTRY_FILL in result["censored"][leg]

    def test_market_signal_survive_unconfirmed_entry(self):
        rec = _make_rec(entry_fill_confirmed=False)
        result = decompose_round_trip(rec)
        assert result["legs"]["market"] is not None
        assert result["legs"]["signal"] is not None


class TestCensoringExitFill:
    """Unconfirmed exit fills on a CLOSED trip censor timing."""

    def test_unconfirmed_exit_censors_timing(self):
        rec = _make_rec(exit_fill_confirmed=False)
        result = decompose_round_trip(rec)
        assert result["legs"]["timing"] is None
        assert "timing" in result["censored"]
        assert CENSOR_EXIT_FILL in result["censored"]["timing"]


class TestCensoringNoIntended:
    """Missing intended_notional censors market, signal, sizing."""

    def test_no_intended_censors_market_signal_sizing(self):
        rec = _make_rec(intended_notional=None)
        result = decompose_round_trip(rec)
        for leg in ("market", "signal", "sizing"):
            assert result["legs"][leg] is None
            assert leg in result["censored"]
            assert CENSOR_NO_INTENDED in result["censored"][leg]


class TestCensoringNoBenchmark:
    """Missing SPY prices censor market and signal."""

    def test_no_spy_entry_censors_market_signal(self):
        rec = _make_rec(spy_entry_px=None)
        result = decompose_round_trip(rec)
        for leg in ("market", "signal"):
            assert result["legs"][leg] is None
            assert CENSOR_NO_BENCH in result["censored"][leg]

    def test_no_spy_exit_censors_market_signal(self):
        rec = _make_rec(spy_exit_px=None)
        result = decompose_round_trip(rec)
        for leg in ("market", "signal"):
            assert result["legs"][leg] is None

    def test_zero_spy_entry_censors_market_signal(self):
        rec = _make_rec(spy_entry_px=0.0)
        result = decompose_round_trip(rec)
        for leg in ("market", "signal"):
            assert result["legs"][leg] is None
            assert CENSOR_NO_BENCH in result["censored"][leg]

    def test_zero_spy_exit_censors_market_signal(self):
        rec = _make_rec(spy_exit_px=0.0)
        result = decompose_round_trip(rec)
        for leg in ("market", "signal"):
            assert result["legs"][leg] is None
            assert CENSOR_NO_BENCH in result["censored"][leg]


class TestCensoringNoReference:
    """Missing reference prices censor signal, sizing, timing."""

    def test_no_ref_entry(self):
        rec = _make_rec(ref_entry_px=None)
        result = decompose_round_trip(rec)
        assert CENSOR_NO_REF_ENTRY in result["censored"]["signal"]
        assert result["legs"]["sizing"] is None
        assert result["legs"]["timing"] is None

    def test_no_ref_exit(self):
        rec = _make_rec(ref_exit_px=None)
        result = decompose_round_trip(rec)
        assert CENSOR_NO_REF_EXIT in result["censored"]["signal"]


class TestSharesConflict:
    """Cross-day re-records with conflicting shares censor N_r-derived legs."""

    def test_shares_conflict_censors(self):
        rec = _make_rec(shares_conflict=True, realized_notional=None)
        result = decompose_round_trip(rec)
        assert result["legs"]["sizing"] is None
        assert CENSOR_SHARES_CONFLICT in result["censored"]["sizing"]


class TestOpenMTM:
    """Open positions use exit_px=ref_exit_px so timing isolates entry."""

    def test_open_position_timing_computable(self):
        rec = _make_rec(
            status="open_mtm",
            exit_fill_confirmed=None,
            exit_px=209.0,
            ref_exit_px=209.0,
        )
        result = decompose_round_trip(rec)
        assert result["legs"]["timing"] is not None

    def test_open_position_sum_check(self):
        rec = _make_rec(
            status="open_mtm",
            exit_fill_confirmed=None,
            exit_px=209.0,
            ref_exit_px=209.0,
        )
        result = decompose_round_trip(rec)
        assert result["sum_check"]["ok"] is True


class TestExitUnmatched:
    """Exit events with no matching entry censor everything."""

    def test_unmatched_exit_all_censored(self):
        rec = _make_rec(status="exit_unmatched")
        result = decompose_round_trip(rec)
        for name in LEG_NAMES:
            assert result["legs"][name] is None
            assert name in result["censored"]
            assert CENSOR_UNMATCHED_EXIT in result["censored"][name]
        assert result["total_pnl"] is None
        assert result["sum_check"] is None


class TestDiagnostics:
    """Diagnostic fields are populated for inspection."""

    def test_diagnostics_present(self):
        result = decompose_round_trip(_make_rec())
        d = result["diagnostics"]
        assert d["r_ref"] is not None
        assert d["r_spy"] is not None
        assert d["r_real"] is not None
        assert d["intended_notional"] is not None
        assert d["realized_notional"] is not None

    def test_entry_slippage_bps(self):
        rec = _make_rec(entry_px=200.0, ref_entry_px=199.0)
        result = decompose_round_trip(rec)
        expected_bps = (200.0 / 199.0 - 1.0) * 1e4
        assert abs(result["diagnostics"]["entry_slippage_bps"] - expected_bps) < 0.01

    def test_no_slippage_when_entry_unconfirmed(self):
        rec = _make_rec(entry_fill_confirmed=False)
        result = decompose_round_trip(rec)
        assert result["diagnostics"]["entry_slippage_bps"] is None


class TestAssertIdentity:
    """assert_identity raises on residual violations."""

    def test_clean_records_pass(self):
        results = [decompose_round_trip(_make_rec())]
        assert_identity(results)

    def test_violated_identity_raises(self):
        result = decompose_round_trip(_make_rec())
        result["sum_check"]["ok"] = False
        result["sum_check"]["residual"] = 1.0
        with pytest.raises(AssertionError, match="identity violated"):
            assert_identity([result])

    def test_censored_records_skipped(self):
        rec = _make_rec(entry_fill_confirmed=False)
        result = decompose_round_trip(rec)
        assert result["sum_check"] is None
        assert_identity([result])


class TestOutputShape:
    """The result dict carries expected top-level keys."""

    def test_result_keys(self):
        result = decompose_round_trip(_make_rec())
        expected_keys = {
            "decision_id", "date", "exit_date", "ticker", "status",
            "regime", "run_type", "mu", "rank_score", "blocked_by",
            "exit_reason", "legs", "censored", "total_pnl", "sum_check",
            "diagnostics",
        }
        assert expected_keys == set(result.keys())

    def test_leg_names_constant(self):
        assert LEG_NAMES == ("market", "signal", "sizing", "timing", "cost")


class TestEdgeCases:
    """Boundary conditions and numerical edge cases."""

    def test_zero_entry_price_censors_r_real(self):
        rec = _make_rec(entry_px=0.0)
        result = decompose_round_trip(rec)
        assert result["diagnostics"]["r_real"] is None

    def test_zero_ref_entry_censors_r_ref(self):
        rec = _make_rec(ref_entry_px=0.0)
        result = decompose_round_trip(rec)
        assert result["diagnostics"]["r_ref"] is None

    def test_identical_prices_zero_legs(self):
        rec = _make_rec(
            entry_px=200.0, exit_px=200.0,
            ref_entry_px=200.0, ref_exit_px=200.0,
            spy_entry_px=550.0, spy_exit_px=550.0,
        )
        result = decompose_round_trip(rec)
        for name in LEG_NAMES:
            assert result["legs"][name] == 0.0
        assert result["sum_check"]["ok"] is True

    def test_large_gain_identity_holds(self):
        rec = _make_rec(
            entry_px=100.0, exit_px=200.0,
            ref_entry_px=100.0, ref_exit_px=200.0,
            spy_entry_px=500.0, spy_exit_px=510.0,
            intended_notional=10000.0,
            realized_notional=10000.0,
        )
        result = decompose_round_trip(rec)
        assert result["sum_check"]["ok"] is True

    def test_negative_return_identity_holds(self):
        rec = _make_rec(
            entry_px=200.0, exit_px=180.0,
            ref_entry_px=199.0, ref_exit_px=179.0,
            spy_entry_px=550.0, spy_exit_px=540.0,
        )
        result = decompose_round_trip(rec)
        assert result["sum_check"]["ok"] is True
        assert result["total_pnl"] < 0
