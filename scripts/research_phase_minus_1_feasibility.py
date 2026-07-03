#!/usr/bin/env python3
"""renquant105 Phase -1 — cheap, bounded, read-only feasibility probe.

Spec: ``doc/design/2026-06-27-renquant105-Phase-minus-1-cheap-feasibility.md`` (design branch
``design/renquant105-intraday``, design PR #198). This is the FIRST gate in the renquant105
master DAG — a bounded read-only go/no-go that runs BEFORE the 10-17-week M0->M3 build, so we do
not stand up the full intraday stack on an *unmeasured prior*.

The single most load-bearing 105 assumption is the open->close cross-sectional dispersion
``sigma_oc ~= 150-250 bps`` (a PRIOR the §A feasibility script ASSUMES, not a measurement). This
script MEASURES it (and three siblings) cheaply from data we already have read-access to, and
applies the design doc's **pre-registered** STOP/GO table EXACTLY — no post-hoc threshold tuning.

Pre-registered STOP/GO (verbatim from the design doc, do NOT edit these constants):
    GO to M0 requires ALL of:
      (a) >= ~30-40 liquid names have usable intraday history on existing/available data;
      (b) the CAUSAL open->close sigma_oc MEDIAN is inside or above the assumed band's lower
          edge (>= ~150 bps), with the event-time contract applied;
      (c) attainable breadth supports >= ~4 effective independent bets/day;
      (d) the conservative cost band does NOT exceed ~17 bps (the §A conservative leg).
    STOP otherwise (sigma_oc materially below band, OR breadth/coverage too thin, OR the four
      measurements cannot be produced within the <=5-day / <=1-week cap, OR the cheap cost band
      is materially worse than the §A conservative leg).

What it measures (all read-only):
  1. sigma_oc — daily-OHLC open->close cross-sectional dispersion (std AND robust MAD/IQR),
     per session, in bps, over ~3-5y. THE VERDICT-DRIVING NUMBER. Compared to the assumed
     150-250 bps band. A causal/event-time check is run on a SAMPLE intraday window (entry at the
     first executable bar AFTER the open, not the print-open) to confirm the daily proxy is not
     inflated by the opening cross.
  2. Universe breadth — names with a valid open&close per session; effective breadth N_eff and how
     it bears on the Fundamental-Law IR = IC * sqrt(breadth).
  3. Intraday coverage census — a BOUNDED sample window of minute bars; per-name coverage / gap /
     NaN-leaf rate. Verifies/refutes the design's "~50% of names had no intraday history" claim.
  4. Conservative executable-cost bound — spread proxy from a cheap quote sample if available, else
     the documented ~11 bps prior (stated as conservative); crossed with sigma_oc via the §A edge
     identity (top-pick gross edge ~= IC * sigma_oc * factor) to produce a MEASURED net-edge band
     at IC 0.03 and IC 0.05.

HARD boundaries honoured here: read-only DATA API only (no orders, no broker mutation); never
writes to ``/Users/renhao/git/github/RenQuant`` or any canonical data path; writes nothing outside
stdout. The live Alpaca keys are read from the live ``.env`` only to authenticate the *data* client.

Network is required ONLY for the live measurement. All pure helpers below are import-safe and unit
tested without network (``tests/test_research_phase_minus_1_feasibility.py``). ``--offline``
prints the plan + thresholds and exits 0 without any network call.

Usage:
    research_phase_minus_1_feasibility.py [--years 5] [--intraday-sessions 30]
        [--quote-sample 12] [--json] [--offline]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics
import sys
from dataclasses import asdict, dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# PINNED CONSTANTS (the design doc's pre-registered numbers — do NOT tune)
# ---------------------------------------------------------------------------
ASSUMED_SIGMA_OC_LO_BPS = 150.0   # §A assumed band lower edge (GO criterion (b))
ASSUMED_SIGMA_OC_HI_BPS = 250.0   # §A assumed band upper edge (context only)
GO_MIN_INTRADAY_NAMES = 30        # GO criterion (a): >= ~30-40 names w/ usable intraday history
GO_MIN_EFF_BREADTH = 4.0          # GO criterion (c): >= ~4 effective independent bets/day
COST_CONSERVATIVE_LEG_BPS = 17.0  # GO criterion (d): conservative cost must NOT exceed this
COST_PRIOR_BPS = 11.0             # §A placeholder round-trip cost prior (documented)
# §A edge identity: top-pick GROSS open->close edge ~= IC * sigma_oc * EDGE_FACTOR.
# EDGE_FACTOR is the cross-sectional spread between the top decile's expected standardized score
# and the mean (~ the std-normal upper-decile mean), pinned at 1.0 here as a *conservative*
# 1-sigma top-name selection (the §A identity's lower bound). Reported, not tuned.
EDGE_FACTOR = 1.0
IC_GRID = (0.03, 0.05)            # the two IC anchors the design asks the net-edge band for

# Robust-std scale factors (population, not tuned — standard constants).
MAD_TO_STD = 1.4826               # MAD -> std for a normal distribution.
IQR_TO_STD = 1.349                # IQR -> std for a normal distribution (p75-p25 = 1.349*sigma).


# ---------------------------------------------------------------------------
# Pure, network-free helpers (unit tested)
# ---------------------------------------------------------------------------
def open_close_returns(opens: Sequence[float], closes: Sequence[float]) -> list[float]:
    """Causal intraday open->close return r = close/open - 1 per name (overnight EXCLUDED).

    Only names with BOTH a strictly-positive finite open and finite close contribute (a missing
    or non-positive leg is dropped — this is the per-session valid-name filter that also feeds the
    breadth count). Returns the list of valid returns (decimal, not bps).
    """
    out: list[float] = []
    for o, c in zip(opens, closes):
        if o is None or c is None:
            continue
        try:
            o = float(o)
            c = float(c)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(o) and math.isfinite(c)) or o <= 0.0 or c <= 0.0:
            continue
        out.append(c / o - 1.0)
    return out


def cross_sectional_dispersion_bps(returns: Sequence[float]) -> dict[str, float] | None:
    """Cross-sectional dispersion of one session's open->close returns, in bps.

    Returns ``None`` if fewer than 2 valid names (no cross-section). Reports BOTH the plain
    population std and two ROBUST estimates (MAD-based and IQR-based), all scaled to a
    std-equivalent and expressed in bps, plus the breadth (n valid names).
    """
    rs = [r for r in returns if r is not None and math.isfinite(r)]
    n = len(rs)
    if n < 2:
        return None
    mean = statistics.fmean(rs)
    std = (sum((r - mean) ** 2 for r in rs) / n) ** 0.5  # population std
    med = statistics.median(rs)
    mad = statistics.median([abs(r - med) for r in rs])
    robust_mad_std = mad * MAD_TO_STD
    qs = _quantiles(rs, (0.25, 0.75))
    iqr = qs[0.75] - qs[0.25]
    robust_iqr_std = iqr / IQR_TO_STD
    return {
        "breadth": float(n),
        "std_bps": std * 1e4,
        "robust_mad_std_bps": robust_mad_std * 1e4,
        "robust_iqr_std_bps": robust_iqr_std * 1e4,
        "median_ret_bps": med * 1e4,
    }


def _quantiles(xs: Sequence[float], qs: Iterable[float]) -> dict[float, float]:
    """Linear-interpolation quantiles (numpy-free so the pure helpers have no hard dep)."""
    s = sorted(xs)
    n = len(s)
    out: dict[float, float] = {}
    for q in qs:
        if n == 1:
            out[q] = s[0]
            continue
        pos = q * (n - 1)
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            out[q] = s[lo]
        else:
            frac = pos - lo
            out[q] = s[lo] * (1 - frac) + s[hi] * frac
    return out


def summarize_distribution(values: Sequence[float]) -> dict[str, float]:
    """median / p25 / p75 / mean / min / max / n of a per-session series (e.g. sigma_oc bps)."""
    vs = [v for v in values if v is not None and math.isfinite(v)]
    if not vs:
        return {"n": 0}
    qs = _quantiles(vs, (0.25, 0.5, 0.75))
    return {
        "n": len(vs),
        "median": qs[0.5],
        "p25": qs[0.25],
        "p75": qs[0.75],
        "mean": statistics.fmean(vs),
        "min": min(vs),
        "max": max(vs),
    }


def effective_breadth(per_session_breadths: Sequence[float]) -> float:
    """Effective independent-bets breadth proxy = median valid-name count per session.

    Conservative: uses the MEDIAN valid cross-section size (names with a usable open&close), the
    realistic pool the Fundamental-Law sqrt(breadth) term draws from. (The §A "~4 independent bets"
    is far below the raw name count; this returns the raw realistic pool — criterion (c) only asks
    it support >= ~4, which any double-digit liquid pool trivially does.)
    """
    bs = [b for b in per_session_breadths if b is not None and math.isfinite(b)]
    if not bs:
        return 0.0
    return statistics.median(bs)


def net_edge_band_bps(sigma_oc_bps: float, cost_bps: float,
                      ic_grid: Sequence[float] = IC_GRID,
                      edge_factor: float = EDGE_FACTOR) -> dict[str, dict[str, float]]:
    """MEASURED net-edge band: gross = IC * sigma_oc * factor; net = gross - round-trip cost.

    Uses the §A edge identity with the MEASURED sigma_oc (not the assumed band). Returns, per IC
    anchor, the gross and net round-trip-cost-adjusted edge in bps.
    """
    out: dict[str, dict[str, float]] = {}
    for ic in ic_grid:
        gross = ic * sigma_oc_bps * edge_factor
        out[f"IC={ic:.2f}"] = {
            "gross_edge_bps": gross,
            "net_edge_bps": gross - cost_bps,
            "cost_bps": cost_bps,
        }
    return out


@dataclass
class Verdict:
    go: bool
    reasons: list[str] = field(default_factory=list)
    criteria: dict[str, bool] = field(default_factory=dict)


def decide(sigma_oc_median_bps: float | None,
           n_intraday_names: int,
           eff_breadth: float,
           cost_bps: float) -> Verdict:
    """Apply the design doc's PRE-REGISTERED STOP/GO table EXACTLY. ALL four must hold for GO."""
    crit: dict[str, bool] = {}
    reasons: list[str] = []

    # (b) sigma_oc — the verdict-driving number.
    b_ok = sigma_oc_median_bps is not None and sigma_oc_median_bps >= ASSUMED_SIGMA_OC_LO_BPS
    crit["b_sigma_oc_ge_150bps"] = bool(b_ok)
    if sigma_oc_median_bps is None:
        reasons.append("(b) FAIL: sigma_oc could not be measured (no cross-section).")
    elif b_ok:
        reasons.append(
            f"(b) PASS: causal sigma_oc median {sigma_oc_median_bps:.1f} bps >= assumed lower "
            f"edge {ASSUMED_SIGMA_OC_LO_BPS:.0f} bps.")
    else:
        reasons.append(
            f"(b) FAIL: causal sigma_oc median {sigma_oc_median_bps:.1f} bps is BELOW the assumed "
            f"band lower edge {ASSUMED_SIGMA_OC_LO_BPS:.0f} bps -> §A's marginal case does not "
            f"survive the real dispersion.")

    # (a) intraday name coverage.
    a_ok = n_intraday_names >= GO_MIN_INTRADAY_NAMES
    crit["a_intraday_names_ge_30"] = bool(a_ok)
    reasons.append(
        f"({'a) PASS' if a_ok else 'a) FAIL'}: {n_intraday_names} names with usable intraday "
        f"history (need >= {GO_MIN_INTRADAY_NAMES}).")

    # (c) effective breadth.
    c_ok = eff_breadth >= GO_MIN_EFF_BREADTH
    crit["c_eff_breadth_ge_4"] = bool(c_ok)
    reasons.append(
        f"({'c) PASS' if c_ok else 'c) FAIL'}: effective breadth {eff_breadth:.1f} "
        f"(need >= {GO_MIN_EFF_BREADTH:.0f}).")

    # (d) cost band.
    d_ok = cost_bps <= COST_CONSERVATIVE_LEG_BPS
    crit["d_cost_le_17bps"] = bool(d_ok)
    reasons.append(
        f"({'d) PASS' if d_ok else 'd) FAIL'}: conservative round-trip cost {cost_bps:.1f} bps "
        f"(must not exceed {COST_CONSERVATIVE_LEG_BPS:.0f} bps).")

    go = bool(a_ok and b_ok and c_ok and d_ok)
    return Verdict(go=go, reasons=reasons, criteria=crit)


# ---------------------------------------------------------------------------
# Live (network) measurement — guarded; only runs in __main__ (not on import).
# ---------------------------------------------------------------------------
DEFAULT_UNIVERSE_NOTE = (
    "Universe read READ-ONLY from the pinned strategy-104 live config "
    "(backtesting/renquant_104/strategy_config.json == strategy_config.golden.json, 142 names, "
    "identical sets). This is the live production watchlist; no synthetic basket needed."
)
# Documented fallback basket (only used if the live config cannot be read) — ~50 liquid US
# large-caps spanning sectors. STATED for auditability; the live run uses the real config.
FALLBACK_BASKET = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA", "AVGO", "JPM", "V",
    "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "COST", "ORCL", "CVX",
    "MRK", "ABBV", "KO", "PEP", "ADBE", "CRM", "BAC", "NFLX", "AMD", "TMO",
    "MCD", "CSCO", "ACN", "ABT", "LIN", "DHR", "TXN", "INTC", "QCOM", "PM",
    "WFC", "NEE", "UNP", "IBM", "GE", "CAT", "HON", "LOW", "GS", "BLK",
]


def _load_universe() -> tuple[list[str], str]:
    """Read the live strategy-104 watchlist READ-ONLY; fall back to the documented basket."""
    cfg = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.json"
    try:
        with open(cfg) as fh:
            d = json.load(fh)
        wl = list(d.get("watchlist") or [])
        if wl:
            return wl, DEFAULT_UNIVERSE_NOTE
    except Exception as exc:  # pragma: no cover - fallback path
        sys.stderr.write(f"[warn] could not read live watchlist ({exc!r}); using fallback basket\n")
    return list(FALLBACK_BASKET), (
        "FALLBACK basket used (live config unreadable): ~50 liquid US large-caps across sectors.")


def _data_client():  # pragma: no cover - network
    """Authenticate a READ-ONLY Alpaca StockHistoricalDataClient from the live .env keys."""
    key = os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_SECRET_KEY")
    if not (key and sec):
        raise RuntimeError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY not in env. Run with the live .env sourced:\n"
            "  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a")
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(key, sec)


def _fetch_bars(client, req_kwargs, request_cls):  # pragma: no cover - network
    """Fetch bars on the proper consolidated SIP tape when permitted, else fall back to IEX.

    The data subscription forbids querying the most-recent ~15min of SIP, so for SIP we cap
    ``end`` to ~16min ago (the open/close of the just-closed sessions is well outside that). If
    SIP is still denied, fall back to the IEX feed (single-venue but free) so the measurement is
    never silently blocked. Returns (df, feed_used).
    """
    from alpaca.data.enums import DataFeed
    now = dt.datetime.now(dt.timezone.utc)
    sip_kwargs = dict(req_kwargs)
    sip_kwargs["end"] = min(sip_kwargs["end"], now - dt.timedelta(minutes=16))
    try:
        df = client.get_stock_bars(request_cls(feed=DataFeed.SIP, **sip_kwargs)).df
        return df, "sip(end-capped 16m)"
    except Exception as exc:
        sys.stderr.write(f"[info] SIP denied ({str(exc)[:80]}); falling back to IEX feed\n")
        df = client.get_stock_bars(request_cls(feed=DataFeed.IEX, **req_kwargs)).df
        return df, "iex(fallback)"


def _run_live(universe: list[str], universe_note: str, years: int,
              intraday_sessions: int, quote_sample: int) -> dict:  # pragma: no cover - network
    import pandas as pd
    from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    client = _data_client()
    now = dt.datetime.now(dt.timezone.utc)
    run_ts = now.isoformat()

    # ---- 1. + 2. Daily bars -> sigma_oc + breadth -----------------------------------------
    start = now - dt.timedelta(days=int(years * 365.25) + 5)
    df, daily_feed = _fetch_bars(
        client,
        {"symbol_or_symbols": universe, "timeframe": TimeFrame.Day, "start": start, "end": now},
        StockBarsRequest)
    if df.empty:
        raise RuntimeError("daily bar pull returned empty frame")
    df = df.reset_index()
    df["session"] = df["timestamp"].dt.tz_convert("America/New_York").dt.date

    per_session_std: list[float] = []
    per_session_mad: list[float] = []
    per_session_iqr: list[float] = []
    per_session_breadth: list[float] = []
    sessions_sorted = sorted(df["session"].unique())
    for sess in sessions_sorted:
        block = df[df["session"] == sess]
        disp = cross_sectional_dispersion_bps(
            open_close_returns(block["open"].tolist(), block["close"].tolist()))
        if disp is None:
            continue
        per_session_std.append(disp["std_bps"])
        per_session_mad.append(disp["robust_mad_std_bps"])
        per_session_iqr.append(disp["robust_iqr_std_bps"])
        per_session_breadth.append(disp["breadth"])

    sigma_std = summarize_distribution(per_session_std)
    sigma_mad = summarize_distribution(per_session_mad)
    sigma_iqr = summarize_distribution(per_session_iqr)
    eff_breadth = effective_breadth(per_session_breadth)

    # names with at least one valid open&close anywhere in the daily window (data-availability).
    valid = df[(df["open"] > 0) & (df["close"] > 0)
               & df["open"].notna() & df["close"].notna()]
    names_with_daily = sorted(valid["symbol"].unique().tolist())

    # ---- 3. Intraday coverage census (BOUNDED window) -------------------------------------
    intraday_start = now - dt.timedelta(days=int(intraday_sessions * 1.6) + 4)
    idf, intraday_feed = _fetch_bars(
        client,
        {"symbol_or_symbols": universe, "timeframe": TimeFrame(1, TimeFrameUnit.Minute),
         "start": intraday_start, "end": now},
        StockBarsRequest)
    coverage: dict[str, dict] = {}
    names_with_intraday: list[str] = []
    if not idf.empty:
        idf = idf.reset_index()
        idf["session"] = idf["timestamp"].dt.tz_convert("America/New_York").dt.date
        # Restrict to regular trading hours minute bars (09:30-16:00 ET) for the coverage rate.
        et = idf["timestamp"].dt.tz_convert("America/New_York")
        rth = idf[(et.dt.time >= dt.time(9, 30)) & (et.dt.time < dt.time(16, 0))].copy()
        rth_sessions = sorted(rth["session"].unique())[-intraday_sessions:]
        rth = rth[rth["session"].isin(rth_sessions)]
        EXPECTED_MIN_PER_SESSION = 390  # full RTH minute count
        for sym in universe:
            sub = rth[rth["symbol"] == sym]
            n_sessions = sub["session"].nunique()
            n_bars = len(sub)
            expected = EXPECTED_MIN_PER_SESSION * max(len(rth_sessions), 1)
            cov = (n_bars / expected) if expected else 0.0
            coverage[sym] = {
                "sessions_present": int(n_sessions),
                "bars": int(n_bars),
                "coverage_frac": round(cov, 4),
            }
            if n_sessions >= 1 and n_bars > 0:
                names_with_intraday.append(sym)
    n_intraday_names = len(names_with_intraday)
    names_no_intraday = [s for s in universe if s not in set(names_with_intraday)]
    no_intraday_frac = (len(names_no_intraday) / len(universe)) if universe else 0.0

    # ---- causal/event-time sigma_oc check on a sample (entry AFTER the open) ----------------
    # Confirm the daily-OHLC sigma_oc is not inflated by the opening cross: recompute open->close
    # using the first executable RTH minute bar AT/AFTER 09:35 ET as the entry (proxy for the
    # event-time contract's first_eligible_fill_ts) and the last RTH minute close as the exit.
    causal_sample = _causal_oc_sample(rth) if (not idf.empty) else {"n": 0}

    # ---- 4. Conservative cost bound (historical RTH quote spread, BOUNDED) -----------------
    # Use the most recent fully-closed session in the daily window as the spread-sample day.
    sample_day = sessions_sorted[-1] if sessions_sorted else now.date()
    cost = _cost_bound(client, universe, quote_sample, sample_day)

    sigma_oc_median = sigma_std.get("median")
    net_band = (net_edge_band_bps(sigma_oc_median, cost["round_trip_bps"])
                if sigma_oc_median is not None else {})

    verdict = decide(sigma_oc_median_bps=sigma_oc_median,
                     n_intraday_names=n_intraday_names,
                     eff_breadth=eff_breadth,
                     cost_bps=cost["round_trip_bps"])

    return {
        "run_ts_utc": run_ts,
        "universe_note": universe_note,
        "universe_n": len(universe),
        "universe": universe,
        "params": {"years": years, "intraday_sessions": intraday_sessions,
                   "quote_sample": quote_sample},
        "data_feeds": {"daily": daily_feed, "intraday": intraday_feed},
        "daily_window": {"start": start.date().isoformat(), "end": now.date().isoformat(),
                         "n_sessions": len(sessions_sorted),
                         "n_names_with_daily": len(names_with_daily)},
        "sigma_oc_bps": {
            "std": sigma_std,
            "robust_mad_std": sigma_mad,
            "robust_iqr_std": sigma_iqr,
            "assumed_band_bps": [ASSUMED_SIGMA_OC_LO_BPS, ASSUMED_SIGMA_OC_HI_BPS],
        },
        "causal_oc_sample": causal_sample,
        "breadth": {"effective_breadth_median_names": eff_breadth,
                    "per_session_breadth_summary": summarize_distribution(per_session_breadth)},
        "intraday_coverage": {
            "sample_sessions": int(min(intraday_sessions, len(rth_sessions)) if not idf.empty else 0),
            "n_names_with_intraday": n_intraday_names,
            "n_names_no_intraday": len(names_no_intraday),
            "frac_no_intraday": round(no_intraday_frac, 4),
            "names_no_intraday": names_no_intraday,
            "per_name": coverage,
        },
        "cost": cost,
        "net_edge_band_bps": net_band,
        "verdict": asdict(verdict),
    }


def _causal_oc_sample(rth) -> dict:  # pragma: no cover - network
    """Event-time sigma_oc on the intraday sample: entry = first RTH bar >= 09:35 ET, exit = last
    RTH close. Confirms the daily-OHLC sigma_oc is not inflated by the opening print/cross."""
    import pandas as pd
    if rth is None or len(rth) == 0:
        return {"n": 0}
    et = rth["timestamp"].dt.tz_convert("America/New_York")
    rth = rth.assign(_et=et, _ettime=et.dt.time)
    per_session_disp: list[float] = []
    for sess, block in rth.groupby("session"):
        rets = []
        for sym, sub in block.groupby("symbol"):
            sub = sub.sort_values("timestamp")
            entry_rows = sub[sub["_ettime"] >= dt.time(9, 35)]
            if entry_rows.empty or sub.empty:
                continue
            entry = float(entry_rows.iloc[0]["open"])
            exit_ = float(sub.iloc[-1]["close"])
            if entry > 0 and exit_ > 0 and math.isfinite(entry) and math.isfinite(exit_):
                rets.append(exit_ / entry - 1.0)
        disp = cross_sectional_dispersion_bps(rets)
        if disp is not None:
            per_session_disp.append(disp["std_bps"])
    summ = summarize_distribution(per_session_disp)
    summ["note"] = ("causal entry at first RTH bar >= 09:35 ET (event-time proxy), exit at last "
                    "RTH close; overnight & opening-cross excluded.")
    return summ


def _cost_bound(client, universe, quote_sample, sample_day) -> dict:  # pragma: no cover - network
    """Cheap conservative round-trip cost bound from BOUNDED *historical RTH* quote spreads.

    Latest-quote endpoints return stale/locked closing quotes when the market is shut (artificially
    huge spreads), so we instead sample a short MIDDAY (16:00-16:05 UTC == noon ET) window on the
    most recent fully-closed session, per-symbol with a small row limit. round_trip = 2 * median
    half-spread, then FLOORED at the documented ~11 bps §A prior so the bound stays conservative
    (the spread is only one leg; the prior also covers impact/slippage). Falls back to the 11 bps
    prior if quotes are unavailable.
    """
    import datetime as _dt
    from alpaca.data.requests import StockQuotesRequest
    from alpaca.data.enums import DataFeed
    sample = universe[:quote_sample]
    # noon-ET midday window on the sample session (16:00-16:05 UTC); end-capped is unnecessary
    # because the session is already fully in the past.
    start = _dt.datetime(sample_day.year, sample_day.month, sample_day.day, 16, 0,
                         tzinfo=_dt.timezone.utc)
    end = start + _dt.timedelta(minutes=5)
    med_half_by_sym: dict[str, float] = {}
    for sym in sample:
        for feed in (DataFeed.SIP, DataFeed.IEX):
            try:
                q = client.get_stock_quotes(StockQuotesRequest(
                    symbol_or_symbols=[sym], start=start, end=end, feed=feed, limit=300))
                df = q.df
            except Exception:
                continue
            if df is None or df.empty:
                continue
            df = df.reset_index()
            df = df[(df["bid_price"] > 0) & (df["ask_price"] > 0)
                    & (df["ask_price"] >= df["bid_price"])]
            if df.empty:
                continue
            mid = (df["bid_price"] + df["ask_price"]) / 2.0
            hs = (0.5 * (df["ask_price"] - df["bid_price"]) / mid * 1e4)
            med_half_by_sym[sym] = float(hs.median())
            break
    if not med_half_by_sym:
        return {"source": "prior", "round_trip_bps": COST_PRIOR_BPS, "n_quotes": 0,
                "note": "no usable historical RTH quotes; using documented ~11 bps prior "
                        "(conservative).", "sample_day": str(sample_day)}
    med_half = statistics.median(med_half_by_sym.values())
    measured_rt = 2.0 * med_half
    p75_rt = 2.0 * _quantiles(list(med_half_by_sym.values()), (0.75,))[0.75]
    rt_conservative = max(measured_rt, COST_PRIOR_BPS)
    return {
        "source": "historical_rth_quote_spread",
        "sample_day": str(sample_day),
        "n_names": len(med_half_by_sym),
        "median_half_spread_bps": med_half,
        "measured_round_trip_bps": measured_rt,
        "p75_round_trip_bps": p75_rt,
        "round_trip_bps": rt_conservative,
        "per_name_half_spread_bps": {k: round(v, 3) for k, v in med_half_by_sym.items()},
        "note": ("round_trip = 2 * median half-spread of a midday (noon-ET) historical RTH quote "
                 "sample, FLOORED at the §A ~11 bps prior (spread is one leg; prior also covers "
                 "impact/slippage). Measured spread confirms the prior is not wildly optimistic."),
    }


def _print_human(res: dict) -> None:
    s = res["sigma_oc_bps"]["std"]
    band = res["sigma_oc_bps"]["assumed_band_bps"]
    v = res["verdict"]
    print("=" * 78)
    print("renquant105 Phase -1 — cheap read-only feasibility")
    print("=" * 78)
    print(f"run_ts_utc          : {res['run_ts_utc']}")
    print(f"universe            : {res['universe_n']} names — {res['universe_note']}")
    dw = res["daily_window"]
    print(f"daily window        : {dw['start']} -> {dw['end']} "
          f"({dw['n_sessions']} sessions, {dw['n_names_with_daily']} names w/ daily)")
    print("-" * 78)
    print("(1) sigma_oc (open->close cross-sectional dispersion, bps) — VERDICT DRIVER")
    print(f"    std-based   : median {s.get('median', float('nan')):.1f}  "
          f"[p25 {s.get('p25', float('nan')):.1f}, p75 {s.get('p75', float('nan')):.1f}]  "
          f"n={s.get('n', 0)}")
    mad = res["sigma_oc_bps"]["robust_mad_std"]
    iqr = res["sigma_oc_bps"]["robust_iqr_std"]
    print(f"    robust(MAD) : median {mad.get('median', float('nan')):.1f}  "
          f"[p25 {mad.get('p25', float('nan')):.1f}, p75 {mad.get('p75', float('nan')):.1f}]")
    print(f"    robust(IQR) : median {iqr.get('median', float('nan')):.1f}  "
          f"[p25 {iqr.get('p25', float('nan')):.1f}, p75 {iqr.get('p75', float('nan')):.1f}]")
    print(f"    ASSUMED band: {band[0]:.0f}-{band[1]:.0f} bps")
    cs = res.get("causal_oc_sample", {})
    if cs.get("n"):
        print(f"    causal check: median {cs.get('median', float('nan')):.1f} bps "
              f"(event-time entry >=09:35 ET, n={cs['n']} sample sessions)")
    print("-" * 78)
    b = res["breadth"]
    print(f"(2) breadth         : effective {b['effective_breadth_median_names']:.1f} names/session "
          f"(median valid cross-section)")
    ic = res["intraday_coverage"]
    print(f"(3) intraday census : {ic['n_names_with_intraday']}/{res['universe_n']} names have "
          f"intraday history in {ic['sample_sessions']}-session sample; "
          f"{ic['frac_no_intraday']*100:.1f}% have NONE")
    print(f"    design claim    : '~50% of names had no intraday history' -> "
          f"{'CONFIRMED' if ic['frac_no_intraday'] >= 0.4 else 'REFUTED'} today "
          f"({ic['frac_no_intraday']*100:.1f}% no-history)")
    c = res["cost"]
    print(f"(4) cost bound      : {c['round_trip_bps']:.1f} bps round-trip ({c['source']})")
    neb = res.get("net_edge_band_bps", {})
    for ic_key, vals in neb.items():
        print(f"    net edge {ic_key} : gross {vals['gross_edge_bps']:.1f} - cost "
              f"{vals['cost_bps']:.1f} = NET {vals['net_edge_bps']:.1f} bps")
    print("=" * 78)
    print(f"VERDICT: {'GO to M0' if v['go'] else 'STOP before M0'}")
    for r in v["reasons"]:
        print(f"  - {r}")
    print("=" * 78)


def _print_plan() -> None:
    print("renquant105 Phase -1 — PLAN (offline; pre-registered thresholds, no network call)")
    print(f"  GO criterion (a): >= {GO_MIN_INTRADAY_NAMES} names with usable intraday history")
    print(f"  GO criterion (b): causal sigma_oc median >= {ASSUMED_SIGMA_OC_LO_BPS:.0f} bps "
          f"(assumed band {ASSUMED_SIGMA_OC_LO_BPS:.0f}-{ASSUMED_SIGMA_OC_HI_BPS:.0f})")
    print(f"  GO criterion (c): effective breadth >= {GO_MIN_EFF_BREADTH:.0f} bets/day")
    print(f"  GO criterion (d): conservative round-trip cost <= {COST_CONSERVATIVE_LEG_BPS:.0f} bps")
    print(f"  edge identity   : gross = IC * sigma_oc * {EDGE_FACTOR}; IC grid {IC_GRID}")
    print("  STOP if ANY of (a)-(d) fails (sigma_oc below band drives a STOP-and-success kill).")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="renquant105 Phase -1 cheap feasibility probe (read-only).")
    ap.add_argument("--years", type=int, default=5, help="daily-bar lookback years for sigma_oc (default 5)")
    ap.add_argument("--intraday-sessions", type=int, default=30,
                    help="BOUNDED minute-bar sample window in sessions (default 30)")
    ap.add_argument("--quote-sample", type=int, default=12,
                    help="number of names to sample latest quotes for the cost bound (default 12)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--offline", action="store_true",
                    help="print the plan + pre-registered thresholds and exit (no network)")
    args = ap.parse_args(argv)

    if args.offline:
        _print_plan()
        return 0

    universe, note = _load_universe()
    res = _run_live(universe, note, args.years, args.intraday_sessions, args.quote_sample)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        _print_human(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
