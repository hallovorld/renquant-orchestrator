"""Tests for S-TC transfer coefficient measurement."""
from __future__ import annotations

import os
import subprocess
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

from renquant_orchestrator.tc_measurement import (
    TC_DDL,
    DEFAULT_RUNS_DB,
    _classify_reason,
    compute_buy_side_tc,
    run_measurement,
)
from renquant_orchestrator.runtime_paths import default_data_root


def _create_runs_db(tmp_path):
    db = tmp_path / "runs.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT,
            created_at TEXT
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, role TEXT, mu REAL,
            sigma REAL, kelly_target_pct REAL, blocked_by TEXT
        );
        CREATE TABLE trades (
            run_id TEXT, ticker TEXT, action TEXT, target_pct REAL
        );
    """)
    return db, conn


def _seed_run(conn, run_id, run_date, candidates, trades, created_at=None):
    conn.execute(
        "INSERT INTO pipeline_runs VALUES (?, ?, ?)",
        (run_id, run_date, created_at or f"{run_date}T09:30:00"),
    )
    for c in candidates:
        conn.execute(
            "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, c["ticker"], "candidate", c["mu"],
             c.get("sigma", 0.3), c["kelly"], c.get("blocked_by")),
        )
    for t in trades:
        conn.execute(
            "INSERT INTO trades VALUES (?, ?, 'buy', ?)",
            (run_id, t["ticker"], t["target_pct"]),
        )
    conn.commit()


class TestClassifyReason:
    def test_pre_selection(self):
        assert _classify_reason("wash_sale") == "pre_selection_blocked"
        assert _classify_reason("sector") == "pre_selection_blocked"

    def test_sizing_failure(self):
        assert _classify_reason("buy_blocked") == "sizing_failed"
        assert _classify_reason("size_insufficient_cash") == "sizing_failed"

    def test_selected_submitted(self):
        assert _classify_reason("broker_pending_submitted") == "selected_submitted"

    def test_broker_outcome(self):
        assert _classify_reason("broker_skip:some_reason") == "broker_outcome"

    def test_unclassified(self):
        assert _classify_reason("unknown_reason") == "unclassified"


class TestComputeBuySideTC:
    def test_measured_tc(self, tmp_path):
        db, conn = _create_runs_db(tmp_path)
        candidates = [
            {"ticker": "AAPL", "mu": 0.05, "kelly": 0.08},
            {"ticker": "MSFT", "mu": 0.04, "kelly": 0.06},
            {"ticker": "GOOG", "mu": 0.06, "kelly": 0.10},
            {"ticker": "AMZN", "mu": 0.03, "kelly": 0.04},
            {"ticker": "META", "mu": 0.07, "kelly": 0.12},
        ]
        trades = [
            {"ticker": "AAPL", "target_pct": 0.08},
            {"ticker": "GOOG", "target_pct": 0.09},
            {"ticker": "META", "target_pct": 0.11},
        ]
        _seed_run(conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)
        result = compute_buy_side_tc(conn, "2026-07-01-live-abc")

        assert result is not None
        assert result["category"] == "measured"
        assert result["buy_side_tc"] is not None
        assert -1.0 <= result["buy_side_tc"] <= 1.0
        assert result["n_eligible"] == 5
        assert result["n_bought"] == 3

    def test_no_deployment(self, tmp_path):
        db, conn = _create_runs_db(tmp_path)
        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(5)
        ]
        _seed_run(conn, "2026-07-01-live-abc", "2026-07-01", candidates, [])
        result = compute_buy_side_tc(conn, "2026-07-01-live-abc")

        assert result is not None
        assert result["category"] == "no_deployment"
        assert result["buy_side_tc"] is None

    def test_too_few_eligible(self, tmp_path):
        db, conn = _create_runs_db(tmp_path)
        candidates = [
            {"ticker": "AAPL", "mu": 0.05, "kelly": 0.08},
        ]
        _seed_run(conn, "2026-07-01-live-abc", "2026-07-01", candidates, [])
        result = compute_buy_side_tc(conn, "2026-07-01-live-abc")
        assert result is None

    def test_pre_selection_excluded_from_corr(self, tmp_path):
        db, conn = _create_runs_db(tmp_path)
        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(5)
        ]
        candidates[0]["blocked_by"] = "wash_sale"
        candidates[1]["blocked_by"] = "sector"
        trades = [{"ticker": "T2", "target_pct": 0.08}]
        _seed_run(conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)
        result = compute_buy_side_tc(conn, "2026-07-01-live-abc")

        assert result is not None
        assert result["n_survived_admission"] == 3

    def test_zero_dispersion(self, tmp_path):
        db, conn = _create_runs_db(tmp_path)
        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(5)
        ]
        trades = [
            {"ticker": f"T{i}", "target_pct": 0.08}
            for i in range(5)
        ]
        _seed_run(conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)
        result = compute_buy_side_tc(conn, "2026-07-01-live-abc")

        assert result is not None
        assert result["category"] == "zero_dispersion"
        assert result["buy_side_tc"] is None


class TestRunMeasurement:
    def test_end_to_end(self, tmp_path):
        runs_db, runs_conn = _create_runs_db(tmp_path)
        ledger_db = tmp_path / "ledger.db"

        candidates = [
            {"ticker": "AAPL", "mu": 0.05, "kelly": 0.08},
            {"ticker": "MSFT", "mu": 0.04, "kelly": 0.06},
            {"ticker": "GOOG", "mu": 0.06, "kelly": 0.10},
            {"ticker": "AMZN", "mu": 0.03, "kelly": 0.04},
            {"ticker": "META", "mu": 0.07, "kelly": 0.12},
        ]
        for i in range(85):
            candidates.append(
                {"ticker": f"PAD{i}", "mu": 0.035, "kelly": 0.05}
            )

        trades = [
            {"ticker": "AAPL", "target_pct": 0.08},
            {"ticker": "GOOG", "target_pct": 0.09},
            {"ticker": "META", "target_pct": 0.11},
        ]
        _seed_run(runs_conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)

        summary = run_measurement(runs_db, ledger_db)

        assert summary["n_canonical_runs"] == 1
        assert summary["n_new_computed"] == 1
        assert summary["n_written"] == 1
        assert summary["tc_n_measured"] >= 0

        summary2 = run_measurement(runs_db, ledger_db)
        assert summary2["n_new_computed"] == 0
        assert summary2["n_written"] == 0

    def test_dry_run(self, tmp_path):
        runs_db, runs_conn = _create_runs_db(tmp_path)
        ledger_db = tmp_path / "ledger.db"

        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(90)
        ]
        trades = [{"ticker": "T0", "target_pct": 0.08}]
        _seed_run(runs_conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)

        summary = run_measurement(runs_db, ledger_db, dry_run=True)

        assert summary["n_new_computed"] == 1
        assert summary["n_written"] == 0

    def test_empty_db(self, tmp_path):
        runs_db, _ = _create_runs_db(tmp_path)
        ledger_db = tmp_path / "ledger.db"

        summary = run_measurement(runs_db, ledger_db)

        assert summary["n_canonical_runs"] == 0
        assert summary["n_new_computed"] == 0

    def test_rerun_supersedes_prior_canonical(self, tmp_path):
        """A later rerun becoming the new canonical run for an
        already-measured day must REPLACE that day's row, not add a
        second one (Codex round-3 review on #391: persistence was keyed
        by run_id, not run_date, so a rerun would double-count the day
        in the rolling summary)."""
        runs_db, runs_conn = _create_runs_db(tmp_path)
        ledger_db = tmp_path / "ledger.db"

        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(90)
        ]
        trades_a = [{"ticker": "T0", "target_pct": 0.08}]
        _seed_run(
            runs_conn, "2026-07-01-live-runA", "2026-07-01",
            candidates, trades_a, created_at="2026-07-01T09:30:00",
        )
        run_measurement(runs_db, ledger_db)

        # A later rerun for the SAME trading day, with a later created_at,
        # becomes the new canonical run and buys a different name.
        trades_b = [{"ticker": "T1", "target_pct": 0.08}]
        _seed_run(
            runs_conn, "2026-07-01-live-runB", "2026-07-01",
            candidates, trades_b, created_at="2026-07-01T15:00:00",
        )
        summary2 = run_measurement(runs_db, ledger_db)

        ledger_conn = sqlite3.connect(str(ledger_db))
        rows = ledger_conn.execute(
            "SELECT run_id, run_date FROM tc_metrics WHERE run_date='2026-07-01'"
        ).fetchall()
        assert len(rows) == 1, f"expected exactly one row for the day, got {rows}"
        assert rows[0][0] == "2026-07-01-live-runB"
        assert summary2["tc_n_measured"] == 1

    def test_dry_run_never_creates_ledger_db(self, tmp_path):
        """--dry-run must never create or write decision_ledger.db — even
        opening it read-write / enabling WAL / calling _ensure_table()
        violates the advertised 'compute but don't persist' contract
        (Codex round-3 review on #391)."""
        runs_db, runs_conn = _create_runs_db(tmp_path)
        ledger_db = tmp_path / "ledger.db"

        candidates = [
            {"ticker": f"T{i}", "mu": 0.05, "kelly": 0.08}
            for i in range(90)
        ]
        trades = [{"ticker": "T0", "target_pct": 0.08}]
        _seed_run(runs_conn, "2026-07-01-live-abc", "2026-07-01", candidates, trades)

        assert not ledger_db.exists()
        summary = run_measurement(runs_db, ledger_db, dry_run=True)
        assert summary["n_new_computed"] == 1
        assert not ledger_db.exists(), (
            "dry-run created decision_ledger.db — persistence contract violated"
        )


class TestDefaultRunsDbResolution:
    """main()'s default --runs-db must resolve through the canonical
    runtime_paths.default_data_root() authority, never a hard-coded
    workstation path (Codex review on #391: RQ_ROOT / ~/git/github/RenQuant
    is a machine-specific default a standing scheduled job cannot trust)."""

    def test_default_runs_db_matches_canonical_data_root(self):
        assert DEFAULT_RUNS_DB == default_data_root() / "data" / "runs.alpaca.db"

    def test_default_runs_db_honors_data_root_env_at_import(self, tmp_path):
        # DEFAULT_RUNS_DB is a module-level constant computed at import time,
        # so proving it is genuinely DERIVED (not a value that merely looks
        # similar) requires a fresh interpreter with the env var set before
        # import — patching os.environ post-import wouldn't move it.
        repo_src = Path(__file__).resolve().parents[1] / "src"
        env = dict(os.environ)
        env["RENQUANT_DATA_ROOT"] = str(tmp_path)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(repo_src)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        result = subprocess.run(
            [sys.executable, "-c",
             "from renquant_orchestrator.tc_measurement import DEFAULT_RUNS_DB; "
             "print(DEFAULT_RUNS_DB)"],
            capture_output=True, text=True, env=env, check=True,
        )
        assert result.stdout.strip() == str(tmp_path / "data" / "runs.alpaca.db")
