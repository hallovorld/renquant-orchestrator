"""Tests for the data-accumulation readiness monitor."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.readiness_monitor import (
    ALL_CHECKS,
    CheckResult,
    Status,
    check_decision_ledger,
    check_gate_verdict_freshness,
    check_intraday_corpus,
    check_lambda_sweep,
    check_pit_features,
    check_pit_snapshots,
    check_readonly_sessions,
    check_trading_days,
    main,
    record_transitions,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def data_root(tmp_path):
    """Minimal data root with structure for checks."""
    (tmp_path / "data" / "estimate_snapshots").mkdir(parents=True)
    (tmp_path / "data" / "pit_features").mkdir(parents=True)
    (tmp_path / "data" / "intraday").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def db_path(tmp_path):
    """DB with pipeline_runs and gate_verdicts tables."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE pipeline_runs (
        run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT)""")
    conn.execute("""CREATE TABLE gate_verdicts (
        run_id TEXT, run_date DATE, verdict TEXT)""")
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# PIT snapshot checks
# ---------------------------------------------------------------------------

class TestPitSnapshots:
    def test_no_dir(self, tmp_path):
        r = check_pit_snapshots(tmp_path)
        assert r.status == Status.UNKNOWN

    def test_empty(self, data_root):
        r = check_pit_snapshots(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 0

    def test_partial(self, data_root):
        snap_dir = data_root / "data" / "estimate_snapshots"
        for i in range(10):
            (snap_dir / f"2026-07-{i+1:02d}").mkdir()
        r = check_pit_snapshots(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 10
        assert r.pct == pytest.approx(11.1, abs=0.1)

    def test_ready(self, data_root):
        snap_dir = data_root / "data" / "estimate_snapshots"
        for i in range(95):
            d = 1 + i
            month = (d - 1) // 28 + 4
            day = (d - 1) % 28 + 1
            (snap_dir / f"2026-{month:02d}-{day:02d}").mkdir()
        r = check_pit_snapshots(data_root)
        assert r.status == Status.READY
        assert r.current >= 90


class TestPitFeatures:
    def test_no_manifest(self, data_root):
        r = check_pit_features(data_root)
        assert r.status == Status.UNKNOWN

    def test_partial_manifest(self, data_root):
        manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
        manifest.write_text(json.dumps({
            "processed_days": ["2026-07-02", "2026-07-03"]
        }))
        r = check_pit_features(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 2

    def test_ready_manifest(self, data_root):
        days = [f"2026-{m:02d}-{d:02d}" for m in range(4, 8) for d in range(1, 29)]
        manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
        manifest.write_text(json.dumps({"processed_days": days[:95]}))
        r = check_pit_features(data_root)
        assert r.status == Status.READY


# ---------------------------------------------------------------------------
# Intraday corpus
# ---------------------------------------------------------------------------

class TestIntradayCorpus:
    def test_no_dir(self, tmp_path):
        r = check_intraday_corpus(tmp_path)
        assert r.status == Status.UNKNOWN

    def test_partial(self, data_root):
        for t in ["AAPL", "GOOG", "MSFT"]:
            (data_root / "data" / "intraday" / t).mkdir()
        r = check_intraday_corpus(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 3

    def test_ready(self, data_root):
        for i in range(110):
            (data_root / "data" / "intraday" / f"TICK{i}").mkdir()
        r = check_intraday_corpus(data_root)
        assert r.status == Status.READY
        assert r.current == 110


# ---------------------------------------------------------------------------
# Readonly sessions
# ---------------------------------------------------------------------------

class TestReadonlySessions:
    def test_no_dir(self, data_root):
        r = check_readonly_sessions(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 0

    def test_partial(self, data_root):
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(3):
            (sess_dir / f"session_{i}.json").write_text("{}")
        r = check_readonly_sessions(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 3

    def test_ready(self, data_root):
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(6):
            (sess_dir / f"session_{i}.json").write_text("{}")
        r = check_readonly_sessions(data_root)
        assert r.status == Status.READY


# ---------------------------------------------------------------------------
# Decision ledger
# ---------------------------------------------------------------------------

class TestDecisionLedger:
    def test_no_db(self, tmp_path):
        r = check_decision_ledger(tmp_path / "nope.db")
        assert r.status == Status.UNKNOWN

    def test_no_table(self, db_path):
        r = check_decision_ledger(db_path)
        assert r.status == Status.NOT_READY

    def test_empty_table(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE decision_entries (
            id INTEGER PRIMARY KEY, ticker TEXT, fwd_return REAL)""")
        conn.commit()
        conn.close()
        r = check_decision_ledger(db_path)
        assert r.status == Status.NOT_READY
        assert r.current == 0

    def test_partial_coverage(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE decision_entries (
            id INTEGER PRIMARY KEY, ticker TEXT, fwd_return REAL)""")
        conn.executemany("INSERT INTO decision_entries (ticker, fwd_return) VALUES (?, ?)",
                         [("AAPL", 0.05), ("GOOG", None), ("MSFT", None)])
        conn.commit()
        conn.close()
        r = check_decision_ledger(db_path)
        assert r.status == Status.NOT_READY
        assert r.current == pytest.approx(33.3, abs=0.1)

    def test_full_coverage(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE decision_entries (
            id INTEGER PRIMARY KEY, ticker TEXT, fwd_return REAL)""")
        for t in ["AAPL", "GOOG", "MSFT", "AMZN", "META"]:
            conn.execute("INSERT INTO decision_entries (ticker, fwd_return) VALUES (?, ?)",
                         (t, 0.03))
        conn.commit()
        conn.close()
        r = check_decision_ledger(db_path)
        assert r.status == Status.READY
        assert r.current == 100.0


# ---------------------------------------------------------------------------
# Gate verdict freshness
# ---------------------------------------------------------------------------

class TestGateVerdict:
    def test_no_db(self, tmp_path):
        r = check_gate_verdict_freshness(tmp_path / "nope.db")
        assert r.status == Status.UNKNOWN

    def test_no_verdicts(self, db_path):
        r = check_gate_verdict_freshness(db_path)
        assert r.status == Status.NOT_READY

    def test_stale_verdict(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO gate_verdicts VALUES (?, ?, ?)",
                     ("run-old", "2026-01-01", "PASS"))
        conn.commit()
        conn.close()
        r = check_gate_verdict_freshness(db_path)
        assert r.status == Status.NOT_READY

    def test_fresh_verdict(self, db_path):
        from datetime import date as d, timedelta
        today = d.today()
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO gate_verdicts VALUES (?, ?, ?)",
                     ("run-fresh", str(today - timedelta(days=3)), "PASS"))
        conn.commit()
        conn.close()
        r = check_gate_verdict_freshness(db_path)
        assert r.status == Status.READY
        assert r.current == 3


# ---------------------------------------------------------------------------
# Lambda sweep
# ---------------------------------------------------------------------------

class TestLambdaSweep:
    def test_no_table(self, db_path):
        r = check_lambda_sweep(db_path)
        assert r.status == Status.NOT_READY

    def test_partial(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE config_experiments (id INTEGER PRIMARY KEY, config TEXT)")
        for i in range(10):
            conn.execute("INSERT INTO config_experiments (config) VALUES (?)", (f"cfg{i}",))
        conn.commit()
        conn.close()
        r = check_lambda_sweep(db_path)
        assert r.status == Status.NOT_READY
        assert r.current == 10


# ---------------------------------------------------------------------------
# Trading days baseline
# ---------------------------------------------------------------------------

class TestTradingDays:
    def test_no_db(self, tmp_path):
        r = check_trading_days(tmp_path / "nope.db")
        assert r.status == Status.UNKNOWN

    def test_below_threshold(self, db_path):
        conn = sqlite3.connect(str(db_path))
        for i in range(30):
            conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                         (f"run-{i}", f"2026-06-{i+1:02d}", "live"))
        conn.commit()
        conn.close()
        r = check_trading_days(db_path)
        assert r.status == Status.NOT_READY
        assert r.current == 30

    def test_above_threshold(self, db_path):
        conn = sqlite3.connect(str(db_path))
        for i in range(65):
            m = (i // 28) + 4
            d = (i % 28) + 1
            conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                         (f"run-{i}", f"2026-{m:02d}-{d:02d}", "live"))
        conn.commit()
        conn.close()
        r = check_trading_days(db_path)
        assert r.status == Status.READY


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

class TestTransitions:
    def test_first_run_no_transitions(self, tmp_path):
        state_file = tmp_path / "state.json"
        results = [
            CheckResult("a", Status.NOT_READY, 0, 10, "test"),
            CheckResult("b", Status.READY, 10, 10, "test"),
        ]
        transitions = record_transitions(results, state_file)
        assert transitions == []
        assert state_file.exists()

    def test_transition_detected(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"a": "NOT_READY", "b": "READY"}))
        results = [
            CheckResult("a", Status.READY, 10, 10, "now ready"),
            CheckResult("b", Status.READY, 10, 10, "still ready"),
        ]
        transitions = record_transitions(results, state_file)
        assert len(transitions) == 1
        assert transitions[0] == ("a", Status.NOT_READY, Status.READY)
        log = tmp_path / "state.transitions.jsonl"
        assert log.exists()

    def test_regression_detected(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"a": "READY"}))
        results = [CheckResult("a", Status.NOT_READY, 5, 10, "regressed")]
        transitions = record_transitions(results, state_file)
        assert len(transitions) == 1
        assert transitions[0] == ("a", Status.READY, Status.NOT_READY)


# ---------------------------------------------------------------------------
# run_all_checks integration
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    def test_all_checks_run(self, data_root, db_path):
        results = run_all_checks(data_root=data_root, db_path=db_path)
        assert len(results) == len(ALL_CHECKS)
        for r in results:
            assert isinstance(r.status, Status)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_text_output(self, data_root, db_path, capsys):
        rc = main(["--data-root", str(data_root), "--db", str(db_path)])
        out = capsys.readouterr().out
        assert "Readiness:" in out
        assert rc == 1

    def test_json_output(self, data_root, db_path, capsys):
        rc = main(["--data-root", str(data_root), "--db", str(db_path), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == len(ALL_CHECKS)
        assert all("status" in d for d in data)

    def test_with_state_file(self, data_root, db_path, tmp_path, capsys):
        state = tmp_path / "state.json"
        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--state-file", str(state)])
        assert state.exists()
        assert rc == 1

    def test_all_ready_returns_zero(self, data_root, db_path, capsys):
        snap_dir = data_root / "data" / "estimate_snapshots"
        for i in range(95):
            m = (i // 28) + 4
            d = (i % 28) + 1
            (snap_dir / f"2026-{m:02d}-{d:02d}").mkdir()
        days = [f"2026-{m:02d}-{d:02d}" for m in range(4, 8) for d in range(1, 29)]
        manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
        manifest.write_text(json.dumps({"processed_days": days[:95]}))
        for i in range(110):
            (data_root / "data" / "intraday" / f"TICK{i}").mkdir()
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(6):
            (sess_dir / f"session_{i}.json").write_text("{}")

        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE decision_entries (
            id INTEGER PRIMARY KEY, ticker TEXT, fwd_return REAL)""")
        for t in ["AAPL", "GOOG", "MSFT", "AMZN", "META"]:
            conn.execute("INSERT INTO decision_entries (ticker, fwd_return) VALUES (?, ?)",
                         (t, 0.03))
        conn.execute("CREATE TABLE config_experiments (id INTEGER PRIMARY KEY, config TEXT)")
        for i in range(50):
            conn.execute("INSERT INTO config_experiments (config) VALUES (?)", (f"cfg{i}",))
        from datetime import date as dt, timedelta
        today = dt.today()
        conn.execute("INSERT INTO gate_verdicts VALUES (?, ?, ?)",
                     ("run-fresh", str(today - timedelta(days=1)), "PASS"))
        for i in range(65):
            m = (i // 28) + 4
            d = (i % 28) + 1
            conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                         (f"run-{i}", f"2026-{m:02d}-{d:02d}", "live"))
        conn.commit()
        conn.close()

        rc = main(["--data-root", str(data_root), "--db", str(db_path)])
        assert rc == 0
