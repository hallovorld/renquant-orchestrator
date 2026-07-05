"""Tests for the M4-b matched-breadth conviction-floor replay harness.

All fixtures are synthetic — no production DB, no live artifacts.
Covers: apply_floor with quantile and MAD formulas, matched_breadth_compare
on synthetic data, block_bootstrap_ci structure, and CLI dry-run.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.m4b_conviction_replay import (
    BREADTH_TOL,
    ReplayConfig,
    apply_floor,
    block_bootstrap_ci,
    block_bootstrap_diff_ci,
    calibrate_parameter,
    load_candidate_scores,
    main,
    matched_breadth_compare,
)


# ------------------------------------------------------------------ helpers


def _make_scores_df(
    dates: list[str],
    n_tickers: int = 10,
    seed: int = 42,
    mu_center: float = 0.02,
    mu_spread: float = 0.03,
) -> pd.DataFrame:
    """Create a synthetic scores DataFrame mimicking load_candidate_scores output."""
    rng = np.random.default_rng(seed)
    rows = []
    for date in dates:
        for i in range(n_tickers):
            mu = mu_center + mu_spread * (i / n_tickers - 0.5)
            rows.append({
                "date": date,
                "run_id": f"run-{date}",
                "ticker": f"T{i:03d}",
                "mu": mu,
                "raw_score": mu * 2.0,
                "blocked_by": None,
                "selected": 1,
                "fwd_20d": rng.normal(mu, 0.05),
                "fwd_5d": rng.normal(mu * 0.3, 0.03),
            })
    return pd.DataFrame(rows)


def _make_db(tmp_path: Path, dates: list[str], n_tickers: int = 25,
             mu_center: float = 0.02, mu_spread: float = 0.03,
             seed: int = 42) -> Path:
    """Create a minimal synthetic sqlite DB for testing load_candidate_scores."""
    db_path = tmp_path / "test_runs.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT,
            run_type TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE candidate_scores (
            run_id TEXT,
            ticker TEXT,
            mu REAL,
            raw_score REAL,
            blocked_by TEXT,
            selected INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE ticker_forward_returns (
            as_of_date TEXT,
            ticker TEXT,
            fwd_5d REAL,
            fwd_20d REAL,
            fwd_60d REAL
        )
    """)
    rng = np.random.default_rng(seed)
    for date in dates:
        run_id = f"run-{date}"
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?)",
            (run_id, date, "live", f"{date}T10:00:00"),
        )
        for i in range(n_tickers):
            mu = mu_center + mu_spread * (i / n_tickers - 0.5)
            conn.execute(
                "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, f"T{i:03d}", mu, mu * 2.0, None, 1),
            )
            fwd_20d = rng.normal(mu, 0.05)
            fwd_5d = rng.normal(mu * 0.3, 0.03)
            conn.execute(
                "INSERT INTO ticker_forward_returns VALUES (?, ?, ?, ?, ?)",
                (date, f"T{i:03d}", fwd_5d, fwd_20d, None),
            )
    conn.commit()
    conn.close()
    return db_path


# -------------------------------------------------------- test apply_floor


class TestApplyFloorQuantile:
    """Test apply_floor with the quantile formula (candidate (a))."""

    def test_quantile_top_20_admits_correct_fraction(self):
        """Top-20% quantile should admit approximately 20% of names."""
        df = _make_scores_df(["2026-07-01"], n_tickers=20, mu_center=0.05)
        config = ReplayConfig(quantile_k=0.20, baseline_floor=0.03)
        result = apply_floor(df, config)
        admitted = result["admitted_candidate"].sum()
        # With 20 tickers and top-20%, expect ~4 admitted (subject to mu>0)
        assert 2 <= admitted <= 6

    def test_quantile_respects_mu_positive_side_condition(self):
        """BL-4 side-condition: candidate must have mu > 0 even if in top-K%."""
        # All mu values negative -> no candidate admissions
        rows = [
            {"date": "2026-07-01", "run_id": "r1", "ticker": f"T{i}",
             "mu": -0.05 + i * 0.002, "raw_score": 0.0,
             "blocked_by": None, "selected": 1}
            for i in range(20)
        ]
        df = pd.DataFrame(rows)
        config = ReplayConfig(quantile_k=0.30, baseline_floor=0.03)
        result = apply_floor(df, config)
        assert result["admitted_candidate"].sum() == 0

    def test_quantile_admits_subset_of_scored_names(self):
        """Admitted names should be a subset of all names on the bar."""
        df = _make_scores_df(["2026-07-01", "2026-07-02"], n_tickers=30)
        config = ReplayConfig(quantile_k=0.25, baseline_floor=0.03)
        result = apply_floor(df, config)
        for _, group in result.groupby("date"):
            admitted = group[group["admitted_candidate"]]
            assert set(admitted["ticker"]).issubset(set(group["ticker"]))

    def test_rank_column_present_and_correct(self):
        """Each bar should have a rank column with 1 = highest mu."""
        df = _make_scores_df(["2026-07-01"], n_tickers=10, mu_center=0.05)
        config = ReplayConfig(quantile_k=0.30, baseline_floor=0.03)
        result = apply_floor(df, config)
        assert "rank" in result.columns
        # The name with the highest mu should have rank 1
        top = result.loc[result["mu"].idxmax()]
        assert top["rank"] == 1

    def test_empty_input(self):
        """Empty DataFrame should return empty with correct columns."""
        df = pd.DataFrame(columns=["date", "run_id", "ticker", "mu",
                                    "raw_score", "blocked_by", "selected"])
        config = ReplayConfig(quantile_k=0.20)
        result = apply_floor(df, config)
        assert "admitted_baseline" in result.columns
        assert "admitted_candidate" in result.columns
        assert len(result) == 0


class TestApplyFloorMAD:
    """Test apply_floor with the MAD formula (candidate (b))."""

    def test_mad_admits_separated_names(self):
        """Names with mu >= k*MAD AND mu > 0 should be admitted."""
        # Construct a bar with known MAD: median(|mu - median(mu)|)
        mus = [-0.04, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
        rows = [
            {"date": "2026-07-01", "run_id": "r1", "ticker": f"T{i}",
             "mu": m, "raw_score": m * 2, "blocked_by": None, "selected": 1}
            for i, m in enumerate(mus)
        ]
        df = pd.DataFrame(rows)
        config = ReplayConfig(mad_k=1.0, baseline_floor=0.03)
        result = apply_floor(df, config)

        # Compute expected MAD manually
        mu_series = pd.Series(mus)
        median_mu = mu_series.median()
        mad = (mu_series - median_mu).abs().median()

        # Names with mu >= mad AND mu > 0
        admitted = result[result["admitted_candidate"]]
        for _, row in admitted.iterrows():
            assert row["mu"] >= mad
            assert row["mu"] > 0

    def test_mad_zero_dispersion_admits_none(self):
        """If all mu are identical (MAD=0), k*MAD=0 so only mu>0 matters."""
        rows = [
            {"date": "2026-07-01", "run_id": "r1", "ticker": f"T{i}",
             "mu": 0.02, "raw_score": 0.04, "blocked_by": None, "selected": 1}
            for i in range(10)
        ]
        df = pd.DataFrame(rows)
        # k=1.0, MAD=0.0 -> floor=0.0, so mu>0 is the binding condition
        config = ReplayConfig(mad_k=1.0, baseline_floor=0.03)
        result = apply_floor(df, config)
        # All have mu=0.02 > 0 and mu >= 0 -> all admitted
        assert result["admitted_candidate"].sum() == 10

    def test_mad_respects_mu_positive_side_condition(self):
        """Even with a low MAD floor, negative mu names are excluded."""
        mus = [-0.10, -0.08, -0.05, -0.03, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05]
        rows = [
            {"date": "2026-07-01", "run_id": "r1", "ticker": f"T{i}",
             "mu": m, "raw_score": m * 2, "blocked_by": None, "selected": 1}
            for i, m in enumerate(mus)
        ]
        df = pd.DataFrame(rows)
        config = ReplayConfig(mad_k=0.5, baseline_floor=0.03)
        result = apply_floor(df, config)
        admitted = result[result["admitted_candidate"]]
        assert (admitted["mu"] > 0).all()


class TestApplyFloorBaseline:
    """Test the baseline absolute floor."""

    def test_baseline_admits_above_floor(self):
        """Baseline admits names with mu >= baseline_floor."""
        df = _make_scores_df(["2026-07-01"], n_tickers=10, mu_center=0.04)
        config = ReplayConfig(baseline_floor=0.03)
        result = apply_floor(df, config)
        admitted = result[result["admitted_baseline"]]
        assert (admitted["mu"] >= 0.03).all()

    def test_baseline_rejects_below_floor(self):
        """Names below the floor should not be baseline-admitted."""
        df = _make_scores_df(["2026-07-01"], n_tickers=10, mu_center=0.04)
        config = ReplayConfig(baseline_floor=0.03)
        result = apply_floor(df, config)
        rejected = result[~result["admitted_baseline"]]
        assert (rejected["mu"] < 0.03).all()


# ------------------------------------------------- test matched_breadth_compare


class TestMatchedBreadthCompare:
    """Test matched_breadth_compare on synthetic data."""

    def test_basic_comparison_structure(self):
        """Result should have all expected keys."""
        df = _make_scores_df(
            ["2026-07-01", "2026-07-02", "2026-07-03"],
            n_tickers=20,
            mu_center=0.04,
        )
        config = ReplayConfig(quantile_k=0.25, baseline_floor=0.03)
        admitted = apply_floor(df, config)
        result = matched_breadth_compare(admitted)

        assert "per_day_stats" in result
        assert "mean_baseline_breadth" in result
        assert "mean_candidate_breadth" in result
        assert "daily_return_baseline" in result
        assert "daily_return_candidate" in result
        assert "summary" in result
        assert len(result["per_day_stats"]) == 3

    def test_per_day_stats_have_required_fields(self):
        """Each per-day stat dict should have date, counts, and return fields."""
        df = _make_scores_df(["2026-07-01"], n_tickers=15, mu_center=0.04)
        config = ReplayConfig(quantile_k=0.30, baseline_floor=0.03)
        admitted = apply_floor(df, config)
        result = matched_breadth_compare(admitted)

        for stat in result["per_day_stats"]:
            assert "date" in stat
            assert "n_baseline" in stat
            assert "n_candidate" in stat
            assert "mean_ret_baseline" in stat
            assert "mean_ret_candidate" in stat

    def test_matched_breadth_limits_candidate_to_baseline_count(self):
        """The matched candidate set should have at most N_baseline names."""
        df = _make_scores_df(
            ["2026-07-01", "2026-07-02"],
            n_tickers=30,
            mu_center=0.04,
        )
        config = ReplayConfig(quantile_k=0.50, baseline_floor=0.03)
        admitted = apply_floor(df, config)
        result = matched_breadth_compare(admitted)

        for stat in result["per_day_stats"]:
            if stat["n_matched"] > 0:
                assert stat["n_matched"] <= stat["n_baseline"]

    def test_empty_input_returns_empty_structure(self):
        """Empty DataFrame should produce valid empty result."""
        df = pd.DataFrame(columns=[
            "date", "run_id", "ticker", "mu", "raw_score",
            "admitted_baseline", "admitted_candidate", "fwd_20d",
        ])
        result = matched_breadth_compare(df)
        assert result["per_day_stats"] == []
        assert result["mean_baseline_breadth"] == 0.0
        assert len(result["daily_return_baseline"]) == 0

    def test_summary_delta_is_consistent(self):
        """Pooled delta should equal candidate mean - baseline mean."""
        df = _make_scores_df(
            ["2026-07-01", "2026-07-02", "2026-07-03"],
            n_tickers=20,
            mu_center=0.04,
            seed=123,
        )
        config = ReplayConfig(quantile_k=0.25, baseline_floor=0.03)
        admitted = apply_floor(df, config)
        result = matched_breadth_compare(admitted)
        s = result["summary"]
        if s.get("n_resolved_dates", 0) > 0:
            expected_delta = s["pooled_mean_candidate"] - s["pooled_mean_baseline"]
            assert s["pooled_delta"] == pytest.approx(expected_delta, abs=1e-10)


# ------------------------------------------------------- test block_bootstrap_ci


class TestBlockBootstrapCI:
    """Test block_bootstrap_ci returns expected structure."""

    def test_returns_ci_for_sufficient_data(self):
        """With enough dates, should produce bootstrap CI."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.01, 0.03, size=30)
        result = block_bootstrap_ci(returns, n_boot=500, block_size=5)
        assert result["admissible"] is True
        assert "ci95_two_sided" in result
        assert "boot_se" in result
        assert "mean" in result
        assert len(result["ci95_two_sided"]) == 2

    def test_too_few_dates_returns_inadmissible(self):
        """With very few dates, bootstrap should be refused."""
        returns = np.array([0.01, 0.02, 0.03])
        result = block_bootstrap_ci(returns, n_boot=500, block_size=5)
        assert result["admissible"] is False
        assert "reason" in result

    def test_single_value_returns_inadmissible(self):
        """A single-element array should not be admissible."""
        result = block_bootstrap_ci(np.array([0.05]), n_boot=500, block_size=5)
        assert result["admissible"] is False

    def test_diff_ci_structure(self):
        """block_bootstrap_diff_ci should return a proper CI structure."""
        rng = np.random.default_rng(42)
        base = rng.normal(0.01, 0.03, size=30)
        cand = rng.normal(0.015, 0.03, size=30)
        result = block_bootstrap_diff_ci(base, cand, n_boot=500, block_size=5)
        assert result["admissible"] is True
        assert "ci95_two_sided" in result
        assert "mean" in result

    def test_diff_ci_length_mismatch(self):
        """Mismatched array lengths should return an error."""
        result = block_bootstrap_diff_ci(
            np.array([0.01, 0.02]),
            np.array([0.01, 0.02, 0.03]),
            n_boot=100,
        )
        assert "error" in result

    def test_ci_bounds_contain_mean(self):
        """The 95% CI should contain the sample mean (most of the time)."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.02, 0.03, size=50)
        result = block_bootstrap_ci(returns, n_boot=2000, block_size=5)
        assert result["admissible"] is True
        lo, hi = result["ci95_two_sided"]
        # The mean should be within the CI (with high probability)
        assert lo <= result["mean"] <= hi


# -------------------------------------------------------------- test CLI


class TestCLI:
    """Test the CLI entry point."""

    def test_cli_with_db(self, tmp_path):
        """CLI should run successfully with a synthetic DB."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
             "2026-06-05"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main([
            "--db", str(db_path),
            "--quantile-k", "0.30",
            "--baseline-floor", "0.03",
        ])
        assert rc == 0

    def test_cli_json_output(self, tmp_path, capsys):
        """CLI with --json should output valid JSON."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main([
            "--db", str(db_path),
            "--quantile-k", "0.25",
            "--json",
        ])
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "config" in data
        assert "comparison" in data
        assert "bootstrap_ci" in data

    def test_cli_output_file(self, tmp_path):
        """CLI with --output should write results to a file."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            n_tickers=25,
            mu_center=0.04,
        )
        out_path = tmp_path / "results.json"
        rc = main([
            "--db", str(db_path),
            "--mad-k", "1.0",
            "--output", str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "config" in data

    def test_cli_missing_db(self, tmp_path, capsys):
        """CLI with a non-existent DB should exit with error."""
        rc = main(["--db", str(tmp_path / "nonexistent.db")])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower() or "ERROR" in err

    def test_cli_mad_formula(self, tmp_path, capsys):
        """CLI with --mad-k should use the dispersion formula."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main([
            "--db", str(db_path),
            "--mad-k", "0.5",
            "--json",
        ])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["config"]["mad_k"] == 0.5

    def test_cli_date_range(self, tmp_path, capsys):
        """CLI with date range should filter scores."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-05", "2026-06-10", "2026-06-15"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main([
            "--db", str(db_path),
            "--start-date", "2026-06-05",
            "--end-date", "2026-06-10",
            "--quantile-k", "0.25",
            "--json",
        ])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        # Should only have dates within the range
        stats = data["comparison"]["per_day_stats"]
        for s in stats:
            assert "2026-06-05" <= s["date"] <= "2026-06-10"

    def test_cli_calibrate_without_formula_errors(self, tmp_path, capsys):
        """--calibrate with neither --quantile-k nor --mad-k has no formula to
        calibrate, and would otherwise silently compare baseline to itself
        (admitted_candidate falls back to admitted_baseline) -- must error,
        not silently no-op."""
        db_path = _make_db(
            tmp_path, ["2026-06-01", "2026-06-02"], n_tickers=25, mu_center=0.04,
        )
        rc = main(["--db", str(db_path), "--calibrate", "--json"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "--quantile-k or --mad-k" in err

    def test_cli_json_calibrated_field_true_when_calibrate_passed(
        self, tmp_path, capsys,
    ):
        """--calibrate with a formula flag: JSON output's calibrated field
        must be True -- this is the structural flag downstream consumers
        check to know which experiment class produced the report."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
             "2026-06-05"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main([
            "--db", str(db_path), "--quantile-k", "0.30", "--calibrate", "--json",
        ])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["calibrated"] is True

    def test_cli_json_calibrated_field_false_without_calibrate_flag(
        self, tmp_path, capsys,
    ):
        """Fixed-parameter run (no --calibrate): JSON output's calibrated
        field must be False, even though --quantile-k was given."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main(["--db", str(db_path), "--quantile-k", "0.30", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["calibrated"] is False

    def test_cli_text_report_uncalibrated_is_labeled_exploratory(
        self, tmp_path, capsys,
    ):
        """The default text report for a fixed-parameter (uncalibrated) run
        must NOT claim the matched-breadth title -- this is the exact gap
        Codex flagged: a user could run --quantile-k alone and get a report
        titled 'M4-b Matched-Breadth Conviction Floor Replay' with no
        calibration having occurred."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main(["--db", str(db_path), "--quantile-k", "0.30"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Exploratory Fixed-Parameter Replay" in out
        assert "NOT matched-breadth" in out
        assert "Matched-Breadth Conviction Floor Replay" not in out
        assert "WARNING" in out

    def test_cli_text_report_calibrated_is_labeled_matched_breadth(
        self, tmp_path, capsys,
    ):
        """The default text report for a genuinely calibrated run must show
        the matched-breadth title, with no exploratory warning."""
        db_path = _make_db(
            tmp_path,
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
             "2026-06-05"],
            n_tickers=25,
            mu_center=0.04,
        )
        rc = main(["--db", str(db_path), "--quantile-k", "0.30", "--calibrate"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("# M4-b Matched-Breadth Conviction Floor Replay")
        assert "Exploratory" not in out
        assert "WARNING" not in out


# ------------------------------------------------- test load_candidate_scores


class TestLoadCandidateScores:
    """Test the DB loader."""

    def test_loads_all_dates(self, tmp_path):
        dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
        db_path = _make_db(tmp_path, dates, n_tickers=25)
        df = load_candidate_scores(db_path)
        assert set(df["date"].unique()) == set(dates)

    def test_date_filtering(self, tmp_path):
        dates = ["2026-06-01", "2026-06-05", "2026-06-10"]
        db_path = _make_db(tmp_path, dates, n_tickers=25)
        df = load_candidate_scores(db_path, start_date="2026-06-05")
        assert "2026-06-01" not in df["date"].values
        assert "2026-06-05" in df["date"].values

    def test_canonical_run_dedup(self, tmp_path):
        """When multiple runs exist for the same date, keep only canonical."""
        db_path = tmp_path / "dedup.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE pipeline_runs (
                run_id TEXT PRIMARY KEY, run_date TEXT,
                run_type TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE candidate_scores (
                run_id TEXT, ticker TEXT, mu REAL,
                raw_score REAL, blocked_by TEXT, selected INTEGER
            )
        """)
        # Two runs on the same date
        conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?, ?)",
                     ("run-a", "2026-06-01", "live", "2026-06-01T09:00"))
        conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?, ?)",
                     ("run-b", "2026-06-01", "live", "2026-06-01T10:00"))
        for run_id in ("run-a", "run-b"):
            for i in range(25):
                conn.execute(
                    "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, f"T{i:03d}", 0.05, 0.10, None, 1),
                )
        conn.commit()
        conn.close()
        df = load_candidate_scores(db_path)
        # Should only have one canonical run
        assert len(df["run_id"].unique()) == 1

    def test_joins_forward_returns(self, tmp_path):
        db_path = _make_db(tmp_path, ["2026-06-01"], n_tickers=25)
        df = load_candidate_scores(db_path)
        assert "fwd_20d" in df.columns

    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE pipeline_runs (
                run_id TEXT PRIMARY KEY, run_date TEXT,
                run_type TEXT, created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE candidate_scores (
                run_id TEXT, ticker TEXT, mu REAL,
                raw_score REAL, blocked_by TEXT, selected INTEGER
            )
        """)
        conn.commit()
        conn.close()
        df = load_candidate_scores(db_path)
        assert df.empty


# ------------------------------------------------ test calibrate_parameter


class TestCalibrateParameter:
    """Test the matched-breadth calibration loop."""

    def test_quantile_calibration_matches_baseline_breadth(self) -> None:
        dates = [f"2026-06-{d:02d}" for d in range(1, 21)]
        scores = _make_scores_df(dates, n_tickers=30, mu_spread=0.06)

        config = ReplayConfig(quantile_k=0.3, baseline_floor=0.03, min_breadth=5)
        calibrated_k = calibrate_parameter(scores, config)

        # Apply with calibrated parameter and verify breadth matches
        cal_config = ReplayConfig(
            quantile_k=calibrated_k, baseline_floor=0.03, min_breadth=5,
        )
        admitted = apply_floor(scores, cal_config)
        baseline_config = ReplayConfig(baseline_floor=0.03, min_breadth=5)
        baseline_admitted = apply_floor(scores, baseline_config)

        mean_cand = admitted.groupby("date")["admitted_candidate"].sum().mean()
        mean_base = baseline_admitted.groupby("date")["admitted_baseline"].sum().mean()
        assert abs(mean_cand - mean_base) <= BREADTH_TOL

    def test_mad_calibration_matches_baseline_breadth(self) -> None:
        dates = [f"2026-06-{d:02d}" for d in range(1, 21)]
        scores = _make_scores_df(dates, n_tickers=30, mu_spread=0.06)

        config = ReplayConfig(mad_k=1.0, baseline_floor=0.03, min_breadth=5)
        calibrated_k = calibrate_parameter(scores, config)

        cal_config = ReplayConfig(
            mad_k=calibrated_k, baseline_floor=0.03, min_breadth=5,
        )
        admitted = apply_floor(scores, cal_config)
        baseline_config = ReplayConfig(baseline_floor=0.03, min_breadth=5)
        baseline_admitted = apply_floor(scores, baseline_config)

        mean_cand = admitted.groupby("date")["admitted_candidate"].sum().mean()
        mean_base = baseline_admitted.groupby("date")["admitted_baseline"].sum().mean()
        assert abs(mean_cand - mean_base) <= BREADTH_TOL

    def test_calibration_raises_on_empty_data(self) -> None:
        scores = _make_scores_df([], n_tickers=30)
        config = ReplayConfig(quantile_k=0.3, baseline_floor=0.03, min_breadth=5)
        with pytest.raises(ValueError, match="no dates"):
            calibrate_parameter(scores, config)

    def test_calibrated_k_is_positive(self) -> None:
        dates = [f"2026-06-{d:02d}" for d in range(1, 16)]
        scores = _make_scores_df(dates, n_tickers=25, mu_spread=0.04)

        config = ReplayConfig(quantile_k=0.2, baseline_floor=0.03, min_breadth=5)
        calibrated_k = calibrate_parameter(scores, config)
        assert calibrated_k > 0
