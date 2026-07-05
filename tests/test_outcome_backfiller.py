"""Tests for decision outcome backfiller."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.outcome_backfiller import (
    _map_gate,
    backfill,
    main,
)
from renquant_orchestrator.decision_ledger import DDL as LEDGER_DDL
from renquant_orchestrator.ledger_attribution import OUTCOMES_DDL


def _make_runs_db(path):
    """Create a minimal runs.alpaca.db with candidate_scores + ticker_forward_returns."""
    con = sqlite3.connect(str(path))
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
        CREATE TABLE ticker_forward_returns (
            as_of_date TEXT,
            ticker TEXT,
            close_price REAL,
            fwd_1d REAL,
            fwd_5d REAL,
            fwd_10d REAL,
            fwd_20d REAL,
            updated_at TEXT,
            fwd_60d REAL,
            PRIMARY KEY (as_of_date, ticker)
        );
    """)
    return con


def _insert_run(con, run_id, run_date):
    con.execute(
        "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)",
        (run_id, run_date, "live", "renquant-104", "2026-07-01T00:00:00"),
    )


def _insert_candidate(con, run_id, ticker, selected=0, blocked_by=None):
    con.execute(
        "INSERT INTO candidate_scores (run_id, ticker, role, selected, blocked_by) "
        "VALUES (?,?,?,?,?)",
        (run_id, ticker, "candidate", selected, blocked_by),
    )


def _insert_fwd(con, date, ticker, fwd_5d=0.01, fwd_20d=0.02, fwd_60d=0.03, close=100.0):
    con.execute(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?,?)",
        (date, ticker, close, None, fwd_5d, None, fwd_20d, "2026-07-01", fwd_60d),
    )


class TestMapGate:
    def test_selected_allow(self):
        gate, verdict = _map_gate(None, 1)
        assert gate == "admission"
        assert verdict == "allow"

    def test_not_selected_block(self):
        gate, verdict = _map_gate(None, 0)
        assert gate == "qp_not_selected"
        assert verdict == "block"

    def test_veto_prefix(self):
        gate, verdict = _map_gate("veto:rank_score_below_floor", 0)
        assert gate == "VetoWeakBuys"
        assert verdict == "block"

    def test_regime_prefix(self):
        gate, verdict = _map_gate("regime_admission:failed:BULL_CALM", 0)
        assert gate == "RegimeAdmission"
        assert verdict == "block"

    def test_conviction_prefix(self):
        gate, verdict = _map_gate("conviction:mu_below_floor", 0)
        assert gate == "ConvictionGate"
        assert verdict == "block"

    def test_fundamentals(self):
        gate, verdict = _map_gate("panel_fundamentals_missing", 0)
        assert gate == "FundamentalsFail"
        assert verdict == "block"

    def test_kelly(self):
        gate, verdict = _map_gate("kelly_zero:capped_zero", 0)
        assert gate == "KellySizing"
        assert verdict == "block"

    def test_unknown_prefix(self):
        gate, verdict = _map_gate("something_new:reason", 0)
        assert gate.startswith("other:")
        assert verdict == "block"

    def test_empty_string_selected(self):
        gate, verdict = _map_gate("", 1)
        assert gate == "admission"
        assert verdict == "allow"


class TestBackfill:
    def test_basic_backfill(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_candidate(con, "run-1", "GOOG", selected=0, blocked_by="veto:rank_score_below_floor")
        _insert_fwd(con, "2026-06-10", "AAPL", fwd_5d=0.01, fwd_20d=0.03, fwd_60d=0.05)
        _insert_fwd(con, "2026-06-10", "GOOG", fwd_5d=-0.02, fwd_20d=-0.01, fwd_60d=0.01)
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db)
        assert result["runs_scanned"] == 1
        assert result["outcomes_prepared"] == 2
        assert result["outcomes_written"] == 2
        assert result["skipped_no_forward_returns"] == 0

        ledger_con = sqlite3.connect(str(ledger_db))
        rows = ledger_con.execute("SELECT * FROM decision_outcomes").fetchall()
        assert len(rows) == 2

    def test_missing_forward_returns(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db)
        assert result["outcomes_prepared"] == 0
        assert result["skipped_no_forward_returns"] == 1

    def test_dry_run(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db, dry_run=True)
        assert result["dry_run"] is True
        assert result["outcomes_prepared"] == 1
        assert result["outcomes_written"] == 0
        assert not ledger_db.exists()

    def test_date_filter(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-01")
        _insert_run(con, "run-2", "2026-06-15")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_candidate(con, "run-2", "GOOG", selected=1)
        _insert_fwd(con, "2026-06-01", "AAPL")
        _insert_fwd(con, "2026-06-15", "GOOG")
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db, start_date="2026-06-10")
        assert result["runs_scanned"] == 1
        assert result["outcomes_prepared"] == 1

    def test_idempotent(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        con.commit()
        con.close()

        r1 = backfill(runs_db, ledger_db)
        r2 = backfill(runs_db, ledger_db)
        assert r1["outcomes_written"] == 1
        assert r2["outcomes_written"] == 0

    def test_multiple_runs(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_run(con, "run-2", "2026-06-11")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_candidate(con, "run-1", "GOOG", selected=0, blocked_by="conviction:mu_below_floor")
        _insert_candidate(con, "run-2", "AAPL", selected=0, blocked_by="regime_admission:failed:BULL_CALM")
        _insert_candidate(con, "run-2", "MSFT", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        _insert_fwd(con, "2026-06-10", "GOOG")
        _insert_fwd(con, "2026-06-11", "AAPL")
        _insert_fwd(con, "2026-06-11", "MSFT")
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db)
        assert result["runs_scanned"] == 2
        assert result["outcomes_prepared"] == 4
        assert result["outcomes_written"] == 4

    def test_non_live_runs_excluded(self, tmp_path):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)",
            ("sim-1", "2026-06-10", "simulation", "renquant-104", "2026-07-01"),
        )
        _insert_candidate(con, "sim-1", "AAPL", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        con.commit()
        con.close()

        result = backfill(runs_db, ledger_db)
        assert result["runs_scanned"] == 0
        assert result["outcomes_prepared"] == 0


class TestCLI:
    def test_missing_runs_db(self, tmp_path, capsys):
        rc = main(["--runs-db", str(tmp_path / "nope.db")])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_dry_run_output(self, tmp_path, capsys):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        con.commit()
        con.close()

        rc = main(["--runs-db", str(runs_db), "--ledger-db", str(ledger_db), "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry run" in out

    def test_json_output(self, tmp_path, capsys):
        runs_db = tmp_path / "runs.db"
        ledger_db = tmp_path / "ledger.db"
        con = _make_runs_db(runs_db)
        _insert_run(con, "run-1", "2026-06-10")
        _insert_candidate(con, "run-1", "AAPL", selected=1)
        _insert_fwd(con, "2026-06-10", "AAPL")
        con.commit()
        con.close()

        rc = main(["--runs-db", str(runs_db), "--ledger-db", str(ledger_db), "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["outcomes_written"] == 1
