"""Tests for attribution/report.py pure functions (107 sprint D3).

Covers:
1. coverage_report — per-leg coverage counts, censoring, exit_unmatched skip
2. rollup — per-leg totals, by-month, by-regime, cumulative curves, leak ranking
3. render_markdown — smoke tests for expected sections and formatting
4. _check_out_dir — forbidden production paths rejected, safe paths returned
5. write_report — file creation, names, JSON parsability
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.attribution import report as rp
from renquant_orchestrator.attribution.decompose import LEG_NAMES


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_result(**overrides):
    base = {
        "decision_id": "test-001",
        "date": "2026-06-15",
        "exit_date": "2026-06-20",
        "ticker": "AAPL",
        "status": "closed",
        "regime": "BULL_CALM",
        "run_type": "live",
        "mu": 0.05,
        "rank_score": 3.0,
        "blocked_by": None,
        "exit_reason": "panel_exit",
        "legs": {"market": 10.0, "signal": 5.0, "sizing": -2.0, "timing": -3.0, "cost": -1.0},
        "censored": {},
        "total_pnl": 9.0,
        "sum_check": {"total": 9.0, "legs_sum": 9.0, "residual": 0.0, "ok": True},
        "diagnostics": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. TestCoverageReport
# ---------------------------------------------------------------------------

class TestCoverageReport:
    def test_fully_present_single_record(self):
        """All legs present -> every leg bucket is 'present' with n=1."""
        results = [_make_result()]
        cov = rp.coverage_report(results)
        assert cov["n_records"] == 1
        assert cov["n_fully_decomposable"] == 1
        assert cov["n_open_mtm"] == 0
        assert cov["n_exit_unmatched"] == 0
        for leg in LEG_NAMES:
            assert "present" in cov["per_leg"][leg]
            assert cov["per_leg"][leg]["present"]["n"] == 1

    def test_exit_unmatched_skipped(self):
        """exit_unmatched records are excluded from per_leg buckets."""
        results = [
            _make_result(status="exit_unmatched"),
            _make_result(decision_id="test-002"),
        ]
        cov = rp.coverage_report(results)
        assert cov["n_records"] == 2
        assert cov["n_exit_unmatched"] == 1
        # Only the non-unmatched record counts in per_leg
        for leg in LEG_NAMES:
            assert cov["per_leg"][leg]["present"]["n"] == 1

    def test_open_mtm_counted(self):
        """open_mtm records counted in n_open_mtm and included in per_leg."""
        results = [_make_result(status="open_mtm")]
        cov = rp.coverage_report(results)
        assert cov["n_open_mtm"] == 1
        for leg in LEG_NAMES:
            assert cov["per_leg"][leg]["present"]["n"] == 1

    def test_censored_leg_bucketed(self):
        """A censored leg appears under its censoring reason, not 'present'."""
        results = [_make_result(
            legs={"market": 10.0, "signal": 5.0, "sizing": None, "timing": None, "cost": -1.0},
            censored={"sizing": "no_fill_confirmation", "timing": "no_fill_confirmation"},
        )]
        cov = rp.coverage_report(results)
        assert "no_fill_confirmation" in cov["per_leg"]["sizing"]
        assert cov["per_leg"]["sizing"]["no_fill_confirmation"]["n"] == 1
        assert "present" not in cov["per_leg"]["sizing"]
        # Legs that ARE present still show up
        assert cov["per_leg"]["market"]["present"]["n"] == 1

    def test_absent_leg_bucketed(self):
        """A None leg without a censoring reason shows as 'absent'."""
        results = [_make_result(
            legs={"market": 10.0, "signal": None, "sizing": -2.0, "timing": -3.0, "cost": -1.0},
            censored={},
        )]
        cov = rp.coverage_report(results)
        assert "absent" in cov["per_leg"]["signal"]
        assert cov["per_leg"]["signal"]["absent"]["n"] == 1

    def test_multiple_censoring_reasons_per_leg(self):
        """Multiple records with different censoring reasons for the same leg."""
        results = [
            _make_result(
                decision_id="r1",
                date="2026-06-10",
                legs={"market": 1.0, "signal": None, "sizing": None, "timing": None, "cost": None},
                censored={"signal": "no_spy_data", "sizing": "no_fill_confirmation",
                           "timing": "no_fill_confirmation", "cost": "no_fill_confirmation"},
            ),
            _make_result(
                decision_id="r2",
                date="2026-06-15",
                legs={"market": 2.0, "signal": None, "sizing": None, "timing": None, "cost": None},
                censored={"signal": "no_ref_exit", "sizing": "no_shares",
                           "timing": "no_shares", "cost": "no_shares"},
            ),
        ]
        cov = rp.coverage_report(results)
        sig = cov["per_leg"]["signal"]
        assert "no_spy_data" in sig
        assert "no_ref_exit" in sig
        assert sig["no_spy_data"]["n"] == 1
        assert sig["no_ref_exit"]["n"] == 1

    def test_date_range_correct(self):
        """date_min/date_max reflect the actual date range of records in each bucket."""
        results = [
            _make_result(decision_id="r1", date="2026-06-01"),
            _make_result(decision_id="r2", date="2026-06-15"),
            _make_result(decision_id="r3", date="2026-06-30"),
        ]
        cov = rp.coverage_report(results)
        present = cov["per_leg"]["market"]["present"]
        assert present["date_min"] == "2026-06-01"
        assert present["date_max"] == "2026-06-30"
        assert present["n"] == 3

    def test_n_fully_decomposable_null_sum_check(self):
        """Records with sum_check=None do not count as fully decomposable."""
        results = [
            _make_result(decision_id="r1", sum_check=None),
            _make_result(decision_id="r2"),
        ]
        cov = rp.coverage_report(results)
        assert cov["n_fully_decomposable"] == 1

    def test_notes_present(self):
        """Coverage report includes informational notes."""
        cov = rp.coverage_report([_make_result()])
        assert isinstance(cov["notes"], list)
        assert len(cov["notes"]) >= 1

    def test_empty_results(self):
        """Empty results list produces empty per_leg buckets."""
        cov = rp.coverage_report([])
        assert cov["n_records"] == 0
        assert cov["n_fully_decomposable"] == 0
        for leg in LEG_NAMES:
            assert cov["per_leg"][leg] == {}


# ---------------------------------------------------------------------------
# 2. TestRollup
# ---------------------------------------------------------------------------

class TestRollup:
    def test_single_record_totals(self):
        """Single fully-present record: leg totals match the record's legs."""
        results = [_make_result()]
        roll = rp.rollup(results)
        assert roll["leg_totals"]["market"] == pytest.approx(10.0)
        assert roll["leg_totals"]["signal"] == pytest.approx(5.0)
        assert roll["leg_totals"]["cost"] == pytest.approx(-1.0)
        for leg in LEG_NAMES:
            assert roll["leg_counts"][leg] == 1

    def test_none_legs_skipped(self):
        """None legs are not summed and do not increment the count."""
        results = [_make_result(
            legs={"market": 10.0, "signal": None, "sizing": None, "timing": None, "cost": -1.0},
        )]
        roll = rp.rollup(results)
        assert roll["leg_totals"]["signal"] == 0.0
        assert roll["leg_counts"]["signal"] == 0
        assert roll["leg_totals"]["market"] == pytest.approx(10.0)
        assert roll["leg_counts"]["market"] == 1

    def test_multiple_records_across_months(self):
        """Two records in different months show up in by_month."""
        results = [
            _make_result(decision_id="r1", date="2026-05-10",
                         legs={"market": 5.0, "signal": 2.0, "sizing": 0.0, "timing": 0.0, "cost": -0.5}),
            _make_result(decision_id="r2", date="2026-06-15",
                         legs={"market": 3.0, "signal": 1.0, "sizing": 0.0, "timing": 0.0, "cost": -0.3}),
        ]
        roll = rp.rollup(results)
        assert "2026-05" in roll["by_month"]
        assert "2026-06" in roll["by_month"]
        assert roll["by_month"]["2026-05"]["market"] == pytest.approx(5.0)
        assert roll["by_month"]["2026-06"]["market"] == pytest.approx(3.0)

    def test_multiple_records_across_regimes(self):
        """Records in different regimes appear in by_regime."""
        results = [
            _make_result(decision_id="r1", regime="BULL_CALM",
                         legs={"market": 5.0, "signal": 0.0, "sizing": 0.0, "timing": 0.0, "cost": 0.0}),
            _make_result(decision_id="r2", regime="BEAR_VOLATILE",
                         legs={"market": -3.0, "signal": 0.0, "sizing": 0.0, "timing": 0.0, "cost": 0.0}),
        ]
        roll = rp.rollup(results)
        assert roll["by_regime"]["BULL_CALM"]["market"] == pytest.approx(5.0)
        assert roll["by_regime"]["BEAR_VOLATILE"]["market"] == pytest.approx(-3.0)

    def test_unknown_regime_fallback(self):
        """Missing regime falls back to 'UNKNOWN'."""
        results = [_make_result(regime=None)]
        roll = rp.rollup(results)
        assert "UNKNOWN" in roll["by_regime"]

    def test_cumulative_curves(self):
        """Cumulative curves accumulate in date order."""
        results = [
            _make_result(decision_id="r1", date="2026-06-01",
                         legs={"market": 3.0, "signal": 0.0, "sizing": 0.0, "timing": 0.0, "cost": 0.0}),
            _make_result(decision_id="r2", date="2026-06-10",
                         legs={"market": 7.0, "signal": 0.0, "sizing": 0.0, "timing": 0.0, "cost": 0.0}),
        ]
        roll = rp.rollup(results)
        curve = roll["cumulative_curves"]["market"]
        assert len(curve) == 2
        assert curve[0] == ("2026-06-01", pytest.approx(3.0))
        assert curve[1] == ("2026-06-10", pytest.approx(10.0))

    def test_leak_ranking_sorted_ascending(self):
        """Leak ranking is sorted by total ascending (worst leak first)."""
        results = [_make_result(
            legs={"market": 10.0, "signal": 5.0, "sizing": -8.0, "timing": -3.0, "cost": -1.0},
        )]
        roll = rp.rollup(results)
        totals = [row["total"] for row in roll["leak_ranking"]]
        assert totals == sorted(totals)
        # sizing is the biggest leak (-8.0) -> should be first
        assert roll["leak_ranking"][0]["leg"] == "sizing"
        assert roll["leak_ranking"][0]["total"] == pytest.approx(-8.0)

    def test_total_pnl_summation(self):
        """total_pnl_where_computable sums total_pnl from all records where non-None."""
        results = [
            _make_result(decision_id="r1", total_pnl=9.0),
            _make_result(decision_id="r2", total_pnl=-3.0),
            _make_result(decision_id="r3", total_pnl=None),
        ]
        roll = rp.rollup(results)
        assert roll["total_pnl_where_computable"] == pytest.approx(6.0)

    def test_empty_results(self):
        """Empty results: totals are all zero, leak_ranking exists."""
        roll = rp.rollup([])
        for leg in LEG_NAMES:
            assert roll["leg_totals"][leg] == 0.0
            assert roll["leg_counts"][leg] == 0
        assert len(roll["leak_ranking"]) == len(LEG_NAMES)
        assert roll["total_pnl_where_computable"] == 0.0

    def test_by_month_keys_sorted(self):
        """by_month keys are sorted chronologically."""
        results = [
            _make_result(decision_id="r1", date="2026-07-01"),
            _make_result(decision_id="r2", date="2026-05-01"),
            _make_result(decision_id="r3", date="2026-06-01"),
        ]
        roll = rp.rollup(results)
        months = list(roll["by_month"].keys())
        assert months == sorted(months)


# ---------------------------------------------------------------------------
# 3. TestRenderMarkdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    @pytest.fixture()
    def sample_report(self):
        results = [
            _make_result(decision_id="r1", date="2026-06-10", regime="BULL_CALM"),
            _make_result(decision_id="r2", date="2026-06-20", regime="BEAR_VOLATILE",
                         legs={"market": -5.0, "signal": 2.0, "sizing": 0.0, "timing": -1.0, "cost": -0.5},
                         total_pnl=-4.5),
        ]
        return {
            "generated_at": "2026-06-25T12:00:00+00:00",
            "run_type": "live",
            "half_spread_bps": 5.0,
            "coverage": rp.coverage_report(results),
            "rollup": rp.rollup(results),
            "records": results,
        }

    def test_contains_title(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "# Decision-ledger attribution report" in md

    def test_contains_generated_at(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "2026-06-25T12:00:00+00:00" in md

    def test_contains_leak_ranking_table(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "| leg | total $ | n records |" in md
        # Every leg name should appear somewhere in the table
        for leg in LEG_NAMES:
            assert f"| {leg} |" in md

    def test_contains_coverage_table(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "| leg | state | n | first date | last date |" in md

    def test_contains_per_month_section(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "## Per-month leg totals" in md
        assert "2026-06" in md

    def test_contains_per_regime_section(self, sample_report):
        md = rp.render_markdown(sample_report)
        assert "## Per-regime leg totals" in md
        assert "BULL_CALM" in md
        assert "BEAR_VOLATILE" in md

    def test_number_formatting(self, sample_report):
        md = rp.render_markdown(sample_report)
        # Numbers should be formatted with sign and 2 decimal places
        assert "+10.00" in md or "-5.00" in md  # market legs
        assert "+5.00" in md  # signal from first record


# ---------------------------------------------------------------------------
# 4. TestCheckOutDir
# ---------------------------------------------------------------------------

class TestCheckOutDir:
    def test_safe_path_returned_resolved(self, tmp_path):
        """A safe path is returned as a resolved Path."""
        result = rp._check_out_dir(tmp_path / "attribution")
        assert result == (tmp_path / "attribution").resolve()

    def test_forbidden_umbrella_data_raises(self):
        """Path under the umbrella repo's data/ directory raises ValueError."""
        forbidden = rp._CANONICAL_UMBRELLA / "data" / "runs"
        with pytest.raises(ValueError, match="production path"):
            rp._check_out_dir(forbidden)

    def test_forbidden_umbrella_runtime_raises(self):
        """Path under the umbrella repo's runtime/ directory raises ValueError."""
        forbidden = rp._CANONICAL_UMBRELLA / "runtime" / "output"
        with pytest.raises(ValueError, match="production path"):
            rp._check_out_dir(forbidden)

    def test_forbidden_data_root_data_raises(self):
        """Path under _DATA_ROOT/data/ raises ValueError."""
        forbidden = rp._DATA_ROOT / "data" / "some_subdir"
        with pytest.raises(ValueError, match="production path"):
            rp._check_out_dir(forbidden)

    def test_forbidden_data_root_runtime_raises(self):
        """Path under _DATA_ROOT/runtime/ raises ValueError."""
        forbidden = rp._DATA_ROOT / "runtime" / "some_subdir"
        with pytest.raises(ValueError, match="production path"):
            rp._check_out_dir(forbidden)

    def test_nested_forbidden_raises(self):
        """Deeply nested paths under forbidden prefixes also raise."""
        forbidden = rp._CANONICAL_UMBRELLA / "data" / "a" / "b" / "c"
        with pytest.raises(ValueError, match="production path"):
            rp._check_out_dir(forbidden)

    def test_home_path_allowed(self):
        """A path under home but not under forbidden prefixes is allowed."""
        safe = Path.home() / "renquant-data" / "research" / "test"
        result = rp._check_out_dir(safe)
        assert result == safe.resolve()

    def test_tilde_expansion(self):
        """Tilde paths are expanded before checking."""
        safe = Path("~/renquant-data/research/test-out")
        result = rp._check_out_dir(safe)
        assert result == safe.expanduser().resolve()


# ---------------------------------------------------------------------------
# 5. TestWriteReport
# ---------------------------------------------------------------------------

class TestWriteReport:
    @pytest.fixture()
    def sample_report(self):
        results = [_make_result()]
        return {
            "generated_at": "2026-06-25T120000+0000",
            "run_type": "live",
            "half_spread_bps": 0.0,
            "coverage": rp.coverage_report(results),
            "rollup": rp.rollup(results),
            "records": results,
        }

    def test_files_created(self, tmp_path, sample_report):
        """write_report creates both .md and .json files."""
        paths = rp.write_report(sample_report, tmp_path)
        assert paths["markdown"].exists()
        assert paths["json"].exists()
        assert paths["markdown"].suffix == ".md"
        assert paths["json"].suffix == ".json"

    def test_filenames_contain_stamp_and_run_type(self, tmp_path, sample_report):
        """File names contain the run type and timestamp."""
        paths = rp.write_report(sample_report, tmp_path)
        md_name = paths["markdown"].name
        assert "attribution_live_" in md_name

    def test_json_parseable(self, tmp_path, sample_report):
        """The JSON file is valid JSON and matches the report structure."""
        paths = rp.write_report(sample_report, tmp_path)
        data = json.loads(paths["json"].read_text())
        assert data["run_type"] == "live"
        assert "coverage" in data
        assert "rollup" in data

    def test_markdown_content(self, tmp_path, sample_report):
        """The markdown file contains the report title."""
        paths = rp.write_report(sample_report, tmp_path)
        md_text = paths["markdown"].read_text()
        assert "# Decision-ledger attribution report" in md_text

    def test_creates_directory(self, tmp_path, sample_report):
        """write_report creates the output directory if it does not exist."""
        out = tmp_path / "nested" / "dir"
        paths = rp.write_report(sample_report, out)
        assert out.is_dir()
        assert paths["markdown"].exists()

    def test_forbidden_path_raises(self, sample_report):
        """write_report refuses to write under production paths."""
        forbidden = rp._CANONICAL_UMBRELLA / "data" / "attribution"
        with pytest.raises(ValueError, match="production path"):
            rp.write_report(sample_report, forbidden)


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

class TestLegState:
    """Test the _leg_state helper directly for completeness."""

    def test_present_leg(self):
        result = _make_result()
        assert rp._leg_state(result, "market") == "present"

    def test_censored_leg(self):
        result = _make_result(
            legs={"market": 10.0, "signal": None, "sizing": 0.0, "timing": 0.0, "cost": 0.0},
            censored={"signal": "no_spy_data"},
        )
        assert rp._leg_state(result, "signal") == "no_spy_data"

    def test_absent_leg(self):
        result = _make_result(
            legs={"market": 10.0, "signal": None, "sizing": 0.0, "timing": 0.0, "cost": 0.0},
            censored={},
        )
        assert rp._leg_state(result, "signal") == "absent"

    def test_zero_is_present(self):
        """A leg value of 0.0 is 'present', not absent."""
        result = _make_result(
            legs={"market": 0.0, "signal": 0.0, "sizing": 0.0, "timing": 0.0, "cost": 0.0},
        )
        assert rp._leg_state(result, "market") == "present"


class TestFmt:
    """Test the _fmt helper."""

    def test_none_returns_censored(self):
        assert rp._fmt(None) == "censored"

    def test_positive_formatted(self):
        assert rp._fmt(10.5) == "+10.50"

    def test_negative_formatted(self):
        assert rp._fmt(-3.14) == "-3.14"

    def test_zero_formatted(self):
        assert rp._fmt(0.0) == "+0.00"
