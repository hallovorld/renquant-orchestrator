"""Candidate-level L3 dataset: label join, exclusion counting, widest-run
selection, regime join semantics. Tmp DBs only."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from renquant_orchestrator import l3_candidate_dataset as l3c


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "runs.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT,"
                    " run_type TEXT, created_at TEXT)")
        con.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT,"
                    " role TEXT, panel_score REAL, raw_score REAL,"
                    " rank_score REAL, mu REAL, sigma REAL,"
                    " expected_return REAL, sector TEXT, active_scorer TEXT,"
                    " selected INTEGER, blocked_by TEXT, kelly_target_pct REAL)")
        con.execute("CREATE TABLE live_state_snapshots (run_date TEXT,"
                    " regime TEXT, confidence REAL, created_at TEXT)")
        con.execute("CREATE TABLE ticker_forward_returns (ticker TEXT,"
                    " as_of_date TEXT, fwd_20d REAL, fwd_60d REAL)")
    return db


def _fill(db, rows):
    with sqlite3.connect(db) as con:
        for table, r in rows:
            q = f"INSERT INTO {table} VALUES ({','.join('?' * len(r))})"
            con.execute(q, r)


def test_label_join_widest_run_and_exclusion_count(tmp_path):
    db = _db(tmp_path)
    _fill(db, [
        ("pipeline_runs", ("r-small", "2026-01-05", "live", "2026-01-05 14:00:00")),
        ("pipeline_runs", ("r-wide", "2026-01-05", "live", "2026-01-05 14:05:00")),
        # small run: 1 candidate; wide run: 2 -> wide must win
        ("candidate_scores", ("r-small", "ZZZ", "candidate", 9.0, 1, 1, 0.1, 0.2, 0.05, "software", "xgb", 0, None, 0.1)),
        ("candidate_scores", ("r-wide", "AAPL", "candidate", 2.0, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 1, None, 0.1)),
        ("candidate_scores", ("r-wide", "MSFT", "candidate", 1.0, 1, 1, 0.0, 0.2, 0.01, "giant_tech", "xgb", 0, "wash_sale", 0.0)),
        ("live_state_snapshots", ("2026-01-05", "BULL_CALM", 0.7, "2026-01-05 21:00:00")),
        ("ticker_forward_returns", ("AAPL", "2026-01-05", 0.03, 0.08)),
        # MSFT has no forward row -> excluded and counted
    ])
    rows, manifest = l3c.build_rows(db)
    assert manifest["n_rows"] == 1 and manifest["n_candidates_without_forward_row_excluded"] == 1
    r = rows[0]
    assert r["ticker"] == "AAPL" and r["run_id"] == "r-wide"
    assert r["win"] == 1 and r["fwd_60d"] == 0.08
    assert r["regime"] == "BULL_CALM" and r["regime_source"] == "snapshot"
    assert r["selected"] == 1 and r["n_candidates_that_date"] == 2
    assert manifest["rows_by_run_type"] == {"live": 1}


def test_equal_width_tie_breaks_to_latest_created_at(tmp_path):
    """AUDIT REGRESSION GUARD: equal-width same-date runs must resolve to the
    latest created_at (the canonical run), never SQLite group order — else
    training silently reads a superseded retry's payload."""
    db = _db(tmp_path)
    _fill(db, [
        # r-early sorts first lexically AND by insertion; only the created_at
        # tie-break makes r-late win
        ("pipeline_runs", ("r-early", "2026-01-05", "live", "2026-01-05 14:00:00")),
        ("pipeline_runs", ("r-late", "2026-01-05", "live", "2026-01-05 21:00:00")),
        # both runs: width 2, materially different payloads
        ("candidate_scores", ("r-early", "AAPL", "candidate", 9.0, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 0, None, 0.1)),
        ("candidate_scores", ("r-early", "MSFT", "candidate", 8.0, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 0, None, 0.1)),
        ("candidate_scores", ("r-late", "AAPL", "candidate", 2.0, 1, 1, 0.3, 0.2, 0.07, "giant_tech", "xgb", 1, None, 0.2)),
        ("candidate_scores", ("r-late", "NVDA", "candidate", 1.0, 1, 1, 0.2, 0.2, 0.06, "giant_tech", "xgb", 0, None, 0.1)),
        ("ticker_forward_returns", ("AAPL", "2026-01-05", 0.03, 0.08)),
        ("ticker_forward_returns", ("MSFT", "2026-01-05", 0.01, 0.02)),
        ("ticker_forward_returns", ("NVDA", "2026-01-05", 0.02, 0.04)),
    ])
    rows, manifest = l3c.build_rows(db)
    assert {r["run_id"] for r in rows} == {"r-late"}
    assert {r["ticker"] for r in rows} == {"AAPL", "NVDA"}
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["panel_score"] == 2.0 and aapl["selected"] == 1
    assert manifest["n_rows"] == 2 and manifest["n_dates"] == 1


def test_absent_regime_is_recorded_not_invented(tmp_path):
    db = _db(tmp_path)
    _fill(db, [
        ("pipeline_runs", ("r1", "2026-01-06", "sim", "2026-01-06 14:00:00")),
        ("candidate_scores", ("r1", "AAPL", "candidate", 2.0, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 0, None, 0.1)),
        ("ticker_forward_returns", ("AAPL", "2026-01-06", -0.01, -0.02)),
    ])
    rows, _ = l3c.build_rows(db)
    assert rows[0]["regime"] is None and rows[0]["regime_source"] == "absent"
    assert rows[0]["win"] == 0


def test_cli_writes_and_refuses_empty(tmp_path, capsys):
    db = _db(tmp_path)  # empty tables
    out = tmp_path / "ds" / "cand.csv"
    assert l3c.main(["--db", str(db), "--out", str(out)]) == 1
    assert "zero labelled candidate rows" in capsys.readouterr().out
    _fill(db, [
        ("pipeline_runs", ("r1", "2026-01-05", "live", "2026-01-05 14:00:00")),
        ("candidate_scores", ("r1", "AAPL", "candidate", 2.0, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 1, None, 0.1)),
        ("ticker_forward_returns", ("AAPL", "2026-01-05", 0.03, 0.08)),
    ])
    assert l3c.main(["--db", str(db), "--out", str(out)]) == 0
    m = json.loads(out.with_suffix(".manifest.json").read_text())
    assert m["schema"] == l3c.SCHEMA and m["primary_horizon"] == "fwd_20d"


def test_equal_width_tie_breaks_to_latest_created_at(tmp_path):
    """r1 fixture: two same-date runs with EQUAL width but disagreeing
    payloads — the later created_at run must win, deterministically."""
    db = _db(tmp_path)
    _fill(db, [
        ("pipeline_runs", ("r-early", "2026-01-07", "live", "2026-01-07 14:00:00")),
        ("pipeline_runs", ("r-late",  "2026-01-07", "live", "2026-01-07 21:00:00")),
        # equal width (1 candidate each), materially different payloads
        ("candidate_scores", ("r-early", "AAPL", "candidate", 9.9, 1, 1, 0.9, 0.2, 0.5, "giant_tech", "xgb", 1, None, 0.9)),
        ("candidate_scores", ("r-late",  "AAPL", "candidate", 1.1, 1, 1, 0.1, 0.2, 0.05, "giant_tech", "xgb", 0, None, 0.1)),
        ("ticker_forward_returns", ("AAPL", "2026-01-07", 0.02, 0.05)),
    ])
    rows, _ = l3c.build_rows(db)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r-late"        # later canonical run wins
    assert rows[0]["panel_score"] == 1.1         # its payload, not r-early's
