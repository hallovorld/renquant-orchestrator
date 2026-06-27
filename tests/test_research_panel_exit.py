"""Tests for the read-only panel-exit predictiveness study (synthetic ledger, no network).

The study reads ONLY the decision ledger (candidate_scores + ticker_forward_returns +
pipeline_runs) — it trains no model. These tests build a tiny synthetic SQLite ledger and assert
that the within-date per-date-block statistics read the planted signal correctly.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rpe", Path(__file__).resolve().parent.parent / "scripts" / "research_panel_exit_predictiveness.py")
rpe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rpe)


def _mk_ledger(path: Path, *, regime: str, fired_fwd: float, kept_fwd: float, n_dates: int = 30,
               n_names: int = 12):
    """A ledger where the bottom-floor names (lowest panel + mu<=0) realize ``fired_fwd`` and the
    rest realize ``kept_fwd``, repeated over ``n_dates`` distinct dates, one run per date."""
    con = sqlite3.connect(str(path))
    con.execute("create table pipeline_runs (run_id text primary key, run_date date, regime text)")
    con.execute("create table candidate_scores (run_id text, ticker text, panel_score real, mu real)")
    con.execute("create table ticker_forward_returns (as_of_date date, ticker text, fwd_60d real)")
    import datetime as _dt
    n_bottom = max(1, int(n_names * 0.20))
    for i in range(n_dates):
        d = (_dt.date(2024, 1, 1) + _dt.timedelta(days=i)).isoformat()
        rid = f"{d}-sim-r{i}"
        con.execute("insert into pipeline_runs values (?,?,?)", (rid, d, regime))
        for j in range(n_names):
            tk = f"T{j}"
            is_bottom = j < n_bottom
            panel = -1.0 + j * 0.1          # ascending → first names are the bottom
            mu = -0.01 if is_bottom else 0.02
            fwd = fired_fwd if is_bottom else kept_fwd
            con.execute("insert into candidate_scores values (?,?,?,?)", (rid, tk, panel, mu))
            con.execute("insert into ticker_forward_returns values (?,?,?)", (d, tk, fwd))
    con.commit()
    con.close()


def test_predictive_regime_reads_as_predictive(tmp_path):
    db = tmp_path / "runs.db"
    _mk_ledger(db, regime="BULL_CALM", fired_fwd=-0.08, kept_fwd=+0.02)
    res = rpe.evaluate(db, horizon=60, min_xsec=8)
    bc = res["by_regime"]["BULL_CALM"]["and_fired_minus_kept_fwd"]
    assert bc["mean"] is not None and bc["mean"] < 0
    assert bc["t"] is not None and bc["t"] < -2
    assert "PREDICTIVE" in res["by_regime"]["BULL_CALM"]["reading"]
    assert res["bull_calm_verdict"] == "BULL_CALM_PREDICTIVE"


def test_inverted_regime_reads_as_inverted(tmp_path):
    db = tmp_path / "runs.db"
    # bottom names realize MORE than the kept names → exiting them loses alpha
    _mk_ledger(db, regime="BULL_CALM", fired_fwd=+0.10, kept_fwd=-0.01)
    res = rpe.evaluate(db, horizon=60, min_xsec=8)
    assert "INVERTED" in res["by_regime"]["BULL_CALM"]["reading"]
    assert res["bull_calm_verdict"] == "BULL_CALM_MISFIRE"


def test_one_run_per_date_dedup(tmp_path):
    """A duplicate, smaller re-run of the same date must not double-count the date."""
    db = tmp_path / "runs.db"
    _mk_ledger(db, regime="BULL_CALM", fired_fwd=-0.08, kept_fwd=+0.02, n_dates=30)
    con = sqlite3.connect(str(db))
    # add a SECOND, smaller run for an existing date (fewer names) — should be ignored
    con.execute("insert into pipeline_runs values (?,?,?)",
                ("2024-01-01-sim-dup", "2024-01-01", "BULL_CALM"))
    con.execute("insert into candidate_scores values (?,?,?,?)",
                ("2024-01-01-sim-dup", "T0", -1.0, -0.01))
    con.execute("insert into ticker_forward_returns values (?,?,?)",
                ("2024-01-01", "T0", +99.0))  # absurd value that would skew if double-counted
    con.commit(); con.close()
    res = rpe.evaluate(db, horizon=60, min_xsec=8)
    # 30 distinct dates regardless of the duplicate run
    assert res["by_regime"]["BULL_CALM"]["and_fired_minus_kept_fwd"]["n_dates"] == 30


def test_block_stat_basic():
    s = rpe._block_stat([-0.1, -0.1, -0.1, -0.1])
    assert s["n_dates"] == 4 and s["mean"] is not None and s["mean"] < 0
    assert s["pct_days_negative"] == 1.0
    empty = rpe._block_stat([float("nan"), float("inf")])
    assert empty["n_dates"] == 0 and empty["mean"] is None
