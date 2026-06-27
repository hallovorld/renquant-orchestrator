"""Tests for the conviction-gate outcome validator (no network, synthetic data)."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "validate_conviction_gate",
    Path(__file__).resolve().parent.parent / "scripts" / "validate_conviction_gate.py")
vcg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vcg)


def _mk_db(path: Path, rows):
    con = sqlite3.connect(str(path))
    con.execute("create table candidate_scores (run_id text, ticker text, expected_return real)")
    con.executemany("insert into candidate_scores values (?,?,?)", rows)
    con.commit(); con.close()


def _mk_ds(path: Path, rows):
    df = pd.DataFrame(rows, columns=["date", "ticker", "fwd_60d_excess"])
    df["regime_p_bull_calm"] = 1.0
    df["regime_p_bear"] = 0.0
    df["regime_p_bull_volatile"] = 0.0
    df.to_parquet(path, index=False)


def test_insufficient_aged_ledger(tmp_path):
    db = tmp_path / "runs.db"; ds = tmp_path / "ds.parquet"
    _mk_db(db, [("2026-06-24-live-aaa", "AAPL", 0.05)])
    _mk_ds(ds, [("2026-06-24", "AAPL", 0.10)])  # same date, but only 1 → below min
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30)
    assert res["status"] == "INSUFFICIENT_AGED_LEDGER"


def test_demean_better_when_drops_loser(tmp_path):
    db = tmp_path / "runs.db"; ds = tmp_path / "ds.parquet"
    import datetime as _dt
    csrows, dsrows = [], []
    # 40 DISTINCT aged dates; each has a HIGH-mu winner and a near-floor
    # (intercept) loser, plus low-mu names to pull the full-cross-section mean
    # down so demean keeps the winner and raw also admits the loser.
    for i in range(40):
        d = (_dt.date(2025, 1, 1) + _dt.timedelta(days=i)).isoformat()
        rid = f"{d}-live-r{i}"
        names = [("WIN", 0.060, +0.12), ("LOSE", 0.031, -0.05),
                 ("LO1", -0.01, 0.0), ("LO2", 0.0, 0.0), ("LO3", 0.005, 0.0)]
        for tk, mu, fwd in names:
            csrows.append((rid, f"{tk}{i}", mu))
            dsrows.append((d, f"{tk}{i}", fwd))
    _mk_db(db, csrows); _mk_ds(ds, dsrows)
    # as_of well after the 2025-01 dates → their 60d horizon has elapsed → aged
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30,
                       as_of="2025-06-01")
    assert res["status"] == "OK"
    # demean (full-cross-section) keeps the WIN (+0.12), raw also admits LOSE (-0.05)
    assert res["demean_minus_raw_mean_fwd"] > 0
    assert res["verdict"] == "DEMEAN_BETTER"
    # causal number: the names demean drops are realized losers
    assert res["dropped_by_demean_mean_fwd"] < 0
    # the OK verdict carries the directional/not-significance caveat
    assert "significance" in res["caveat"]


def test_not_yet_aged_rows_are_insufficient(tmp_path):
    # Codex #190: even with MANY dates AND fwd_60d present, if the 60d horizon has
    # NOT elapsed as of `as_of`, they must NOT count as aged → INSUFFICIENT.
    import datetime as _dt
    db = tmp_path / "runs.db"; ds = tmp_path / "ds.parquet"
    csrows, dsrows = [], []
    for i in range(40):  # 40 distinct dates, all "today-ish"
        d = (_dt.date(2026, 6, 1) + _dt.timedelta(days=i)).isoformat()
        csrows.append((f"{d}-live-r{i}", f"T{i}", 0.05))
        dsrows.append((d, f"T{i}", 0.10))  # fwd present but horizon not elapsed
    _mk_db(db, csrows); _mk_ds(ds, dsrows)
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30,
                       as_of="2026-06-20")  # < first date + 60d → none aged
    assert res["status"] == "INSUFFICIENT_AGED_LEDGER"
    assert res["aged_joined_dates"] == 0


def _mk_db_with_mu(path: Path, rows):
    """candidate_scores with a populated ``mu`` column (expected_return NULL),
    exercising the 2026-06-26 coalesce(mu, expected_return) ledger path."""
    con = sqlite3.connect(str(path))
    con.execute("create table candidate_scores "
                "(run_id text, ticker text, expected_return real, mu real)")
    con.executemany(
        "insert into candidate_scores (run_id, ticker, mu) values (?,?,?)", rows)
    con.commit(); con.close()


def test_rank_evidence_flags_demean_dropping_relative_underperformers(tmp_path):
    # Floor-free lens: mu rank perfectly predicts fwd, so the below-cross-section
    # names demean refuses are the realized relative losers. Also exercises the
    # mu-column ledger path (expected_return is NULL here, sim-style).
    import datetime as _dt
    db = tmp_path / "r.db"; ds = tmp_path / "d.parquet"
    csrows, dsrows = [], []
    for i in range(40):                       # 40 aged dates
        d = (_dt.date(2025, 1, 1) + _dt.timedelta(days=i)).isoformat()
        rid = f"{d}-sim-r{i}"
        for k in range(1, 11):                # 10-name cross-section, all mu>0
            mu = 0.01 * k                     # 0.01..0.10
            csrows.append((rid, f"T{k}_{i}", mu))
            dsrows.append((d, f"T{k}_{i}", mu))   # fwd == mu → monotone, IC=+1
    _mk_db_with_mu(db, csrows); _mk_ds(ds, dsrows)
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30,
                       as_of="2025-06-01")
    assert res["aged_joined_dates"] >= 30           # mu column WAS picked up
    re = res["rank_evidence"]
    assert re["xsection_rank_ic"]["mean"] > 0.9      # mu ranks fwd
    assert re["within_date_refused_minus_kept"]["mean"] < 0   # drops relative losers
    assert re["within_date_refused_minus_kept"]["pct_days_refused_below_kept"] == 1.0
    assert "good" in re["reading"]
