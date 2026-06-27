"""Tests for the read-only renquant105 trend-signal baseline study (synthetic ledger, no network).

The study reads ONLY the decision ledger (candidate_scores + ticker_forward_returns +
pipeline_runs) — it trains no model and never writes to a canonical path. These tests build a
tiny synthetic SQLite ledger and assert that:
  * the rank-IC reads a planted monotone signal,
  * recall/precision and the MODEL-vs-GATE killed-winner decomposition read a planted case,
  * the data-sufficiency gate reports INSUFFICIENT_LIVE_HISTORY below --min-dates and does not
    fabricate a baseline,
  * the missing-DB path is a clean CI skip (exit 0).
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sqlite3
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rtsb", Path(__file__).resolve().parent.parent / "scripts" / "research_trend_signal_baseline.py")
rtsb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rtsb)


def _sessions_after(start: _dt.date, n: int):
    out, d = [], start
    while len(out) < n:
        d = d + _dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _mk_ledger(path: Path, *, n_dates: int, n_names: int = 20, run_type: str = "live",
               start: _dt.date = _dt.date(2024, 1, 1), trailing_sessions: int = 80,
               signal: bool = True):
    """A ledger where, on each date, mu is monotone in the realized fwd_20d (planted signal)
    when ``signal`` is True. ``trailing_sessions`` extra forward-return rows extend the session
    calendar so the 20-session horizon ages.
    """
    con = sqlite3.connect(str(path))
    con.execute("create table pipeline_runs (run_id text, run_date date, run_type text)")
    con.execute(
        "create table candidate_scores (run_id text, ticker text, raw_score real, mu real, "
        "selected integer, blocked_by text, model_type text, active_scorer text)")
    con.execute(
        "create table ticker_forward_returns (as_of_date date, ticker text, "
        "fwd_5d real, fwd_10d real, fwd_20d real, fwd_60d real)")
    dates = [d for d in _sessions_after(start, n_dates)]
    last = dates[-1]
    for i, d in enumerate(dates):
        rid = f"{run_type}-{d.isoformat()}"
        con.execute("insert into pipeline_runs values (?,?,?)", (rid, d.isoformat(), run_type))
        for j in range(n_names):
            # planted: higher mu -> higher fwd_20d (rank-IC ~ +1) when signal=True
            mu = (j - n_names / 2) / (n_names * 5.0)  # spread around 0
            fwd = (j / n_names - 0.5) * 0.2 if signal else ((n_names - j) / n_names - 0.5) * 0.2
            con.execute(
                "insert into candidate_scores values (?,?,?,?,?,?,?,?)",
                (rid, f"T{j}", mu * 10, mu, 0, None, "hf_patchtst", "hf_patchtst"))
            con.execute(
                "insert into ticker_forward_returns values (?,?,?,?,?,?)",
                (d.isoformat(), f"T{j}", fwd, fwd, fwd, fwd))
    # extend the session calendar so the horizon elapses (filler ticker, distinct as_of dates)
    for s in _sessions_after(last, trailing_sessions):
        con.execute("insert into ticker_forward_returns values (?,?,?,?,?,?)",
                    (s.isoformat(), "FILLER", 0.0, 0.0, 0.0, 0.0))
    con.commit()
    con.close()


def test_rank_ic_reads_planted_signal(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_dates=30, min_xsec=10,
                        as_of="2024-12-31")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["n_dates"] >= 30
    assert ic["mean_ic"] > 0.5  # strong planted monotone signal
    assert ic["above_leakage_floor"] is True


def test_inverted_signal_negative_ic(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=False)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_dates=30, min_xsec=10,
                        as_of="2024-12-31")
    ic = res["live"]["ic"]["fwd_20d"]["mu"]
    assert ic["mean_ic"] < 0  # inverted ranking -> negative IC


def test_sufficiency_gate_does_not_fabricate(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=12, signal=True)  # below min_dates=30
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_dates=30, min_xsec=10,
                        as_of="2024-12-31")
    assert res["data_sufficiency"]["verdict"] == "INSUFFICIENT_LIVE_HISTORY"
    assert res["live"]["sufficient"] is False


def test_killed_winner_decomposition_present(tmp_path):
    db = tmp_path / "led.db"
    _mk_ledger(db, n_dates=40, signal=True)
    res = rtsb.evaluate(db, book_size=8, mu_floor=0.03, min_dates=30, min_xsec=10,
                        as_of="2024-12-31")
    t = res["live"]["trend"]["fwd_20d"]
    # both legs of the decomposition are computed and in [0,1]
    assert t["missed_by_model"] is not None and 0.0 <= t["missed_by_model"] <= 1.0
    assert t["killed_by_gate"] is not None and 0.0 <= t["killed_by_gate"] <= 1.0
    # with a clean planted signal the model catches trends -> recall_topk > 0
    assert t["recall_topk"] > 0.0


def test_missing_db_is_clean_skip(capsys):
    rc = rtsb.main(["--runs-db", "/tmp/__rtsb_does_not_exist__.db"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out
