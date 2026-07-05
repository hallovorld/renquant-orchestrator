"""Tests for config experiment store (S6 lambda sweep storage)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.config_experiment_store import (
    CONFIG_EXPERIMENTS_DDL,
    ensure_table,
    read_experiments,
    write_experiment,
    write_experiments,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    return conn


def _exp(experiment_id, run_date="2026-07-01", config_name="lambda_0.01",
         cash_drag_lambda=0.01, **kw):
    return {
        "experiment_id": experiment_id,
        "run_date": run_date,
        "config_name": config_name,
        "config": {"cash_drag_lambda": cash_drag_lambda},
        "cash_drag_lambda": cash_drag_lambda,
        "min_invested_pct": kw.get("min_invested_pct", 0.7),
        "turnover_max": kw.get("turnover_max", 0.15),
        "deployed_frac": kw.get("deployed_frac", 0.85),
        "n_names_selected": kw.get("n_names_selected", 5),
        "turnover": kw.get("turnover", 0.12),
        "max_weight": kw.get("max_weight", 0.12),
        "solver_status": kw.get("solver_status", "optimal"),
        "baseline_run_id": kw.get("baseline_run_id", "run-1"),
        "metrics": kw.get("metrics", {}),
        "created_at": "2026-07-01T00:00:00+00:00",
    }


class TestEnsureTable:
    def test_creates_table(self):
        conn = sqlite3.connect(":memory:")
        ensure_table(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "config_experiments" in tables

    def test_idempotent(self):
        conn = sqlite3.connect(":memory:")
        ensure_table(conn)
        ensure_table(conn)


class TestWriteExperiment:
    def test_insert(self):
        conn = _make_db()
        assert write_experiment(conn, _exp("exp-1"))
        rows = conn.execute("SELECT COUNT(*) FROM config_experiments").fetchone()[0]
        assert rows == 1

    def test_idempotent(self):
        conn = _make_db()
        assert write_experiment(conn, _exp("exp-1"))
        assert not write_experiment(conn, _exp("exp-1"))

    def test_fields_stored(self):
        conn = _make_db()
        write_experiment(conn, _exp("exp-1", cash_drag_lambda=0.05))
        row = conn.execute(
            "SELECT cash_drag_lambda, config_json FROM config_experiments"
        ).fetchone()
        assert row[0] == 0.05
        config = json.loads(row[1])
        assert config["cash_drag_lambda"] == 0.05


class TestWriteExperiments:
    def test_multiple(self):
        conn = _make_db()
        exps = [_exp(f"exp-{i}", config_name=f"lambda_{i}") for i in range(5)]
        n = write_experiments(conn, exps)
        assert n == 5

    def test_partial_duplicate(self):
        conn = _make_db()
        write_experiment(conn, _exp("exp-0"))
        exps = [_exp(f"exp-{i}") for i in range(3)]
        n = write_experiments(conn, exps)
        assert n == 2


class TestReadExperiments:
    def test_read_all(self):
        conn = _make_db()
        write_experiments(conn, [_exp(f"exp-{i}") for i in range(3)])
        rows = read_experiments(conn)
        assert len(rows) == 3

    def test_filter_by_config_name(self):
        conn = _make_db()
        write_experiment(conn, _exp("exp-a", config_name="lambda_0.01"))
        write_experiment(conn, _exp("exp-b", config_name="lambda_0.05"))
        rows = read_experiments(conn, config_name="lambda_0.01")
        assert len(rows) == 1
        assert rows[0]["experiment_id"] == "exp-a"

    def test_filter_by_date(self):
        conn = _make_db()
        write_experiment(conn, _exp("exp-a", run_date="2026-06-01"))
        write_experiment(conn, _exp("exp-b", run_date="2026-07-01"))
        rows = read_experiments(conn, start_date="2026-06-15")
        assert len(rows) == 1
        assert rows[0]["experiment_id"] == "exp-b"

    def test_empty_db(self):
        conn = _make_db()
        rows = read_experiments(conn)
        assert rows == []
