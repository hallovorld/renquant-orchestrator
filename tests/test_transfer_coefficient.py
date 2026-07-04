"""Tests for the transfer-coefficient measurement module (S-TC)."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.transfer_coefficient import (
    compute_tc_per_run,
    main,
    measure_tc,
    tc_decomposition,
    tc_summary,
)


@pytest.fixture()
def tc_db(tmp_path):
    """In-memory DB with candidate_scores + pipeline_runs for TC tests."""
    db_path = tmp_path / "tc_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE pipeline_runs (
        run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT,
        regime TEXT, portfolio_value REAL
    )""")
    conn.execute("""CREATE TABLE candidate_scores (
        run_id TEXT, ticker TEXT, role TEXT,
        kelly_target_pct REAL, qp_target_w REAL,
        mu REAL, sigma REAL, rank_score REAL,
        blocked_by TEXT, selected INTEGER,
        qp_status TEXT
    )""")

    runs = [
        ("run-2026-06-01-live-abc", "2026-06-01", "live", "BULL_CALM", 100000),
        ("run-2026-06-02-live-def", "2026-06-02", "live", "BULL_CALM", 101000),
        ("run-2026-06-03-live-ghi", "2026-06-03", "live", "BEAR", 99000),
        ("run-2026-06-04-live-jkl", "2026-06-04", "live", "BULL_CALM", 102000),
    ]
    conn.executemany(
        "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)", runs
    )

    scores = [
        # run 1: optimal — one blocked, rest shrunken
        ("run-2026-06-01-live-abc", "AAPL", "candidate", 0.10, 0.08, 0.05, 0.20, 0.8, None, 1, "optimal"),
        ("run-2026-06-01-live-abc", "GOOG", "candidate", 0.08, 0.06, 0.04, 0.18, 0.7, None, 1, "optimal"),
        ("run-2026-06-01-live-abc", "MSFT", "candidate", 0.06, 0.05, 0.03, 0.15, 0.6, None, 1, "optimal"),
        ("run-2026-06-01-live-abc", "AMZN", "candidate", 0.04, 0.00, 0.02, 0.25, 0.5, "vol_gate", 0, "optimal"),
        ("run-2026-06-01-live-abc", "META", "candidate", 0.03, 0.02, 0.01, 0.22, 0.4, None, 1, "optimal"),
        ("run-2026-06-01-live-abc", "NVDA", "candidate", 0.12, 0.09, 0.06, 0.30, 0.9, None, 1, "optimal"),
        # run 2: optimal — perfect TC (kelly == qp)
        ("run-2026-06-02-live-def", "AAPL", "candidate", 0.10, 0.10, 0.05, 0.20, 0.8, None, 1, "optimal"),
        ("run-2026-06-02-live-def", "GOOG", "candidate", 0.08, 0.08, 0.04, 0.18, 0.7, None, 1, "optimal"),
        ("run-2026-06-02-live-def", "MSFT", "candidate", 0.06, 0.06, 0.03, 0.15, 0.6, None, 1, "optimal"),
        ("run-2026-06-02-live-def", "AMZN", "candidate", 0.04, 0.04, 0.02, 0.25, 0.5, None, 1, "optimal"),
        ("run-2026-06-02-live-def", "META", "candidate", 0.03, 0.03, 0.01, 0.22, 0.4, None, 1, "optimal"),
        # run 3: infeasible — prior weights anti-correlated with kelly
        ("run-2026-06-03-live-ghi", "AAPL", "candidate", 0.10, 0.05, 0.05, 0.20, 0.8, None, 1, "infeasible:infeasible"),
        ("run-2026-06-03-live-ghi", "GOOG", "candidate", 0.08, 0.03, 0.04, 0.18, 0.7, None, 1, "infeasible:infeasible"),
        ("run-2026-06-03-live-ghi", "MSFT", "candidate", 0.06, 0.02, 0.03, 0.15, 0.6, None, 1, "infeasible:infeasible"),
        ("run-2026-06-03-live-ghi", "AMZN", "candidate", 0.04, 0.00, 0.02, 0.25, 0.5, "wash_sale", 0, "infeasible:infeasible"),
        ("run-2026-06-03-live-ghi", "META", "candidate", 0.03, 0.00, 0.01, 0.22, 0.4, "conviction", 0, "infeasible:infeasible"),
        ("run-2026-06-03-live-ghi", "NVDA", "candidate", 0.12, 0.06, 0.06, 0.30, 0.9, None, 1, "infeasible:infeasible"),
        # run 4: qp_status never stamped (pre-instrumentation run) — must NOT
        # be counted as "optimal"; the solver's actual outcome is unknown.
        ("run-2026-06-04-live-jkl", "AAPL", "candidate", 0.09, 0.09, 0.05, 0.20, 0.8, None, 1, None),
        ("run-2026-06-04-live-jkl", "GOOG", "candidate", 0.07, 0.07, 0.04, 0.18, 0.7, None, 1, None),
        ("run-2026-06-04-live-jkl", "MSFT", "candidate", 0.05, 0.05, 0.03, 0.15, 0.6, None, 1, None),
        ("run-2026-06-04-live-jkl", "AMZN", "candidate", 0.03, 0.03, 0.02, 0.25, 0.5, None, 1, None),
        ("run-2026-06-04-live-jkl", "META", "candidate", 0.02, 0.02, 0.01, 0.22, 0.4, None, 1, None),
    ]
    conn.executemany(
        "INSERT INTO candidate_scores VALUES (?,?,?,?,?,?,?,?,?,?,?)", scores
    )
    conn.commit()
    conn.close()
    return db_path


def test_compute_tc_per_run_basic(tc_db):
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    assert len(ts) == 4
    assert "tc" in ts.columns
    assert "tc_rank" in ts.columns
    assert all(ts["n_candidates"] >= 5)


def test_tc_perfect_correlation(tc_db):
    """Run 2 has kelly == qp for all candidates -> TC = 1.0."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    run2 = ts[ts["run_id"] == "run-2026-06-02-live-def"]
    assert len(run2) == 1
    assert abs(run2["tc"].iloc[0] - 1.0) < 1e-10


def test_tc_with_blocked_candidates(tc_db):
    """Run 1 has AMZN blocked (kelly=0.04, qp=0), TC should be < 1."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    run1 = ts[ts["run_id"] == "run-2026-06-01-live-abc"]
    assert len(run1) == 1
    tc = run1["tc"].iloc[0]
    assert 0.0 < tc < 1.0


def test_tc_heavy_shrinkage(tc_db):
    """Run 3 has 2 blocked + heavy shrinkage -> TC well below 1."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    run3 = ts[ts["run_id"] == "run-2026-06-03-live-ghi"]
    assert len(run3) == 1
    assert run3["tc"].iloc[0] < 1.0
    assert run3["max_shrinkage"].iloc[0] > 0


def test_tc_summary_stats(tc_db):
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    s = tc_summary(ts)
    assert s["n_runs"] == 4
    assert s["n_valid"] == 4
    assert "by_regime" in s


def test_tc_summary_empty():
    s = tc_summary(pd.DataFrame(columns=[
        "run_id", "run_date", "regime", "n_candidates",
        "tc", "tc_rank", "mean_kelly", "std_kelly",
        "mean_qp", "std_qp", "max_shrinkage",
    ]))
    assert s["n_runs"] == 0


def test_tc_decomposition_sources(tc_db):
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    decomp = tc_decomposition(conn, min_candidates=5)
    conn.close()
    assert decomp["n_runs"] == 4
    assert "blocked" in decomp["by_source"]
    assert "shrinkage" in decomp["by_source"]
    assert "expansion" in decomp["by_source"]
    total_frac = sum(
        decomp["by_source"][k]["frac_of_total"]
        for k in ("blocked", "shrinkage", "expansion")
    )
    assert abs(total_frac - 1.0) < 0.01


def test_measure_tc_end_to_end(tc_db):
    result = measure_tc(db_path=tc_db)
    assert "summary" in result
    assert "decomposition" in result
    assert "time_series" in result
    assert len(result["time_series"]) == 4
    assert result["summary"]["n_runs"] == 4


def test_min_candidates_filter(tc_db):
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=10)
    conn.close()
    assert len(ts) == 0


def test_tc_by_qp_status(tc_db):
    """TC breakdown by QP feasibility — the root cause diagnostic."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    s = tc_summary(ts)
    assert "by_qp_status" in s
    assert "optimal" in s["by_qp_status"]
    assert "infeasible" in s["by_qp_status"]
    assert s["by_qp_status"]["optimal"]["n"] == 2
    assert s["by_qp_status"]["infeasible"]["n"] == 1
    assert 0.0 < s["by_qp_status"]["optimal"]["frac_of_runs"] < 1.0


def test_tc_missing_qp_status_not_counted_as_optimal(tc_db):
    """A run whose qp_status was never stamped must land in its own
    'missing' bucket, not be silently folded into 'optimal' — a blank
    status is not evidence the solver succeeded."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    run4 = ts[ts["run_id"] == "run-2026-06-04-live-jkl"]
    assert run4["qp_status_category"].iloc[0] == "missing"
    assert bool(run4["qp_infeasible"].iloc[0]) is False

    s = tc_summary(ts)
    assert "missing" in s["by_qp_status"]
    assert s["by_qp_status"]["missing"]["n"] == 1
    assert s["by_qp_status"]["optimal"]["n"] == 2


def test_tc_qp_infeasible_flag(tc_db):
    """compute_tc_per_run stamps qp_infeasible per run."""
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    assert "qp_infeasible" in ts.columns
    run3 = ts[ts["run_id"] == "run-2026-06-03-live-ghi"]
    assert bool(run3["qp_infeasible"].iloc[0]) is True
    run1 = ts[ts["run_id"] == "run-2026-06-01-live-abc"]
    assert bool(run1["qp_infeasible"].iloc[0]) is False


def test_tc_regime_breakdown(tc_db):
    conn = sqlite3.connect(f"file:{tc_db}?mode=ro", uri=True)
    ts = compute_tc_per_run(conn, min_candidates=5)
    conn.close()
    s = tc_summary(ts)
    assert s["n_runs"] == 4
    # 3 BULL_CALM + 1 BEAR: only BULL_CALM has ≥3 runs
    assert list(s["by_regime"].keys()) == ["BULL_CALM"]
    assert s["by_regime"]["BULL_CALM"]["n"] == 3


def test_cli_text_output(tc_db, capsys):
    rc = main(["--db", str(tc_db), "--min-candidates", "5"])
    captured = capsys.readouterr()
    assert "Transfer Coefficient" in captured.out
    assert rc == 0 or rc == 1


def test_cli_json_output(tc_db, capsys):
    rc = main(["--db", str(tc_db), "--min-candidates", "5", "--json"])
    captured = capsys.readouterr()
    import json as _json
    data = _json.loads(captured.out)
    assert "summary" in data
    assert "decomposition" in data
    assert rc == 0 or rc == 1


def test_cli_no_data(tc_db, capsys):
    rc = main(["--db", str(tc_db), "--min-candidates", "999"])
    assert rc == 2
