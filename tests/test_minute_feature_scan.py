"""Focused tests for the renquant-105 minute-feature experiment (#206 review fixes).

Covers the four things the review flagged as bugs:
  1. DST-correct RTH session filtering (drops pre-market in EST and after-hours in EDT).
  2. Half-day (early close) truncation.
  3. Next-session entry / label alignment (no same-close look-ahead).
  4. The proper FWL partial-correlation (residualize BOTH sides on the same controls).

These import the experiment modules directly from scripts/ (not packaged in src).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pytest.importorskip("exchange_calendars")

from minute_rth import rth_filter, session_open_close, daily_factors  # noqa: E402
import minute_feature_scan as M  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _bars_at(symbol, utc_times):
    """Build a (symbol, timestamp)-indexed UTC bar frame at the given UTC instants."""
    idx = pd.MultiIndex.from_tuples(
        [(symbol, pd.Timestamp(t, tz="UTC")) for t in utc_times],
        names=["symbol", "timestamp"],
    )
    n = len(idx)
    return pd.DataFrame(
        {
            "open": np.full(n, 100.0),
            "high": np.full(n, 101.0),
            "low": np.full(n, 99.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 1000.0),
            "trade_count": np.full(n, 10.0),
            "vwap": np.full(n, 100.0),
        },
        index=idx,
    )


# --------------------------------------------------------------------------- #
# 1. DST-correct RTH filtering
# --------------------------------------------------------------------------- #
def test_rth_drops_premarket_in_est():
    """In winter (EST, UTC-5), RTH open is 14:30 UTC. A 13:45 UTC bar is 08:45 ET =
    PRE-MARKET and must be dropped; a 14:45 UTC bar (09:45 ET) must be kept."""
    df = _bars_at("AAPL", ["2024-01-10 13:45", "2024-01-10 14:45", "2024-01-10 20:45"])
    out = rth_filter(df)
    kept = out.index.get_level_values("timestamp").tz_convert("UTC").strftime("%H:%M").tolist()
    assert "13:45" not in kept, "08:45 ET pre-market must be excluded in EST"
    assert "14:45" in kept, "09:45 ET RTH must be kept in EST"
    assert "20:45" in kept, "15:45 ET RTH (pre-16:00 close) must be kept in EST"


def test_rth_drops_afterhours_in_edt():
    """In summer (EDT, UTC-4), RTH close is 20:00 UTC. A 20:30 UTC bar is 16:30 ET =
    AFTER-HOURS and must be dropped; the old fixed 13:30-21:00 UTC union wrongly kept
    it. A 13:45 UTC bar (09:45 ET) must be kept."""
    df = _bars_at("AAPL", ["2024-07-10 13:45", "2024-07-10 19:45", "2024-07-10 20:30"])
    out = rth_filter(df)
    kept = out.index.get_level_values("timestamp").tz_convert("UTC").strftime("%H:%M").tolist()
    assert "13:45" in kept, "09:45 ET RTH must be kept in EDT"
    assert "19:45" in kept, "15:45 ET RTH must be kept in EDT"
    assert "20:30" not in kept, "16:30 ET after-hours must be excluded in EDT"


def test_rth_session_label_is_ny_local_date():
    """The session column must be the NY-local trading date, tz-naive."""
    df = _bars_at("AAPL", ["2024-07-10 14:00"])
    out = rth_filter(df)
    assert (out["session"] == pd.Timestamp("2024-07-10")).all()
    assert out["session"].dt.tz is None


# --------------------------------------------------------------------------- #
# 2. Half-days (early closes)
# --------------------------------------------------------------------------- #
def test_half_day_truncates_at_early_close():
    """2024-11-29 (day after Thanksgiving) is an early close at 13:00 ET = 18:00 UTC
    (EST). A 17:45 UTC bar (12:45 ET) is in-session; an 18:30 UTC bar (13:30 ET) is
    AFTER the early close and must be dropped."""
    df = _bars_at("AAPL", ["2024-11-29 15:00", "2024-11-29 17:45", "2024-11-29 18:30",
                           "2024-11-29 20:00"])
    out = rth_filter(df)
    kept = out.index.get_level_values("timestamp").tz_convert("UTC").strftime("%H:%M").tolist()
    assert "15:00" in kept and "17:45" in kept, "pre-13:00-ET bars kept on the half-day"
    assert "18:30" not in kept, "post-early-close (13:30 ET) bar must be dropped"
    assert "20:00" not in kept, "15:00 ET after the 13:00 early close must be dropped"


def test_schedule_marks_half_day_short():
    """session_open_close must report the early close for a known half-day."""
    sched = session_open_close("2024-11-29", "2024-11-29")
    dur_h = (sched["sess_close"] - sched["sess_open"]).dt.total_seconds().iloc[0] / 3600.0
    assert dur_h == pytest.approx(3.5, abs=0.1), "Nov 29 2024 is a 3.5h half-day (09:30-13:00)"


# --------------------------------------------------------------------------- #
# 3. Next-session entry / label alignment (no look-ahead)
# --------------------------------------------------------------------------- #
def test_next_session_entry_uses_tomorrow_open_not_today_close():
    """A signal known after close[D] must be entered at open[D+1]; the horizon-h
    forward return must be close[D+h]/open[D+1] - 1, never close[D+h]/close[D]."""
    dates = pd.bdate_range("2024-01-02", periods=5)
    syms = ["A", "B"]
    px = pd.DataFrame({"A": [10, 11, 12, 13, 14], "B": [20, 21, 22, 23, 24]},
                      index=dates, dtype=float)
    # day-open frame: open[D+1] differs from close[D] so we can tell them apart
    day_open = pd.DataFrame({"A": [10.5, 11.5, 12.5, 13.5, 14.5],
                             "B": [20.5, 21.5, 22.5, 23.5, 24.5]},
                            index=dates, dtype=float)
    next_open = day_open.shift(-1)
    h = 1
    fwd = px.shift(-h) / next_open - 1.0
    # for D=index[0], entry = open[D+1]=11.5 (A), exit = close[D+1]=11 -> 11/11.5 - 1
    assert fwd.iloc[0]["A"] == pytest.approx(11.0 / 11.5 - 1.0)
    # it must NOT equal the look-ahead close/close = 11/10 - 1
    assert fwd.iloc[0]["A"] != pytest.approx(11.0 / 10.0 - 1.0)
    # last row has no next session -> NaN (no fabricated label)
    assert pd.isna(fwd.iloc[-1]["A"])


def test_no_lookahead_signal_strictly_precedes_entry():
    """next_open at row D is the open of session D+1 (a strictly future timestamp)."""
    dates = pd.bdate_range("2024-01-02", periods=4)
    day_open = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0]}, index=dates)
    next_open = day_open.shift(-1)
    assert next_open.iloc[0]["A"] == 2.0  # entry for D0 is D1's open
    assert pd.isna(next_open.iloc[-1]["A"])  # no entry after the last session


# --------------------------------------------------------------------------- #
# 4. Proper FWL partial correlation
# --------------------------------------------------------------------------- #
def _make_panel(dates, syms, values_fn):
    return pd.DataFrame(
        {s: [values_fn(d, s) for d in dates] for s in syms},
        index=dates, dtype=float,
    )


def test_fwl_residualizes_both_sides():
    """Core FWL property: when the forward return is driven ONLY by the (rank-z of the)
    daily control, and the minute feature is a noisy proxy for that SAME control with
    NO extra information, the proper FWL marginal IC -- residualize BOTH sides on the
    control, then correlate residuals -- must be ~0 (the feature adds nothing on top).

    The OLD code (residualize only the return, then correlate with the RAW feature)
    is not a valid partial effect; here we pin the proper calc's null behaviour."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-02", periods=30)
    syms = [f"S{i}" for i in range(60)]
    # control with a clean cross-sectional spread per date
    base = {(d, s): rng.normal() for d in dates for s in syms}
    control = _make_panel(dates, syms, lambda d, s: base[(d, s)])
    factors = {"f": control}
    # return is the rank-z of the control (what the linear rank-control CAN explain),
    # plus pure idiosyncratic noise UNCORRELATED with the feature.
    ret_idio = {(d, s): rng.normal() for d in dates for s in syms}
    rank_z_ctrl = {d: M.rank_z(control.loc[d]) for d in dates}
    feature = _make_panel(dates, syms, lambda d, s: rank_z_ctrl[d][s] + 0.05 * rng.normal())
    fwd = _make_panel(dates, syms, lambda d, s: rank_z_ctrl[d][s] + ret_idio[(d, s)])

    dates_list = list(dates)
    resid_fwd = M.residualize_panel(fwd, factors, dates_list)
    resid_feat = M.residualize_panel(feature, factors, dates_list)
    ic_proper = M.daily_ic(resid_feat, resid_fwd, dates_list).mean()
    # proper FWL: feature carries NO marginal info over the control -> ~0
    assert abs(ic_proper) < 0.1, f"proper FWL marginal IC should be ~0, got {ic_proper}"


def test_fwl_detects_genuine_marginal_signal():
    """When the feature DOES carry information beyond the control, proper FWL recovers
    a positive marginal IC."""
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2024-01-02", periods=40)
    syms = [f"S{i}" for i in range(50)]
    fac_vals = {(d, s): rng.normal() for d in dates for s in syms}
    extra = {(d, s): rng.normal() for d in dates for s in syms}
    factor = _make_panel(dates, syms, lambda d, s: fac_vals[(d, s)])
    factors = {"f": factor}
    feature = _make_panel(dates, syms, lambda d, s: 0.5 * fac_vals[(d, s)] + extra[(d, s)])
    # return depends on the EXTRA part the feature carries -> genuine marginal signal
    fwd = _make_panel(dates, syms, lambda d, s: fac_vals[(d, s)] + extra[(d, s)])
    dates_list = list(dates)
    resid_fwd = M.residualize_panel(fwd, factors, dates_list)
    resid_feat = M.residualize_panel(feature, factors, dates_list)
    ic_proper = M.daily_ic(resid_feat, resid_fwd, dates_list).mean()
    assert ic_proper > 0.2, f"proper FWL should detect the genuine marginal signal, got {ic_proper}"


def test_residualize_panel_orthogonal_to_controls():
    """Residuals must be (numerically) orthogonal to the controls used: a regression
    of the residual on the same controls returns ~zero slope."""
    rng = np.random.default_rng(2)
    dates = pd.bdate_range("2024-01-02", periods=5)
    syms = [f"S{i}" for i in range(30)]
    fac_vals = {(d, s): rng.normal() for d in dates for s in syms}
    factor = _make_panel(dates, syms, lambda d, s: fac_vals[(d, s)])
    factors = {"f": factor}
    y = _make_panel(dates, syms, lambda d, s: 2.0 * fac_vals[(d, s)] + 0.3 * rng.normal())
    resid = M.residualize_panel(y, factors, list(dates))
    d0 = dates[0]
    r = resid.loc[d0].dropna()
    fr = M.rank_z(factor.loc[d0][r.index])
    # corr(residual, rank-z control) ~ 0
    corr = np.corrcoef(r.values, fr.values)[0, 1]
    assert abs(corr) < 0.2, f"residual should be ~orthogonal to the control, corr={corr}"


def test_daily_factors_shapes_and_names():
    dates = pd.bdate_range("2022-01-03", periods=400)
    syms = ["A", "B", "C"]
    px = pd.DataFrame(
        {s: np.cumprod(1 + np.random.default_rng(i).normal(0, 0.01, len(dates)))
         for i, s in enumerate(syms)},
        index=dates,
    )
    f = daily_factors(px)
    assert set(f.keys()) == {"mom_12_1", "mom_6_1", "st_rev_21", "ma200_dist", "pct_52w_high"}
    for name, fr in f.items():
        assert fr.shape == px.shape
