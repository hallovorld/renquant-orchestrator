"""Tests for risk_budget.attribution_bridge — pure functions + mocked orchestration.

Groups:
1. _in_window — date-interval intersection (entry/exit vs [start, end]).
2. _aggregate — leg summation, censoring propagation, ranking, dd_consumers.
3. leg_dd_consumption — orchestration with mocked decomposed_results.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from renquant_orchestrator.risk_budget import attribution_bridge as ab

LEG_NAMES = ab.LEG_NAMES


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_result(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "decision_id": "test-001",
        "date": "2026-06-15",
        "exit_date": "2026-06-20",
        "ticker": "AAPL",
        "status": "closed",
        "regime": "BULL_CALM",
        "legs": {"market": 10.0, "signal": 5.0, "sizing": -2.0, "timing": -3.0, "cost": -1.0},
        "censored": {},
        "total_pnl": 9.0,
        "sum_check": {"total": 9.0, "legs_sum": 9.0, "residual": 0.0, "ok": True},
    }
    base.update(overrides)
    return base


# ===================================================================
# 1. _in_window
# ===================================================================

class TestInWindow:
    """Interval intersection: holding span [entry, exit] vs DD window [start, end]."""

    def test_closed_position_fully_inside_window(self):
        r = _make_result(date="2026-06-15", exit_date="2026-06-20")
        assert ab._in_window(r, "2026-06-10", "2026-06-25") is True

    def test_entry_before_window_exit_inside(self):
        r = _make_result(date="2026-06-01", exit_date="2026-06-15")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_entry_inside_window_exit_after(self):
        r = _make_result(date="2026-06-15", exit_date="2026-06-25")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_entry_after_window_end_is_excluded(self):
        r = _make_result(date="2026-06-26", exit_date="2026-06-30")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is False

    def test_entry_and_exit_both_before_window(self):
        r = _make_result(date="2026-06-01", exit_date="2026-06-05")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is False

    def test_open_position_entry_before_window_end(self):
        """Open position (exit_date=None) with entry before window end always intersects."""
        r = _make_result(date="2026-06-15", exit_date=None)
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_open_position_entry_on_window_end(self):
        """Edge case: entry exactly on window end, still open."""
        r = _make_result(date="2026-06-20", exit_date=None)
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_open_position_entry_after_window_end(self):
        r = _make_result(date="2026-06-25", exit_date=None)
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is False

    def test_entry_on_boundary_start(self):
        """Entry exactly on window start, exit inside."""
        r = _make_result(date="2026-06-10", exit_date="2026-06-15")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_exit_on_boundary_start(self):
        """Exit exactly on window start — still intersects."""
        r = _make_result(date="2026-06-01", exit_date="2026-06-10")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_exit_one_day_before_window_start(self):
        """Exit strictly before window start — no intersection."""
        r = _make_result(date="2026-06-01", exit_date="2026-06-09")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is False

    def test_entry_on_boundary_end(self):
        """Entry exactly on window end — included (entry <= end)."""
        r = _make_result(date="2026-06-20", exit_date="2026-06-25")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is True

    def test_missing_entry_date_is_excluded(self):
        r = _make_result(date=None, exit_date="2026-06-20")
        assert ab._in_window(r, "2026-06-10", "2026-06-20") is False


# ===================================================================
# 2. _aggregate
# ===================================================================

class TestAggregate:
    """Leg summation, censoring, ranking, dd_consumers."""

    def test_empty_list(self):
        out = ab._aggregate([])
        assert out["n_records"] == 0
        assert out["n_decomposed"] == 0
        assert out["total_pnl_decomposed"] == 0.0
        assert all(out["leg_totals"][leg] == 0.0 for leg in LEG_NAMES)
        assert all(out["leg_n"][leg] == 0 for leg in LEG_NAMES)
        assert out["dd_consumers"] == []
        assert len(out["ranking"]) == len(LEG_NAMES)

    def test_single_fully_decomposed(self):
        r = _make_result()
        out = ab._aggregate([r])
        assert out["n_records"] == 1
        assert out["n_decomposed"] == 1
        assert out["total_pnl_decomposed"] == pytest.approx(9.0)
        assert out["leg_totals"]["market"] == pytest.approx(10.0)
        assert out["leg_totals"]["signal"] == pytest.approx(5.0)
        assert out["leg_totals"]["sizing"] == pytest.approx(-2.0)
        assert out["leg_totals"]["timing"] == pytest.approx(-3.0)
        assert out["leg_totals"]["cost"] == pytest.approx(-1.0)
        assert all(out["leg_n"][leg] == 1 for leg in LEG_NAMES)
        # No censoring
        assert all(out["leg_censored"][leg] == {} for leg in LEG_NAMES)

    def test_dd_consumers_are_negative_totals(self):
        r = _make_result()
        out = ab._aggregate([r])
        consumers = out["dd_consumers"]
        assert all(row["total"] < 0 for row in consumers)
        consumer_legs = {row["leg"] for row in consumers}
        assert consumer_legs == {"sizing", "timing", "cost"}

    def test_ranking_sorted_ascending(self):
        r = _make_result()
        out = ab._aggregate([r])
        totals = [row["total"] for row in out["ranking"]]
        assert totals == sorted(totals)

    def test_multiple_results_sum(self):
        r1 = _make_result(
            decision_id="d-001",
            legs={"market": 10.0, "signal": 5.0, "sizing": -2.0, "timing": -3.0, "cost": -1.0},
            total_pnl=9.0,
        )
        r2 = _make_result(
            decision_id="d-002",
            legs={"market": -4.0, "signal": 2.0, "sizing": 1.0, "timing": -1.0, "cost": -0.5},
            total_pnl=-2.5,
        )
        out = ab._aggregate([r1, r2])
        assert out["n_records"] == 2
        assert out["n_decomposed"] == 2
        assert out["total_pnl_decomposed"] == pytest.approx(6.5)
        assert out["leg_totals"]["market"] == pytest.approx(6.0)
        assert out["leg_totals"]["signal"] == pytest.approx(7.0)
        assert out["leg_totals"]["sizing"] == pytest.approx(-1.0)
        assert out["leg_totals"]["timing"] == pytest.approx(-4.0)
        assert out["leg_totals"]["cost"] == pytest.approx(-1.5)

    def test_censored_legs_excluded_from_totals(self):
        """None-valued legs are NOT summed; the censored reason is counted."""
        r = _make_result(
            legs={"market": 10.0, "signal": 5.0, "sizing": -2.0, "timing": None, "cost": None},
            censored={"timing": "entry_fill_unconfirmed(no_fill)", "cost": "entry_fill_unconfirmed(no_fill)"},
            total_pnl=None,
        )
        out = ab._aggregate([r])
        assert out["n_decomposed"] == 0  # total_pnl is None
        assert out["leg_totals"]["timing"] == pytest.approx(0.0)
        assert out["leg_totals"]["cost"] == pytest.approx(0.0)
        assert out["leg_n"]["timing"] == 0
        assert out["leg_n"]["cost"] == 0
        # Censoring recorded
        assert out["leg_censored"]["timing"] == {"entry_fill_unconfirmed(no_fill)": 1}
        assert out["leg_censored"]["cost"] == {"entry_fill_unconfirmed(no_fill)": 1}
        # Market/signal/sizing still counted
        assert out["leg_n"]["market"] == 1
        assert out["leg_n"]["signal"] == 1
        assert out["leg_n"]["sizing"] == 1

    def test_absent_leg_without_censored_reason_defaults_to_absent(self):
        """If a leg value is None and censored dict has no reason, 'absent' is used."""
        r = _make_result(
            legs={"market": 10.0, "signal": 5.0, "sizing": None, "timing": None, "cost": None},
            censored={},  # No reasons provided
            total_pnl=None,
        )
        out = ab._aggregate([r])
        assert out["leg_censored"]["sizing"] == {"absent": 1}
        assert out["leg_censored"]["timing"] == {"absent": 1}
        assert out["leg_censored"]["cost"] == {"absent": 1}

    def test_mixed_censoring_reasons_counted_separately(self):
        r1 = _make_result(
            decision_id="d-001",
            legs={"market": 1.0, "signal": 1.0, "sizing": 1.0, "timing": None, "cost": None},
            censored={"timing": "entry_fill_unconfirmed", "cost": "entry_fill_unconfirmed"},
            total_pnl=None,
        )
        r2 = _make_result(
            decision_id="d-002",
            legs={"market": 1.0, "signal": 1.0, "sizing": 1.0, "timing": None, "cost": None},
            censored={"timing": "exit_unmatched", "cost": "entry_fill_unconfirmed"},
            total_pnl=None,
        )
        out = ab._aggregate([r1, r2])
        assert out["leg_censored"]["timing"] == {
            "entry_fill_unconfirmed": 1,
            "exit_unmatched": 1,
        }
        assert out["leg_censored"]["cost"] == {"entry_fill_unconfirmed": 2}

    def test_all_censored_no_dd_consumers(self):
        """When every leg is censored, totals are all 0.0 so dd_consumers is empty."""
        r = _make_result(
            legs={leg: None for leg in LEG_NAMES},
            censored={leg: "all_censored" for leg in LEG_NAMES},
            total_pnl=None,
        )
        out = ab._aggregate([r])
        assert out["n_records"] == 1
        assert out["n_decomposed"] == 0
        assert out["dd_consumers"] == []
        assert all(out["leg_totals"][leg] == pytest.approx(0.0) for leg in LEG_NAMES)

    def test_ranking_includes_all_legs(self):
        r = _make_result()
        out = ab._aggregate([r])
        ranking_legs = {row["leg"] for row in out["ranking"]}
        assert ranking_legs == set(LEG_NAMES)

    def test_ranking_row_structure(self):
        r = _make_result()
        out = ab._aggregate([r])
        for row in out["ranking"]:
            assert "leg" in row
            assert "total" in row
            assert "n" in row


# ===================================================================
# 3. leg_dd_consumption (mocked)
# ===================================================================

class TestLegDdConsumption:
    """Orchestration: decomposed_results mocked, verify window filtering + aggregate."""

    @pytest.fixture()
    def sample_results(self):
        return [
            _make_result(
                decision_id="d-001",
                date="2026-06-05",
                exit_date="2026-06-10",
                legs={"market": 5.0, "signal": 2.0, "sizing": -1.0, "timing": -0.5, "cost": -0.5},
                total_pnl=5.0,
            ),
            _make_result(
                decision_id="d-002",
                date="2026-06-12",
                exit_date="2026-06-18",
                legs={"market": -3.0, "signal": 1.0, "sizing": 0.5, "timing": -1.0, "cost": -0.5},
                total_pnl=-3.0,
            ),
            _make_result(
                decision_id="d-003",
                date="2026-06-20",
                exit_date=None,
                legs={"market": 2.0, "signal": 1.0, "sizing": 0.0, "timing": None, "cost": None},
                censored={"timing": "open_position", "cost": "open_position"},
                total_pnl=None,
            ),
        ]

    def _patch_decomposed(self, results):
        return patch.object(ab, "decomposed_results", return_value=results)

    def test_overall_only_no_window(self, sample_results):
        with self._patch_decomposed(sample_results):
            out = ab.leg_dd_consumption(None)  # conn unused because mocked
        assert "overall" in out
        assert "dd_window" not in out
        assert out["overall"]["n_records"] == 3

    def test_dd_window_filters_results(self, sample_results):
        with self._patch_decomposed(sample_results):
            out = ab.leg_dd_consumption(
                None, dd_window=("2026-06-11", "2026-06-25"),
            )
        assert "dd_window" in out
        win = out["dd_window"]
        assert win["start"] == "2026-06-11"
        assert win["end"] == "2026-06-25"
        # d-001 (exit 06-10) excluded — before window start.
        # d-002 (06-12 to 06-18) included.
        # d-003 (06-20, open) included.
        assert win["n_records"] == 2

    def test_overall_unaffected_by_window(self, sample_results):
        with self._patch_decomposed(sample_results):
            out = ab.leg_dd_consumption(
                None, dd_window=("2026-06-11", "2026-06-25"),
            )
        assert out["overall"]["n_records"] == 3

    def test_passthrough_kwargs(self, sample_results):
        """run_type, half_spread_bps, allow_sim forwarded to decomposed_results."""
        with patch.object(ab, "decomposed_results", return_value=[]) as mock_dr:
            ab.leg_dd_consumption(
                "fake_conn",
                run_type="sim",
                half_spread_bps=5.0,
                allow_sim=True,
            )
            mock_dr.assert_called_once_with(
                "fake_conn",
                run_type="sim",
                half_spread_bps=5.0,
                allow_sim=True,
            )

    def test_window_all_excluded(self):
        """Window that excludes all results (all closed before window start)."""
        closed_only = [
            _make_result(
                decision_id="d-001",
                date="2026-06-05",
                exit_date="2026-06-10",
                total_pnl=5.0,
            ),
            _make_result(
                decision_id="d-002",
                date="2026-06-12",
                exit_date="2026-06-18",
                total_pnl=-3.0,
            ),
        ]
        with self._patch_decomposed(closed_only):
            out = ab.leg_dd_consumption(
                None, dd_window=("2026-07-01", "2026-07-10"),
            )
        assert out["dd_window"]["n_records"] == 0
