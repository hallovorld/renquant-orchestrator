"""Tests for the read-only panel-exit predictiveness study (synthetic ledger, no network).

The study reads ONLY the decision ledger (candidate_scores + ticker_forward_returns +
pipeline_runs) — it trains no model. These tests build a tiny synthetic SQLite ledger and assert
that the within-date per-date-block statistics read the planted signal correctly, that aging is
enforced by TRADING SESSIONS (not calendar days), and that significance is reported via an
overlap-aware MOVING-BLOCK bootstrap.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sqlite3
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rpe", Path(__file__).resolve().parent.parent / "scripts" / "research_panel_exit_predictiveness.py")
rpe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rpe)


def _sessions_after(start: _dt.date, n: int):
    """``n`` business days strictly after ``start`` (the synthetic trading-session calendar)."""
    out, d = [], start
    while len(out) < n:
        d = d + _dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _mk_ledger(path: Path, *, regime: str, fired_fwd: float, kept_fwd: float, n_dates: int = 30,
               n_names: int = 12, start: _dt.date = _dt.date(2024, 1, 1),
               trailing_sessions: int = 80):
    """A ledger where the bottom-floor names (lowest panel + mu<=0) realize ``fired_fwd`` and the
    rest realize ``kept_fwd``, repeated over ``n_dates`` distinct BUSINESS dates, one run per date.

    ``trailing_sessions`` extra ``ticker_forward_returns`` rows (FILLER ticker) are appended AFTER
    the last ledger date so the script's trading-session calendar (the distinct ``as_of_date``)
    extends far enough for the 60-session horizon to elapse — otherwise no date ages.
    """
    con = sqlite3.connect(str(path))
    con.execute("create table pipeline_runs (run_id text primary key, run_date date, regime text)")
    con.execute("create table candidate_scores (run_id text, ticker text, panel_score real, mu real)")
    con.execute("create table ticker_forward_returns (as_of_date date, ticker text, fwd_60d real)")
    n_bottom = max(1, int(n_names * 0.20))
    dates = []
    d = start
    while len(dates) < n_dates:
        if d.weekday() < 5:  # business days → a realistic session calendar
            dates.append(d)
        d = d + _dt.timedelta(days=1)
    for i, day in enumerate(dates):
        ds = day.isoformat()
        rid = f"{ds}-sim-r{i}"
        con.execute("insert into pipeline_runs values (?,?,?)", (rid, ds, regime))
        for j in range(n_names):
            tk = f"T{j}"
            is_bottom = j < n_bottom
            panel = -1.0 + j * 0.1          # ascending → first names are the bottom
            mu = -0.01 if is_bottom else 0.02
            fwd = fired_fwd if is_bottom else kept_fwd
            con.execute("insert into candidate_scores values (?,?,?,?)", (rid, tk, panel, mu))
            con.execute("insert into ticker_forward_returns values (?,?,?)", (ds, tk, fwd))
    # trailing FILLER session rows so the session calendar spans the full 60-session horizon
    for s in _sessions_after(dates[-1], trailing_sessions):
        con.execute("insert into ticker_forward_returns values (?,?,?)",
                    (s.isoformat(), "_FILLER_", 0.0))
    con.commit()
    con.close()
    # an as_of comfortably past the last ledger date + 60 trading sessions
    return dates[-1] + _dt.timedelta(days=130)


def test_predictive_regime_reads_as_predictive(tmp_path):
    db = tmp_path / "runs.db"
    as_of = _mk_ledger(db, regime="BULL_CALM", fired_fwd=-0.08, kept_fwd=+0.02, n_dates=80)
    res = rpe.evaluate(db, horizon=60, min_xsec=8, as_of=as_of.isoformat())
    bc = res["by_regime"]["BULL_CALM"]["and_fired_minus_kept_fwd"]
    assert bc["mean"] is not None and bc["mean"] < 0
    # overlap-aware: the block-bootstrap 95% CI excludes 0 (not the anti-conservative iid t)
    assert bc["block_sessions"] == 60
    assert bc["ci95_block_bootstrap"] is not None and bc["ci95_block_bootstrap"][1] < 0
    assert bc["significant_block_bootstrap"] is True
    # the naive iid t is retained only as a labelled, anti-conservative reference
    assert "t_iid_anticonservative" in bc and "t_block_bootstrap" in bc
    assert "SUGGESTS exit predictive" in res["by_regime"]["BULL_CALM"]["reading"]
    assert res["bull_calm_verdict"] == "BULL_CALM_SUGGESTS_PREDICTIVE"


def test_inverted_regime_reads_as_inverted(tmp_path):
    db = tmp_path / "runs.db"
    # bottom names realize MORE than the kept names → exiting them loses alpha
    as_of = _mk_ledger(db, regime="BULL_CALM", fired_fwd=+0.10, kept_fwd=-0.01, n_dates=80)
    res = rpe.evaluate(db, horizon=60, min_xsec=8, as_of=as_of.isoformat())
    assert "SUGGESTS exit inverted" in res["by_regime"]["BULL_CALM"]["reading"]
    assert res["bull_calm_verdict"] == "BULL_CALM_SUGGESTS_MISFIRE"


def test_one_run_per_date_dedup(tmp_path):
    """A duplicate, smaller re-run of the same date must not double-count the date."""
    db = tmp_path / "runs.db"
    as_of = _mk_ledger(db, regime="BULL_CALM", fired_fwd=-0.08, kept_fwd=+0.02, n_dates=80)
    con = sqlite3.connect(str(db))
    # add a SECOND, smaller run for an existing date (fewer names) — should be ignored
    first_date = _dt.date(2024, 1, 1)
    while first_date.weekday() >= 5:
        first_date = first_date + _dt.timedelta(days=1)
    con.execute("insert into pipeline_runs values (?,?,?)",
                (f"{first_date.isoformat()}-sim-dup", first_date.isoformat(), "BULL_CALM"))
    con.execute("insert into candidate_scores values (?,?,?,?)",
                (f"{first_date.isoformat()}-sim-dup", "T0", -1.0, -0.01))
    con.execute("insert into ticker_forward_returns values (?,?,?)",
                (first_date.isoformat(), "T0", +99.0))  # absurd value that would skew if double-counted
    con.commit(); con.close()
    res = rpe.evaluate(db, horizon=60, min_xsec=8, as_of=as_of.isoformat())
    # 80 distinct aged dates regardless of the duplicate run
    assert res["by_regime"]["BULL_CALM"]["and_fired_minus_kept_fwd"]["n_dates"] == 80


def test_block_stat_basic():
    s = rpe._block_stat([-0.1, -0.11, -0.09, -0.10, -0.12, -0.08], block=2)
    assert s["n_dates"] == 6 and s["mean"] is not None and s["mean"] < 0
    assert s["pct_days_negative"] == 1.0
    # an overlap-aware CI is produced when there is more than one block
    assert s["ci95_block_bootstrap"] is not None
    empty = rpe._block_stat([float("nan"), float("inf")], block=2)
    assert empty["n_dates"] == 0 and empty["mean"] is None


def test_block_bootstrap_widens_ci_vs_iid():
    """The moving-block bootstrap must NOT understate uncertainty: on an autocorrelated series its
    SE should exceed the naive iid SEM, so it cannot manufacture significance the iid t lacks."""
    import numpy as np
    rng = np.random.default_rng(7)
    # AR(1) series with strong positive autocorrelation (mimics overlapping 60d labels)
    n, phi = 240, 0.9
    e = rng.normal(0, 0.01, n)
    x = np.empty(n); x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    se_b, lo, hi = rpe._moving_block_bootstrap(x, block=60)
    iid_sem = float(np.std(x, ddof=1) / np.sqrt(n))
    assert se_b is not None
    assert se_b > iid_sem            # block bootstrap is more conservative on dependent data
    assert lo < hi


def test_too_few_dates_for_one_block_is_thin_not_significant():
    """A regime with fewer dates than one block (<= horizon) has no independent blocks to resample;
    the bootstrap must REFUSE a CI rather than report a degenerate zero-width 'significant' one."""
    se_b, lo, hi = rpe._moving_block_bootstrap([-0.2] * 14, block=60)
    assert se_b is None and lo is None and hi is None
    stat = rpe._block_stat([-0.2] * 14, block=60)
    assert stat["ci95_block_bootstrap"] is None
    assert stat["significant_block_bootstrap"] is False


def test_calendar_old_but_under_60_sessions_is_not_aged(tmp_path):
    """Codex #195 r2 #2 regression: a ledger date that is >60 CALENDAR days old but <60 TRADING
    SESSIONS old must NOT count as aged, because ``fwd_60d`` is a 60-SESSION (shift(-60)) label.

    A naive ``as_of - 60 calendar days`` cutoff (or a bare ``fwd_60d IS NOT NULL`` check) would
    admit it; the session-correct cutoff must reject it. This test FAILS on the old calendar/null
    behaviour and PASSES on the trading-session cutoff.
    """
    db = tmp_path / "runs.db"
    con = sqlite3.connect(str(db))
    con.execute("create table pipeline_runs (run_id text primary key, run_date date, regime text)")
    con.execute("create table candidate_scores (run_id text, ticker text, panel_score real, mu real)")
    con.execute("create table ticker_forward_returns (as_of_date date, ticker text, fwd_60d real)")
    led = _dt.date(2025, 1, 6)            # Monday — the only ledger date
    as_of = _dt.date(2025, 3, 24)         # 77 calendar days later
    # 9-name cross-section so >= min_xsec; fwd_60d is NON-NULL (it was written "early")
    rid = f"{led.isoformat()}-sim-r0"
    con.execute("insert into pipeline_runs values (?,?,?)", (rid, led.isoformat(), "BULL_CALM"))
    for k in range(9):
        con.execute("insert into candidate_scores values (?,?,?,?)",
                    (rid, f"T{k}", -1.0 + k * 0.1, -0.01 if k < 2 else 0.02))
        con.execute("insert into ticker_forward_returns values (?,?,?)",
                    (led.isoformat(), f"T{k}", -0.05 if k < 2 else 0.02))
    # session calendar = business days in (led, as_of]; count strictly-after sessions
    sess, d = [], led
    while d <= as_of:
        if d.weekday() < 5:
            sess.append(d)
        d += _dt.timedelta(days=1)
    later = [s for s in sess if s > led]
    assert len(later) < 60                 # fewer than a full 60-session horizon have elapsed
    assert (as_of - led).days > 60         # but MORE than 60 calendar days — the trap
    for s in sess:                         # filler rows so the session calendar spans the window
        if s != led:
            con.execute("insert into ticker_forward_returns values (?,?,?)",
                        (s.isoformat(), "_FILLER_", 0.0))
    con.commit(); con.close()
    res = rpe.evaluate(db, horizon=60, min_xsec=8, as_of=as_of.isoformat())
    # session-correct: the date is NOT fully aged → it must be excluded
    assert res["ledger_dates"] == 0
    assert res["dates_dropped_not_aged"] == 1
    assert res["aging"] == "trading_sessions"
    assert res["aged_cutoff"] < led.isoformat()


def test_not_yet_aged_rows_are_dropped(tmp_path):
    """Even with MANY dates and fwd_60d present, if the 60-session horizon has NOT elapsed as of
    ``as_of`` they must be dropped (not counted as aged)."""
    db = tmp_path / "runs.db"
    # ledger dates all "today-ish", as_of just after the last → 0 sessions elapsed
    as_of = _mk_ledger(db, regime="BULL_CALM", fired_fwd=-0.08, kept_fwd=+0.02,
                       n_dates=40, start=_dt.date(2026, 6, 1), trailing_sessions=0)
    # as_of one business day after the last ledger date → no date can have 60 later sessions
    res = rpe.evaluate(db, horizon=60, min_xsec=8, as_of="2026-08-01")
    assert res["ledger_dates"] == 0
    assert res["dates_dropped_not_aged"] == 40
