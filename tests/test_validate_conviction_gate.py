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


def _mk_ds(path: Path, rows, *, trailing_sessions=0):
    df = pd.DataFrame(rows, columns=["date", "ticker", "fwd_60d_excess"])
    if trailing_sessions:
        # Extend the dataset's trading-session index with `trailing_sessions` later
        # business days so the validator can age ledger dates by TRADING SESSIONS
        # (the real fwd_60d_excess is a shift(-60) bar label, ~84 calendar days).
        # These filler rows carry no ledger match, they only populate the session
        # calendar the age-cutoff counts against.
        import datetime as _dt
        last = max(_dt.date.fromisoformat(r[0]) for r in rows)
        extra = []
        d = last
        for _ in range(trailing_sessions):
            d = d + _dt.timedelta(days=1)
            while d.weekday() >= 5:  # skip weekends → business-day session index
                d = d + _dt.timedelta(days=1)
            extra.append((d.isoformat(), "_FILLER_", 0.0))
        df = pd.concat([df, pd.DataFrame(extra, columns=df.columns)],
                       ignore_index=True)
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
    # 70 trailing trading sessions so the 60-SESSION horizon elapses for the
    # ledger dates (a 60-calendar-day cutoff would have been enough, but the label
    # is 60 sessions; we age against the session index).
    _mk_db(db, csrows); _mk_ds(ds, dsrows, trailing_sessions=70)
    # as_of well after the 2025-01 dates AND >60 trading sessions later → aged
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30,
                       as_of="2025-09-01")
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


def test_calendar_old_but_under_60_sessions_is_not_aged(tmp_path):
    # Codex #196 #1 regression: a ledger date that is >60 CALENDAR days old but
    # <60 TRADING SESSIONS old must NOT count as aged, because fwd_60d_excess is a
    # 60-SESSION (shift(-60)) label. The dataset's date index IS the session
    # calendar. Here the only ledger date is 2025-01-06 and as_of is 2025-03-24
    # (77 calendar days later) — the OLD `as_of - 60 calendar days` cutoff
    # (2025-01-23) would mark it aged, but only ~55 business sessions have elapsed,
    # so the session-correct cutoff must reject it. This test FAILS on the old
    # 60-calendar-day cutoff and PASSES on the session cutoff.
    import datetime as _dt
    db = tmp_path / "runs.db"; ds = tmp_path / "ds.parquet"
    # One ledger date with a 9-name cross-section (so >= min_xsec), all mu>0.
    led = _dt.date(2025, 1, 6)  # Monday
    csrows = [(f"{led.isoformat()}-live-r0", f"T{k}", 0.01 * (k + 1))
              for k in range(9)]
    dsrows = [(led.isoformat(), f"T{k}", 0.01 * (k + 1)) for k in range(9)]
    # Build the session index = business days from the ledger date up to as_of.
    # Count how many sessions are STRICTLY AFTER the ledger date and <= as_of.
    as_of = _dt.date(2025, 3, 24)
    sess, d = [], led
    while d <= as_of:
        if d.weekday() < 5:
            sess.append(d)
        d += _dt.timedelta(days=1)
    later = [s for s in sess if s > led]
    assert len(later) < 60                      # fewer than a full 60-session horizon
    assert (as_of - led).days > 60              # but more than 60 calendar days
    # filler session rows so the dataset's date index spans the full window
    for s in sess:
        if s != led:
            dsrows.append((s.isoformat(), "_FILLER_", 0.0))
    _mk_db(db, csrows); _mk_ds(ds, dsrows)
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=1,
                       as_of=as_of.isoformat())
    # session-correct: the date is NOT fully aged → it must be excluded
    assert res["aged_joined_dates"] == 0
    assert res["aging"] == "trading_sessions"


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
    _mk_db_with_mu(db, csrows); _mk_ds(ds, dsrows, trailing_sessions=70)
    res = vcg.evaluate(db, ds, mu_floor=0.03, horizon_days=60, min_dates=30,
                       as_of="2025-09-01")
    assert res["aged_joined_dates"] >= 30           # mu column WAS picked up
    re = res["rank_evidence"]
    assert re["xsection_rank_ic"]["mean"] > 0.9      # mu ranks fwd
    assert re["within_date_refused_minus_kept"]["mean"] < 0   # drops relative losers
    assert re["within_date_refused_minus_kept"]["pct_days_refused_below_kept"] == 1.0
    assert "good" in re["reading"]
    # Codex #196 #2: significance comes from a MOVING-BLOCK bootstrap (overlapping
    # 60-session windows → date obs are not iid), not the naive iid t. Both are
    # surfaced; the block-bootstrap 95% CI is the trustworthy one.
    ic = re["xsection_rank_ic"]
    assert ic["block_sessions"] == 60
    assert ic["block_bootstrap_se"] is not None
    assert ic["ci95_block_bootstrap"] is not None and ic["ci95_block_bootstrap"][0] > 0
    assert ic["significant_block_bootstrap"] is True   # IC=+1 every date → CI>0
    # naive iid t is retained as a labelled reference (None here: IC is a constant
    # +1 every date, so its SEM is 0 — the very degeneracy the bootstrap guards).
    assert "t_iid_anticonservative" in ic
    assert "t_block_bootstrap" in ic
