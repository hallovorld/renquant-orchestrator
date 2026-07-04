"""Tests for S6 lambda sweep script — config experiment generation."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from s6_lambda_sweep import (
    _experiment_id,
    _qualifying_runs,
    LAMBDAS,
    MIN_CANDIDATES,
)


def _make_db(tmp_path):
    db_path = tmp_path / "runs.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT,
            run_type TEXT,
            strategy TEXT,
            created_at TEXT
        );
        CREATE TABLE candidate_scores (
            run_id TEXT,
            ticker TEXT,
            role TEXT,
            selected INTEGER DEFAULT 0,
            blocked_by TEXT,
            mu REAL,
            sigma REAL,
            raw_score REAL,
            rank_score REAL,
            panel_score REAL,
            rs_score REAL,
            expected_return REAL,
            kelly_target_pct REAL,
            model_type TEXT,
            sector TEXT,
            panel_ltr_artifact TEXT,
            expected_return_horizon_days INTEGER,
            mu_horizon_days INTEGER,
            qp_delta_w REAL,
            qp_target_w REAL,
            qp_status TEXT,
            active_scorer TEXT,
            legacy_model_type TEXT,
            PRIMARY KEY (run_id, ticker)
        );
        CREATE TABLE trades (
            run_id TEXT,
            ticker TEXT,
            target_pct REAL
        );
    """)
    return con, db_path


def _insert_run(con, run_id, run_date, n_candidates=50):
    con.execute(
        "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)",
        (run_id, run_date, "live", "renquant-104", f"{run_date}T00:00:00"),
    )
    for i in range(n_candidates):
        ticker = f"T{i:03d}"
        con.execute(
            "INSERT INTO candidate_scores "
            "(run_id, ticker, role, selected, mu, sigma) VALUES (?,?,?,?,?,?)",
            (run_id, ticker, "candidate" if i > 2 else "holding",
             1 if i < 5 else 0,
             0.01 + i * 0.001, 0.10 + i * 0.005),
        )
    con.commit()


class TestExperimentId:
    def test_deterministic(self):
        id1 = _experiment_id("run-1", 0.01)
        id2 = _experiment_id("run-1", 0.01)
        assert id1 == id2

    def test_different_for_different_lambda(self):
        id1 = _experiment_id("run-1", 0.01)
        id2 = _experiment_id("run-1", 0.05)
        assert id1 != id2

    def test_different_for_different_run(self):
        id1 = _experiment_id("run-1", 0.01)
        id2 = _experiment_id("run-2", 0.01)
        assert id1 != id2


class TestQualifyingRuns:
    def test_finds_qualifying_runs(self, tmp_path):
        con, _ = _make_db(tmp_path)
        _insert_run(con, "run-1", "2026-06-10", n_candidates=60)
        _insert_run(con, "run-2", "2026-06-11", n_candidates=60)
        runs = _qualifying_runs(con)
        assert len(runs) == 2

    def test_excludes_small_runs(self, tmp_path):
        con, _ = _make_db(tmp_path)
        _insert_run(con, "run-1", "2026-06-10", n_candidates=60)
        _insert_run(con, "run-small", "2026-06-11", n_candidates=10)
        runs = _qualifying_runs(con)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-1"

    def test_limit(self, tmp_path):
        con, _ = _make_db(tmp_path)
        for i in range(5):
            _insert_run(con, f"run-{i}", f"2026-06-{10+i:02d}", n_candidates=60)
        runs = _qualifying_runs(con, limit=2)
        assert len(runs) == 2

    def test_empty(self, tmp_path):
        con, _ = _make_db(tmp_path)
        runs = _qualifying_runs(con)
        assert runs == []

    def test_dedup_same_date(self, tmp_path):
        con, _ = _make_db(tmp_path)
        _insert_run(con, "run-1a", "2026-06-10", n_candidates=60)
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)",
            ("run-1b", "2026-06-10", "live", "renquant-104", "2026-06-10T12:00:00"),
        )
        for i in range(60):
            con.execute(
                "INSERT OR IGNORE INTO candidate_scores "
                "(run_id, ticker, role, mu, sigma) VALUES (?,?,?,?,?)",
                ("run-1b", f"T{i:03d}", "candidate", 0.01 + i * 0.001, 0.10),
            )
        con.commit()
        runs = _qualifying_runs(con)
        assert len(runs) == 1


class TestLambdaConfig:
    def test_lambda_values(self):
        assert 0.0 in LAMBDAS
        assert 0.01 in LAMBDAS
        assert 0.05 in LAMBDAS
        assert 0.10 in LAMBDAS

    def test_min_candidates(self):
        assert MIN_CANDIDATES >= 40
