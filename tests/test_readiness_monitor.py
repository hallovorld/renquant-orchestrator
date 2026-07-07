"""Tests for the data-accumulation readiness monitor."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from renquant_orchestrator.intraday_quote_logger import default_tick_feed_path
from renquant_orchestrator.readiness_monitor import (
    ALL_CHECKS,
    CheckResult,
    Status,
    check_collector_liveness,
    check_decision_ledger,
    check_fmp_coverage,
    check_gate_verdict_freshness,
    check_intraday_corpus,
    check_lambda_sweep,
    check_oos_pick_table,
    check_parking_sleeve_shadow,
    check_pit_features,
    check_pit_snapshots,
    check_readonly_sessions,
    check_tc_baseline,
    check_trading_days,
    main,
    record_transitions,
    run_all_checks,
)

_OPS_PIT_DIR = Path(__file__).resolve().parent.parent / "ops" / "pit"
if str(_OPS_PIT_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_PIT_DIR))
import pit_liveness_check as liveness  # noqa: E402


def _write_valid_pit_day(snapshot_dir, day: str) -> None:
    """Write a snapshot day that PASSES check_snapshot()'s real 4-endpoint
    publication contract (all manifests present, status=='ok', as_of
    matching, referenced parquet present + non-empty)."""
    day_dir = snapshot_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    for endpoint in liveness.ENDPOINTS:
        parquet_name = f"{endpoint}.parquet"
        (day_dir / parquet_name).write_bytes(b"not-empty")
        (day_dir / f"{endpoint}.manifest.json").write_text(json.dumps({
            "status": "ok", "as_of": day, "output": parquet_name,
        }))


def _write_partial_pit_day(snapshot_dir, day: str) -> None:
    """Write a day dir that fails the contract — some endpoints missing."""
    day_dir = snapshot_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    endpoint = liveness.ENDPOINTS[0]
    parquet_name = f"{endpoint}.parquet"
    (day_dir / parquet_name).write_bytes(b"not-empty")
    (day_dir / f"{endpoint}.manifest.json").write_text(json.dumps({
        "status": "ok", "as_of": day, "output": parquet_name,
    }))


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

    def test_partial_days_not_counted(self, data_root):
        # Codex's exact concern: a dir that merely EXISTS (partial/crashed
        # publish, missing endpoints) must not inflate the count.
        snap_dir = data_root / "data" / "estimate_snapshots"
        today = dt.date.today()
        for i in range(10):
            day = (today - dt.timedelta(days=i)).isoformat()
            _write_valid_pit_day(snap_dir, day)
        for i in range(10, 15):
            day = (today - dt.timedelta(days=i)).isoformat()
            _write_partial_pit_day(snap_dir, day)
        r = check_pit_snapshots(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 10  # only the 10 valid days count

    def test_arbitrary_named_dirs_do_not_mark_ready(self, data_root):
        # The exact pre-fix failure mode: 90 arbitrarily-named (bare, no
        # manifest) directories must NOT report READY.
        snap_dir = data_root / "data" / "estimate_snapshots"
        today = dt.date.today()
        for i in range(95):
            (snap_dir / (today - dt.timedelta(days=i)).isoformat()).mkdir()
        r = check_pit_snapshots(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 0

    def test_ready(self, data_root):
        snap_dir = data_root / "data" / "estimate_snapshots"
        today = dt.date.today()
        for i in range(95):
            day = (today - dt.timedelta(days=i)).isoformat()
            _write_valid_pit_day(snap_dir, day)
        r = check_pit_snapshots(data_root)
        assert r.status == Status.READY
        assert r.current >= 90

    def test_not_ready_when_stale(self, data_root):
        # >=90 valid days, but the latest valid day is old — accrual has
        # lapsed, so this must not report READY even though the count clears
        # the threshold.
        snap_dir = data_root / "data" / "estimate_snapshots"
        anchor = dt.date.today() - dt.timedelta(days=10)
        for i in range(95):
            day = (anchor - dt.timedelta(days=i)).isoformat()
            _write_valid_pit_day(snap_dir, day)
        r = check_pit_snapshots(data_root)
        assert r.status == Status.NOT_READY
        assert r.current >= 90
        assert "STALE" in r.detail


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

def _write_tick_feed(data_root, records) -> None:
    feed = default_tick_feed_path(data_root)
    feed.parent.mkdir(parents=True, exist_ok=True)
    with feed.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


class TestIntradayCorpus:
    def test_no_feed(self, tmp_path):
        r = check_intraday_corpus(tmp_path)
        assert r.status == Status.UNKNOWN
        assert r.authoritative is False

    def test_reads_real_tick_feed_not_a_fictional_directory(self, data_root):
        # Round-3 regression: the OLD check counted directories under
        # data/intraday/, a path the real N1 collector never writes to.
        # Creating that fictional directory structure must NOT be what
        # this check reads.
        for t in ["AAPL", "GOOG", "MSFT"]:
            (data_root / "data" / "intraday" / t).mkdir()
        r = check_intraday_corpus(data_root)
        assert r.status == Status.UNKNOWN  # no real tick feed written yet
        assert r.current == 0

    def test_counts_distinct_days_and_tickers_from_real_feed(self, data_root):
        _write_tick_feed(data_root, [
            {"date": "2026-07-01", "ticker": "AAPL"},
            {"date": "2026-07-01", "ticker": "GOOG"},
            {"date": "2026-07-02", "ticker": "AAPL"},
            {"date": "2026-07-03", "ticker": "AAPL"},
        ])
        r = check_intraday_corpus(data_root)
        assert r.current == 3  # 3 distinct days, not 4 records or 2 tickers
        assert "3 distinct trading day" in r.detail
        assert "2 distinct ticker" in r.detail

    def test_always_informational_never_feeds_ready_aggregate(self, data_root):
        # Even with a large, healthy-looking corpus, this check must stay
        # UNKNOWN/non-authoritative — there is no frozen N_days target to
        # gate READY on (per Codex round-3).
        _write_tick_feed(data_root, [
            {"date": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", "ticker": "AAPL"}
            for i in range(200)
        ])
        r = check_intraday_corpus(data_root)
        assert r.status == Status.UNKNOWN
        assert r.authoritative is False


# ---------------------------------------------------------------------------
# Readonly sessions
# ---------------------------------------------------------------------------

class TestReadonlySessions:
    def test_no_dir(self, data_root):
        r = check_readonly_sessions(data_root)
        assert r.status == Status.UNKNOWN
        assert r.current == 0
        assert r.authoritative is False

    def test_partial(self, data_root):
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(3):
            (sess_dir / f"session_{i}.json").write_text("{}")
        r = check_readonly_sessions(data_root)
        assert r.current == 3
        assert r.authoritative is False

    def test_many_files_still_not_authoritative(self, data_root):
        # Round-3 regression: file presence alone must never report READY
        # or feed the aggregate — six arbitrary/unreplayed session files
        # are not "5 clean sessions" per Codex's review.
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(6):
            (sess_dir / f"session_{i}.json").write_text("{}")
        r = check_readonly_sessions(data_root)
        assert r.status == Status.UNKNOWN
        assert r.authoritative is False
        assert "does NOT verify" in r.detail


# ---------------------------------------------------------------------------
# Decision ledger
# ---------------------------------------------------------------------------

from renquant_orchestrator.decision_ledger import DDL as _LEDGER_DDL
from renquant_orchestrator.ledger_attribution import OUTCOMES_DDL as _OUTCOMES_DDL


def _aged_date(days_old: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days_old)).isoformat()


def _write_ledger_row(conn, *, run_id, as_of, scope, gate, verdict="allow"):
    conn.execute(
        "INSERT INTO decision_ledger (run_id, as_of, scope, gate, verdict, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, as_of, scope, gate, verdict, "test"),
    )


def _write_outcome_row(conn, *, as_of, scope, ticker, gate, verdict="allow", fwd_60d_ret=0.01):
    conn.execute(
        "INSERT INTO decision_outcomes "
        "(as_of, scope, ticker, gate, verdict, fwd_60d_ret, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (as_of, scope, ticker, gate, verdict, fwd_60d_ret, dt.datetime.utcnow().isoformat()),
    )


class TestDecisionLedger:
    def test_no_db(self, tmp_path):
        r = check_decision_ledger(tmp_path / "nope.db")
        assert r.status == Status.UNKNOWN

    def test_no_ledger_table(self, tmp_path):
        path = tmp_path / "ledger.db"
        sqlite3.connect(str(path)).close()
        r = check_decision_ledger(path)
        assert r.status == Status.NOT_READY

    def test_ledger_without_outcomes_table(self, tmp_path):
        path = tmp_path / "ledger.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_LEDGER_DDL)
        conn.commit()
        conn.close()
        r = check_decision_ledger(path)
        assert r.status == Status.NOT_READY
        assert "decision_outcomes" in r.detail

    def test_no_aged_decisions(self, tmp_path):
        # Both tables exist but every decision is recent (<60d old) — none
        # are old enough for a fwd_60d_ret to have resolved yet.
        path = tmp_path / "ledger.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_LEDGER_DDL)
        conn.executescript(_OUTCOMES_DDL)
        _write_ledger_row(conn, run_id="r1", as_of=_aged_date(5), scope="daily", gate="P-WF-GATE")
        conn.commit()
        conn.close()
        r = check_decision_ledger(path)
        assert r.status == Status.NOT_READY
        assert r.current == 0

    def test_partial_coverage(self, tmp_path):
        path = tmp_path / "ledger.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_LEDGER_DDL)
        conn.executescript(_OUTCOMES_DDL)
        # 3 aged (gate, scope) decisions, only 1 has a matching outcome.
        _write_ledger_row(conn, run_id="r1", as_of=_aged_date(70), scope="daily", gate="P-WF-GATE")
        _write_ledger_row(conn, run_id="r2", as_of=_aged_date(75), scope="daily", gate="P-FUND-FRESHNESS")
        _write_ledger_row(conn, run_id="r3", as_of=_aged_date(80), scope="daily", gate="P-SECTOR-CAP")
        _write_outcome_row(conn, as_of=_aged_date(70), scope="daily", ticker="AAPL", gate="P-WF-GATE")
        conn.commit()
        conn.close()
        r = check_decision_ledger(path)
        assert r.status == Status.NOT_READY
        assert r.current == pytest.approx(33.3, abs=0.1)

    def test_full_coverage(self, tmp_path):
        path = tmp_path / "ledger.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_LEDGER_DDL)
        conn.executescript(_OUTCOMES_DDL)
        for i, gate in enumerate(["P-WF-GATE", "P-FUND-FRESHNESS", "P-SECTOR-CAP"]):
            as_of = _aged_date(70 + i)
            _write_ledger_row(conn, run_id=f"r{i}", as_of=as_of, scope="daily", gate=gate)
            _write_outcome_row(conn, as_of=as_of, scope="daily", ticker="AAPL", gate=gate)
        conn.commit()
        conn.close()
        r = check_decision_ledger(path)
        assert r.status == Status.READY
        assert r.current == 100.0

    def test_recent_unaged_decisions_excluded_from_coverage(self, tmp_path):
        # A recent (<60d) decision with NO outcome must not drag down the
        # coverage ratio — it isn't old enough to expect one yet.
        path = tmp_path / "ledger.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_LEDGER_DDL)
        conn.executescript(_OUTCOMES_DDL)
        _write_ledger_row(conn, run_id="r1", as_of=_aged_date(70), scope="daily", gate="P-WF-GATE")
        _write_outcome_row(conn, as_of=_aged_date(70), scope="daily", ticker="AAPL", gate="P-WF-GATE")
        _write_ledger_row(conn, run_id="r2", as_of=_aged_date(5), scope="daily", gate="P-SECTOR-CAP")
        conn.commit()
        conn.close()
        r = check_decision_ledger(path)
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
# Parking sleeve shadow (S7)
# ---------------------------------------------------------------------------

def _write_sleeve_shadow(data_root, rows) -> Path:
    log_path = (
        data_root / "backtesting" / "renquant_104" / "logs"
        / "parking_sleeve_shadow.jsonl"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return log_path


class TestParkingSleeveShadow:
    def test_no_log(self, data_root):
        r = check_parking_sleeve_shadow(data_root)
        assert r.status == Status.NOT_READY
        assert r.authoritative is False
        assert r.current == 0

    def test_legacy_direct_schema_counts_session_dates(self, data_root):
        _write_sleeve_shadow(data_root, [
            {"as_of": "2026-07-01", "spy_frac": 0.2},
            {"as_of": "2026-07-02", "spy_frac": 0.1},
            {"as_of": "2026-07-02", "spy_frac": 0.0},
        ])
        r = check_parking_sleeve_shadow(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 2
        assert "schema=legacy_direct" in r.detail

    def test_runtime_wrapped_schema_reaches_10_session_milestone(self, data_root):
        rows = []
        for i in range(10):
            rows.append({
                "session_date": f"2026-07-{i+1:02d}",
                "book_state": {
                    "session_date": f"2026-07-{i+1:02d}",
                    "sleeve_contribution_pct": 0.0,
                },
                "spy_frac": 0.25,
            })
        r = check_parking_sleeve_shadow(data_root)
        assert r.status == Status.NOT_READY  # file not written yet
        _write_sleeve_shadow(data_root, rows)
        r = check_parking_sleeve_shadow(data_root)
        assert r.status == Status.READY
        assert r.current == 10
        assert r.authoritative is False
        assert "schema=runtime_wrapped" in r.detail

    def test_empty_or_unreadable_file_not_ready(self, data_root):
        _write_sleeve_shadow(data_root, [])
        r = check_parking_sleeve_shadow(data_root)
        assert r.status == Status.NOT_READY
        assert "no readable JSON records" in r.detail


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
# Collector liveness (N1)
# ---------------------------------------------------------------------------

class TestCollectorLiveness:
    def test_no_files(self, tmp_path):
        r = check_collector_liveness(tmp_path)
        assert r.status == Status.NOT_READY
        assert r.authoritative is False

    def test_tick_feed_only(self, data_root):
        feed = data_root / "data" / "rq105" / "intraday_tick_feed.jsonl"
        feed.parent.mkdir(parents=True, exist_ok=True)
        records = [{"session_date": f"2026-07-0{i+1}", "ticker": "AAPL"} for i in range(4)]
        with open(feed, "w") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        r = check_collector_liveness(data_root)
        assert r.status == Status.READY
        assert r.authoritative is False
        assert r.current >= 3

    def test_below_threshold(self, data_root):
        feed = data_root / "data" / "rq105" / "intraday_tick_feed.jsonl"
        feed.parent.mkdir(parents=True, exist_ok=True)
        with open(feed, "w") as fh:
            fh.write(json.dumps({"session_date": "2026-07-01", "ticker": "AAPL"}) + "\n")
        r = check_collector_liveness(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == 1


# ---------------------------------------------------------------------------
# FMP coverage (N3)
# ---------------------------------------------------------------------------

def _populate_fmp_harvest(data_root, tickers, *, age_days=1):
    harvest_dir = data_root / "data" / "fmp_harvest"
    harvest_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    df = pd.DataFrame({"symbol": tickers, "value": range(len(tickers))})
    path = harvest_dir / "earnings_latest.parquet"
    df.to_parquet(path)
    import os, time
    target = time.time() - age_days * 86400
    os.utime(path, (target, target))


class TestFmpCoverage:
    def test_no_harvest_dir(self, data_root):
        r = check_fmp_coverage(data_root)
        assert r.status == Status.NOT_READY

    def test_empty_parquet(self, data_root):
        harvest_dir = data_root / "data" / "fmp_harvest"
        harvest_dir.mkdir(parents=True, exist_ok=True)
        r = check_fmp_coverage(data_root)
        assert r.status == Status.NOT_READY

    def test_no_watchlist_returns_unknown_non_authoritative(self, data_root):
        _populate_fmp_harvest(data_root, ["AAPL", "GOOG", "MSFT"])
        r = check_fmp_coverage(data_root)
        assert r.status == Status.UNKNOWN
        assert r.authoritative is False

    def test_fresh_high_coverage(self, data_root):
        tickers = [f"T{i}" for i in range(100)]
        _populate_fmp_harvest(data_root, tickers, age_days=1)
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": tickers[:98]})
        )
        r = check_fmp_coverage(data_root)
        assert r.status == Status.READY
        assert r.current >= 95.0

    def test_stale_harvest_fails(self, data_root):
        tickers = [f"T{i}" for i in range(100)]
        _populate_fmp_harvest(data_root, tickers, age_days=20)
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": tickers})
        )
        r = check_fmp_coverage(data_root)
        assert r.status == Status.NOT_READY
        assert "STALE" in r.detail

    def test_low_coverage(self, data_root):
        _populate_fmp_harvest(data_root, ["AAPL"], age_days=1)
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": ["AAPL", "GOOG", "MSFT", "AMZN", "NVDA"]})
        )
        r = check_fmp_coverage(data_root)
        assert r.status == Status.NOT_READY
        assert r.current == pytest.approx(20.0)

    def test_only_latest_file_evaluated(self, data_root):
        """Stale files must not contribute to coverage (Codex #336 review)."""
        import pandas as pd
        harvest_dir = data_root / "data" / "fmp_harvest"
        harvest_dir.mkdir(parents=True, exist_ok=True)
        tickers = [f"T{i}" for i in range(100)]
        old_df = pd.DataFrame({"symbol": tickers, "value": range(100)})
        old_path = harvest_dir / "earnings_2026_01.parquet"
        old_df.to_parquet(old_path)
        new_df = pd.DataFrame({"symbol": ["T0"], "value": [1]})
        new_path = harvest_dir / "earnings_2026_07.parquet"
        new_df.to_parquet(new_path)
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": tickers})
        )
        r = check_fmp_coverage(data_root)
        assert r.current == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TC baseline (S-TC)
# ---------------------------------------------------------------------------

class TestTcBaseline:
    def test_no_db(self, tmp_path):
        r = check_tc_baseline(tmp_path / "nope.db")
        assert r.status == Status.NOT_READY

    def test_no_table(self, db_path):
        r = check_tc_baseline(db_path)
        assert r.status == Status.NOT_READY

    def test_below_threshold(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE transfer_coefficient "
                     "(run_date DATE, tc REAL)")
        for i in range(5):
            conn.execute("INSERT INTO transfer_coefficient VALUES (?, ?)",
                         (f"2026-07-0{i+1}", 0.5 + i * 0.01))
        conn.commit()
        conn.close()
        r = check_tc_baseline(db_path)
        assert r.status == Status.NOT_READY
        assert r.current == 5

    def test_above_threshold(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE transfer_coefficient "
                     "(run_date DATE, tc REAL)")
        for i in range(15):
            conn.execute("INSERT INTO transfer_coefficient VALUES (?, ?)",
                         (f"2026-06-{i+10:02d}", 0.5))
        conn.commit()
        conn.close()
        r = check_tc_baseline(db_path)
        assert r.status == Status.READY
        assert r.current == 15


# ---------------------------------------------------------------------------
# OOS pick table (S8)
# ---------------------------------------------------------------------------

def _populate_oos_pick_table(data_root):
    import pandas as pd
    exp_dir = data_root / "data" / "exp"
    exp_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02"],
        "ticker": ["AAPL", "GOOG"],
        "score": [0.1, 0.2],
    })
    df.to_parquet(exp_dir / "oos_pick_table_v1.parquet")


class TestOosPickTable:
    def test_no_exp_dir(self, data_root):
        r = check_oos_pick_table(data_root)
        assert r.status == Status.NOT_READY

    def test_no_parquet(self, data_root):
        (data_root / "data" / "exp").mkdir(parents=True, exist_ok=True)
        r = check_oos_pick_table(data_root)
        assert r.status == Status.NOT_READY

    def test_empty_parquet(self, data_root):
        import pandas as pd
        exp_dir = data_root / "data" / "exp"
        exp_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_parquet(exp_dir / "oos_pick_table_v1.parquet")
        r = check_oos_pick_table(data_root)
        assert r.status == Status.NOT_READY

    def test_valid_table(self, data_root):
        _populate_oos_pick_table(data_root)
        r = check_oos_pick_table(data_root)
        assert r.status == Status.READY
        assert r.current == 2


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

@pytest.fixture()
def ledger_db_path(tmp_path):
    """An unpopulated ledger DB path — always passed explicitly so tests
    never fall through to check_decision_ledger's real-machine default
    (~/renquant-data/decision_ledger.db)."""
    return tmp_path / "ledger_test.db"


def _write_fully_covered_ledger(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_LEDGER_DDL)
    conn.executescript(_OUTCOMES_DDL)
    for i, gate in enumerate(["P-WF-GATE", "P-FUND-FRESHNESS", "P-SECTOR-CAP"]):
        as_of = _aged_date(70 + i)
        _write_ledger_row(conn, run_id=f"r{i}", as_of=as_of, scope="daily", gate=gate)
        _write_outcome_row(conn, as_of=as_of, scope="daily", ticker="AAPL", gate=gate)
    conn.commit()
    conn.close()


class TestRunAllChecks:
    def test_all_checks_run(self, data_root, db_path, ledger_db_path):
        results = run_all_checks(data_root=data_root, db_path=db_path,
                                  ledger_db_path=ledger_db_path)
        assert len(results) == len(ALL_CHECKS)
        for r in results:
            assert isinstance(r.status, Status)

    def test_s10_and_m1_are_marked_non_authoritative(
        self, data_root, db_path, ledger_db_path,
    ):
        results = run_all_checks(data_root=data_root, db_path=db_path,
                                  ledger_db_path=ledger_db_path)
        s10 = next(r for r in results if r.name == "S10_intraday_symbols_present")
        m1 = next(r for r in results if r.name == "M1_session_logs_observed")
        s7 = next(r for r in results if r.name == "S7_parking_sleeve_shadow")
        assert s10.authoritative is False
        assert m1.authoritative is False
        assert s7.authoritative is False

    def test_decision_ledger_uses_its_own_db_not_the_shared_one(
        self, data_root, db_path, ledger_db_path,
    ):
        # check_decision_ledger's DB is a genuinely different file from the
        # shared runs.alpaca.db-backed checks (gate_verdicts, etc.) — the
        # exact schema/path mismatch this fix addresses.
        _write_fully_covered_ledger(ledger_db_path)
        results = run_all_checks(data_root=data_root, db_path=db_path,
                                  ledger_db_path=ledger_db_path)
        s5 = next(r for r in results if r.name == "S5_decision_ledger")
        assert s5.status == Status.READY


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_text_output(self, data_root, db_path, ledger_db_path, capsys):
        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--ledger-db", str(ledger_db_path)])
        out = capsys.readouterr().out
        assert "Readiness:" in out
        assert rc == 1

    def test_json_output(self, data_root, db_path, ledger_db_path, capsys):
        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--ledger-db", str(ledger_db_path), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == len(ALL_CHECKS)
        assert all("status" in d for d in data)

    def test_with_state_file(self, data_root, db_path, ledger_db_path, tmp_path, capsys):
        state = tmp_path / "state.json"
        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--ledger-db", str(ledger_db_path),
                    "--state-file", str(state)])
        assert state.exists()
        assert rc == 1

    def test_informational_checks_dont_block_zero_exit(
        self, data_root, db_path, ledger_db_path, capsys,
    ):
        # S10/M1/N1 are left completely unpopulated — they must not block rc==0.
        snap_dir = data_root / "data" / "estimate_snapshots"
        today = dt.date.today()
        for i in range(95):
            _write_valid_pit_day(snap_dir, (today - dt.timedelta(days=i)).isoformat())
        days = [f"2026-{m:02d}-{d:02d}" for m in range(4, 8) for d in range(1, 29)]
        manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
        manifest.write_text(json.dumps({"processed_days": days[:95]}))

        _write_fully_covered_ledger(ledger_db_path)

        # N3: populate FMP harvest + watchlist config
        _populate_fmp_harvest(data_root, [f"T{i}" for i in range(100)])
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": [f"T{i}" for i in range(100)]})
        )

        # S8: populate OOS pick table
        _populate_oos_pick_table(data_root)

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE config_experiments (id INTEGER PRIMARY KEY, config TEXT)")
        for i in range(50):
            conn.execute("INSERT INTO config_experiments (config) VALUES (?)", (f"cfg{i}",))
        today_ = dt.date.today()
        conn.execute("INSERT INTO gate_verdicts VALUES (?, ?, ?)",
                     ("run-fresh", str(today_ - dt.timedelta(days=1)), "PASS"))
        for i in range(65):
            m = (i // 28) + 4
            d = (i % 28) + 1
            conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                         (f"run-{i}", f"2026-{m:02d}-{d:02d}", "live"))
        # S-TC: populate transfer_coefficient table
        conn.execute("CREATE TABLE transfer_coefficient (run_date DATE, tc REAL)")
        for i in range(15):
            conn.execute("INSERT INTO transfer_coefficient VALUES (?, ?)",
                         (f"2026-06-{i+10:02d}", 0.5))
        conn.commit()
        conn.close()

        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--ledger-db", str(ledger_db_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "S10_intraday_symbols_present" in out
        assert "M1_session_logs_observed" in out
        assert "[informational" in out

    def test_all_ready_returns_zero(self, data_root, db_path, ledger_db_path, capsys):
        snap_dir = data_root / "data" / "estimate_snapshots"
        today = dt.date.today()
        for i in range(95):
            _write_valid_pit_day(snap_dir, (today - dt.timedelta(days=i)).isoformat())
        days = [f"2026-{m:02d}-{d:02d}" for m in range(4, 8) for d in range(1, 29)]
        manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
        manifest.write_text(json.dumps({"processed_days": days[:95]}))
        _write_tick_feed(data_root, [{"date": "2026-07-01", "ticker": "AAPL"}])
        sess_dir = data_root / "data" / "105_sessions"
        sess_dir.mkdir(parents=True)
        for i in range(6):
            (sess_dir / f"session_{i}.json").write_text("{}")

        _write_fully_covered_ledger(ledger_db_path)

        # N3: populate FMP harvest + watchlist config
        _populate_fmp_harvest(data_root, [f"T{i}" for i in range(100)])
        config_dir = data_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "strategy_config.json").write_text(
            json.dumps({"watchlist": [f"T{i}" for i in range(100)]})
        )

        # S8: populate OOS pick table
        _populate_oos_pick_table(data_root)

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE config_experiments (id INTEGER PRIMARY KEY, config TEXT)")
        for i in range(50):
            conn.execute("INSERT INTO config_experiments (config) VALUES (?)", (f"cfg{i}",))
        today_ = dt.date.today()
        conn.execute("INSERT INTO gate_verdicts VALUES (?, ?, ?)",
                     ("run-fresh", str(today_ - dt.timedelta(days=1)), "PASS"))
        for i in range(65):
            m = (i // 28) + 4
            d = (i % 28) + 1
            conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                         (f"run-{i}", f"2026-{m:02d}-{d:02d}", "live"))
        # S-TC: populate transfer_coefficient table
        conn.execute("CREATE TABLE transfer_coefficient (run_date DATE, tc REAL)")
        for i in range(15):
            conn.execute("INSERT INTO transfer_coefficient VALUES (?, ?)",
                         (f"2026-06-{i+10:02d}", 0.5))
        conn.commit()
        conn.close()

        rc = main(["--data-root", str(data_root), "--db", str(db_path),
                    "--ledger-db", str(ledger_db_path)])
        assert rc == 0
