"""Tests for cloud/result_store.py — crash-safe SQLite sweep persistence."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.cloud.result_store import ResultStore


@pytest.fixture
def store(tmp_path):
    s = ResultStore("test_sweep_001", tmp_path)
    s.init_sweep(
        backend="local",
        backtest_start="2024-01-02",
        backtest_end="2026-03-28",
        initial_cash=100_000.0,
        grid_spec={"entry_caps": [0.08, 0.12]},
        n_variants=2,
    )
    yield s
    s.close()


def _seed_row(seed, *, sharpe=1.0, apy=0.10, max_dd=0.05, calmar=2.0,
              sharpe_net_of_cost=None,
              per_regime=None):
    return {
        "seed": seed,
        "sharpe": sharpe,
        "sharpe_net_of_cost": sharpe_net_of_cost or sharpe,
        "apy": apy,
        "max_dd": max_dd,
        "calmar": calmar,
        "per_regime": per_regime or {
            "BULL_CALM": {"sharpe": sharpe, "sharpe_net_of_cost": sharpe,
                          "max_dd": max_dd, "apy": apy, "n_days": 200},
            "BEAR": {"sharpe": 0.5, "sharpe_net_of_cost": 0.5,
                     "max_dd": 0.10, "apy": -0.05, "n_days": 100},
        },
    }


class TestResultStore:
    def test_init_creates_tables(self, store):
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {t[0] for t in tables}
        assert "sweep_runs" in names
        assert "variant_results" in names
        assert "seed_metrics" in names
        assert "regime_metrics" in names

    def test_insert_variant_persists_immediately(self, store):
        store.insert_variant(
            "cap08_drift00_topup02", "candidate", "fp_abc",
            [_seed_row(42), _seed_row(43)],
            entry_cap=0.08, drift_buffer=0.0, topup_threshold=0.02,
        )
        rows = store._conn.execute(
            "SELECT variant_name FROM variant_results WHERE sweep_id = ?",
            ("test_sweep_001",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "cap08_drift00_topup02"

    def test_seed_metrics_persisted(self, store):
        store.insert_variant(
            "cap08", "candidate", "fp",
            [_seed_row(42, sharpe=1.5), _seed_row(43, sharpe=0.8)],
        )
        rows = store._conn.execute(
            "SELECT seed, sharpe FROM seed_metrics WHERE variant_name = ? ORDER BY seed",
            ("cap08",),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == (42, 1.5)
        assert rows[1] == (43, 0.8)

    def test_regime_metrics_persisted(self, store):
        store.insert_variant(
            "cap12", "candidate", "fp",
            [_seed_row(42, per_regime={
                "BULL_CALM": {"sharpe": 1.3, "sharpe_net_of_cost": 1.2,
                              "max_dd": 0.04, "apy": 0.15, "n_days": 180},
            })],
        )
        rows = store._conn.execute(
            "SELECT regime, sharpe, sharpe_net_of_cost, n_days FROM regime_metrics "
            "WHERE variant_name = ?",
            ("cap12",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0] == ("BULL_CALM", 1.3, 1.2, 180)

    def test_crash_recovery_preserves_partial_results(self, store):
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        store.insert_variant("v2", "candidate", "fp", [_seed_row(42)])
        db_path = store._db_path
        store.close()
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT variant_name FROM variant_results ORDER BY variant_name"
        ).fetchall()
        assert len(rows) == 2
        conn.close()

    def test_completed_variants(self, store):
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        store.insert_variant("v2", "candidate", "fp", [_seed_row(42)])
        assert store.completed_variants() == {"v1", "v2"}

    def test_insert_error(self, store):
        store.insert_error("v_bad", "OOM at bar 500")
        assert "v_bad" not in store.completed_variants()
        row = store._conn.execute(
            "SELECT error FROM variant_results WHERE variant_name = ?",
            ("v_bad",),
        ).fetchone()
        assert row[0] == "OOM at bar 500"

    def test_update_verdict(self, store):
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        verdict = {"tier3_ready": True, "criteria": {"1_bc_sharpe": True}}
        store.update_verdict("v1", verdict)
        row = store._conn.execute(
            "SELECT tier3_ready, verdict_json FROM variant_results WHERE variant_name = ?",
            ("v1",),
        ).fetchone()
        assert row[0] == 1
        assert json.loads(row[1])["tier3_ready"] is True

    def test_finalize(self, store):
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        store.update_verdict("v1", {"tier3_ready": False})
        store.finalize(total_seconds=120.0, cost_usd=2.50, aa_passed=True,
                       aa_sharpe_lift=0.001)
        row = store._conn.execute(
            "SELECT status, total_seconds, cost_usd, aa_passed FROM sweep_runs"
        ).fetchone()
        assert row[0] == "completed"
        assert row[1] == 120.0
        assert row[2] == 2.50
        assert row[3] == 1

    def test_resume_skips_completed(self, store):
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        store.insert_variant("v2", "candidate", "fp", [_seed_row(42)])
        all_variants = ["v1", "v2", "v3"]
        completed = store.completed_variants()
        remaining = [v for v in all_variants if v not in completed]
        assert remaining == ["v3"]

    def test_count_completed(self, store):
        assert store.count_completed() == 0
        store.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        assert store.count_completed() == 1
        store.insert_error("v_bad", "crash")
        assert store.count_completed() == 1

    def test_idempotent_init(self, tmp_path):
        s1 = ResultStore("sweep_x", tmp_path)
        s1.init_sweep(backend="local", backtest_start="2024-01-02",
                      backtest_end="2026-03-28", initial_cash=100_000,
                      grid_spec={}, n_variants=5)
        s1.insert_variant("v1", "candidate", "fp", [_seed_row(42)])
        s1.close()
        s2 = ResultStore("sweep_x", tmp_path)
        s2.init_sweep(backend="local", backtest_start="2024-01-02",
                      backtest_end="2026-03-28", initial_cash=100_000,
                      grid_spec={}, n_variants=5)
        assert s2.count_completed() == 1
        s2.close()
