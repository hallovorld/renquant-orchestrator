"""
Shared DST-correct RTH (regular-trading-hours) filtering + daily-factor helpers for
the renquant-105 minute-feature experiments (scripts/minute_feature_scan.py and
scripts/minute_signal_costtest.py). READ-ONLY; no I/O side effects.

The old fixed UTC 13:30-21:00 union admitted pre-market (EST) and after-hours (EDT)
bars that drifted by season. Here we use the XNYS exchange calendar
(exchange_calendars) to filter each bar to its session's [open, close) UTC window,
which is 09:30-16:00 LOCAL exchange time and TRUNCATES half-days (early closes at
13:00 ET) automatically.
"""
import numpy as np
import pandas as pd

try:
    import exchange_calendars as xcals
    _XNYS = xcals.get_calendar("XNYS")
except Exception:  # pragma: no cover - calendar lib should be present in the venv
    _XNYS = None

DAILY_FACTOR_NAMES = ["mom_12_1", "mom_6_1", "st_rev_21", "ma200_dist", "pct_52w_high"]


def session_open_close(start, end):
    """Return a DataFrame indexed by tz-naive session date with UTC `sess_open` and
    `sess_close` timestamps for every XNYS session in [start, end] (half-days carry a
    correctly-shortened close)."""
    if _XNYS is None:
        raise RuntimeError("exchange_calendars (XNYS) is required for RTH filtering")
    start = pd.Timestamp(start).date()
    end = pd.Timestamp(end).date()
    sched = _XNYS.schedule.loc[str(start):str(end)][["open", "close"]].copy()
    sched.columns = ["sess_open", "sess_close"]
    sched.index = pd.DatetimeIndex(sched.index).normalize().tz_localize(None)
    sched.index.name = "session"
    return sched


def rth_filter(df):
    """Filter a (symbol, timestamp)-indexed UTC bar frame to DST-correct RTH and add a
    tz-naive `session` column (NY local date). Keeps bars in [session_open,
    session_close) so half-days truncate to their early close and pre/after-hours are
    dropped. Bars on non-trading timestamps (no matching session) are dropped."""
    if df.empty:
        out = df.copy()
        out["session"] = pd.Series([], dtype="datetime64[ns]")
        return out
    ts = df.index.get_level_values("timestamp")
    ts_utc = ts.tz_convert("UTC")
    ny = ts_utc.tz_convert("America/New_York")
    session = pd.DatetimeIndex(ny.normalize().tz_localize(None))

    lo = session.min()
    hi = session.max()
    sched = session_open_close(lo, hi)

    # map each bar's session to its open/close (UTC, tz-aware); align by position
    sess_open = sched["sess_open"].reindex(session)
    sess_close = sched["sess_close"].reindex(session)
    so = pd.to_datetime(sess_open.to_numpy(), utc=True)
    sc = pd.to_datetime(sess_close.to_numpy(), utc=True)
    tsv = pd.DatetimeIndex(ts_utc)

    valid = sess_open.notna().to_numpy()
    mask = valid & (tsv >= so) & (tsv < sc)

    out = df[mask].copy()
    out["session"] = session[mask]
    return out


def daily_factors(px):
    """The canonical daily price factors used by sighunt, for marginal (FWL) IC.
    `px` is a date x symbol daily close panel. Returns dict name -> date x symbol."""
    f = {}
    f["mom_12_1"] = (px.shift(21) / px.shift(252) - 1.0)
    f["mom_6_1"] = (px.shift(21) / px.shift(126) - 1.0)
    f["st_rev_21"] = -1.0 * (px / px.shift(21) - 1.0)
    sma200 = px.rolling(200, min_periods=150).mean()
    f["ma200_dist"] = px / sma200 - 1.0
    hi252 = px.rolling(252, min_periods=200).max()
    f["pct_52w_high"] = px / hi252
    return f
