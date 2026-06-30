#!/usr/bin/env python
"""
Cross-sectional MINUTE-DERIVED feature IC scan on the renquant-104 universe
(DISCOVERY screen + honest OOS holdout). READ-ONLY.

WHAT THIS SETTLES
  Do minute-derived cross-sectional features carry Spearman rank-IC -- standalone
  AND *marginal* over the 5 daily price factors -- at short (1d/3d) and multi-day
  (5d/20d) horizons, measured from a NEXT-SESSION TRADABLE entry, and does any
  candidate effect survive a chronological out-of-sample holdout? This is the cheap
  gate BEFORE any heavy "PatchTST-on-minute" experiment in renquant-model.

CORRECTNESS FIXES vs the first cut (#206 review, haorensjtu-dev, 2026-06-28):
  1. DST-CORRECT RTH: bars are filtered to each session's [open, close) window from
     the XNYS exchange calendar (exchange_calendars), in UTC -- so 09:30-16:00 LOCAL
     including half-days (early closes truncate automatically). The old fixed UTC
     13:30-21:00 union admitted ~12% pre-/after-hours bars that drifted by season.
  2. NEXT-SESSION ENTRY (no look-ahead): a feature for day D is known only AFTER D's
     close. Positions are therefore ENTERED at the OPEN of the next session D+1 (the
     first tradable timestamp) and the horizon-h forward return is close[D+h]/open[D+1]
     - 1 (strictly future of the signal). No "execute at close[D]" assumption.
  3. PROPER FWL MARGINAL IC: BOTH the minute feature AND the forward return are
     residualized cross-sectionally on the SAME 5 daily factors (rank-standardized)
     per date, then the two residuals are Spearman-correlated. (The old code
     residualized only the return and correlated it with the RAW feature -- not a
     valid partial effect.)
  4. MARGINAL PLACEBO: a SEPARATE within-date shuffle floor is built on the
     residualized feature vs residualized return, using the exact FWL pipeline and
     masks, for each horizon -- not the standalone floor.
  5. CHRONOLOGICAL OOS: sessions are split ~70/30 in time. Everything is reported
     DISCOVERY (in-sample) vs OOS (untouched holdout). Winners are *selected on
     discovery only*; the headline test is whether their marginal IC survives OOS.

PIT / NO LOOK-AHEAD: every feature for day D uses ONLY bars with timestamp < D's RTH
close. Forward returns use the daily close panel (reused from sighunt) and the daily
OPEN panel derived from the corrected RTH minute bars; the entry timestamp is the
NEXT session. The pinned --as-of caps both the minute pull and the labels.

Reproducibility mirrors scripts/sighunt.py: pinned --as-of (NO datetime.now in the
math), cache-first minute parquet (read WITHOUT Alpaca creds when present and
--refresh unset), and a manifest.json pinning as-of, universe/min-cache/daily-bars
hashes, kept-symbol list+hash, all parameters, and the code commit.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from minute_rth import rth_filter, session_open_close, DAILY_FACTOR_NAMES, daily_factors

DEFAULT_CFG = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.golden.json"
# ETFs / non-single-name members dropped so the cross-section is comparable stocks.
ETFS = {"SPY", "GLD", "TLT", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY", "XLV"}

# Short / intraday-adjacent AND multi-day (the renquant-105 goal).
HORIZONS = [1, 3, 5, 20]
N_PERM = 200
OOS_FRAC = 0.70  # first 70% of sessions = DISCOVERY; last 30% = OOS holdout
MIN_NAMES = 15   # min cross-section per date for an IC / residualization


def sha256_file(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(
            ["git", "-C", here, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


def load_universe(cfg_path):
    wl = json.load(open(cfg_path))["watchlist"]
    universe = [t for t in wl if t not in ETFS]
    print(f"[universe] {len(universe)} single names "
          f"(dropped {len(set(wl) & ETFS)} ETFs from {len(wl)}) <- {cfg_path}", flush=True)
    return universe


def fetch_minute_bars(universe, start, end, minutes):
    """Pull split/dividend-adjusted intraday bars from Alpaca, batched by symbol.
    Only called on a refresh / cache-miss; requires ALPACA_API_KEY + SECRET."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import Adjustment

    try:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
    except KeyError as e:
        sys.exit(f"[fatal] need {e} to fetch minute bars; supply --min-cache to read "
                 f"a cached panel without credentials instead.")
    client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    tf = TimeFrame(minutes, TimeFrameUnit.Minute)
    frames = []
    for i, sym in enumerate(universe):
        req = StockBarsRequest(
            symbol_or_symbols=[sym],
            timeframe=tf,
            start=start,
            end=end,
            adjustment=Adjustment.ALL,  # split + dividend adjusted
        )
        try:
            df = client.get_stock_bars(req).df
        except Exception as e:
            print(f"[data] {sym}: fetch error {e}", flush=True)
            continue
        if df is None or len(df) == 0:
            print(f"[data] {sym}: no bars", flush=True)
            continue
        frames.append(df)
        if (i + 1) % 10 == 0 or i + 1 == len(universe):
            print(f"[data] pulled {i + 1}/{len(universe)} symbols "
                  f"(last={sym} rows={len(df)})", flush=True)
    if not frames:
        sys.exit("[fatal] no minute bars fetched.")
    out = pd.concat(frames)
    return out


def build_features(minbars, daily_close, kept):
    """From DST-correct RTH intraday bars, build PIT cross-sectional features as-of
    each day's close. Also returns the per-(symbol,session) day OPEN (first RTH bar
    open) so the cost test / next-session label can use a real tradable open.
    Returns (feat_dict, day_open_frame) both date x symbol aligned to the daily index."""
    feats = {name: {} for name in (
        "intraday_rvol", "intraday_mom_last", "open_range", "vwap_dev",
        "overnight_gap", "range_pct", "close_loc", "amihud_illiq",
    )}
    day_open = {}
    prev_close = daily_close.shift(1)

    grouped = minbars.groupby([minbars.index.get_level_values("symbol"), "session"])
    for (sym, sess), g in grouped:
        if sym not in kept:
            continue
        g = g.sort_index()
        c = g["close"].values
        o = g["open"].values
        hi = g["high"].values
        lo = g["low"].values
        vol = g["volume"].values
        vwap_bar = g["vwap"].values
        n = len(c)
        if n < 4:
            continue
        day_o = o[0]
        day_c = c[-1]
        day_hi = float(np.max(hi))
        day_lo = float(np.min(lo))
        # intraday log returns bar-to-bar
        rets = np.diff(np.log(np.clip(c, 1e-9, None)))
        rvol = float(np.sqrt(np.nansum(rets ** 2))) if len(rets) else np.nan
        # last ~2 bars (~30 min for 15-min) momentum
        k = min(2, n - 1)
        mom_last = float(c[-1] / c[-1 - k] - 1.0) if k >= 1 else np.nan
        # opening range: first ~2 bars return (~30 min)
        j = min(2, n - 1)
        open_rng = float(c[j] / o[0] - 1.0) if j >= 1 else np.nan
        # day VWAP from bar vwap weighted by volume (fallback typical price)
        tv = np.nansum(vol)
        if tv > 0 and np.isfinite(vwap_bar).any():
            day_vwap = float(np.nansum(np.where(np.isfinite(vwap_bar), vwap_bar, (hi + lo + c) / 3) * vol) / tv)
        else:
            day_vwap = float(np.nanmean(c))
        vwap_dev = float(day_c / day_vwap - 1.0) if day_vwap > 0 else np.nan
        rng_pct = float((day_hi - day_lo) / day_c) if day_c > 0 else np.nan
        close_loc = float((day_c - day_lo) / (day_hi - day_lo)) if day_hi > day_lo else 0.5
        # Amihud illiquidity proxy: |intraday return| / dollar-volume (scaled)
        dollar_vol = float(np.nansum(np.abs(c) * vol))
        day_ret_abs = abs(float(day_c / day_o - 1.0)) if day_o > 0 else np.nan
        amihud = float(day_ret_abs / dollar_vol * 1e9) if dollar_vol > 0 else np.nan

        feats["intraday_rvol"].setdefault(sess, {})[sym] = rvol
        feats["intraday_mom_last"].setdefault(sess, {})[sym] = mom_last
        feats["open_range"].setdefault(sess, {})[sym] = open_rng
        feats["vwap_dev"].setdefault(sess, {})[sym] = vwap_dev
        feats["range_pct"].setdefault(sess, {})[sym] = rng_pct
        feats["close_loc"].setdefault(sess, {})[sym] = close_loc
        feats["amihud_illiq"].setdefault(sess, {})[sym] = amihud
        day_open.setdefault(sess, {})[sym] = day_o
        # overnight gap needs prev daily close (PIT: known at today's open)
        if sess in prev_close.index and sym in prev_close.columns:
            pcv = prev_close.at[sess, sym]
            if pd.notna(pcv) and pcv > 0:
                feats["overnight_gap"].setdefault(sess, {})[sym] = float(day_o / pcv - 1.0)

    idx = daily_close.index
    out = {}
    for name, dd in feats.items():
        frame = pd.DataFrame.from_dict(dd, orient="index")
        frame = frame.reindex(index=idx, columns=daily_close.columns)
        out[name] = frame.sort_index()
    dofr = pd.DataFrame.from_dict(day_open, orient="index").reindex(
        index=idx, columns=daily_close.columns).sort_index()
    return out, dofr


def rank_z(series):
    """Cross-sectional rank -> z within a single date (NaN-safe over the given mask)."""
    r = series.rank()
    return (r - r.mean()) / (r.std(ddof=0) + 1e-12)


def residualize_panel(panel, factors, dates):
    """Cross-sectionally regress `panel` (date x symbol) on the rank-standardized
    daily factors per date; return the residual panel. Used to residualize BOTH the
    forward return AND the minute feature on the SAME controls (proper FWL)."""
    resid = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
    fac_names = list(factors.keys())
    for d in dates:
        if d not in panel.index:
            continue
        y = panel.loc[d]
        ok = y.notna()
        for fn in fac_names:
            ok = ok & factors[fn].loc[d].notna()
        if ok.sum() < MIN_NAMES:
            continue
        yv = y[ok].values.astype(float)
        X = [np.ones(int(ok.sum()))]
        for fn in fac_names:
            X.append(rank_z(factors[fn].loc[d][ok]).values)
        X = np.column_stack(X)
        try:
            beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
            r = yv - X @ beta
        except Exception:
            continue
        resid.loc[d, ok.index[ok]] = r
    return resid


def daily_ic(sig, fwd, dates):
    out = {}
    for d in dates:
        if d not in sig.index or d not in fwd.index:
            continue
        s = sig.loc[d]
        f = fwd.loc[d]
        m = s.notna() & f.notna()
        if m.sum() < 10:
            continue
        rho = spearmanr(s[m].values, f[m].values).correlation
        if rho is not None and not np.isnan(rho):
            out[d] = rho
    return pd.Series(out)


def nw_tstat(x, lag):
    """Newey-West t-stat for the mean of a (possibly autocorrelated) series."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return np.nan
    mu = x.mean()
    e = x - mu
    gamma0 = (e @ e) / n
    var = gamma0
    for L in range(1, lag + 1):
        if L >= n:
            break
        w = 1.0 - L / (lag + 1.0)
        cov = (e[L:] @ e[:-L]) / n
        var += 2.0 * w * cov
    se = np.sqrt(max(var, 0.0) / n)
    return mu / se if se > 0 else np.nan


def marginal_placebo_floor(resid_feat, resid_fwd, reb_dates, rng, n_perm):
    """Within-date shuffle floor on the RESIDUALIZED feature vs RESIDUALIZED return,
    using the exact FWL residuals + masks. Returns the |mean_ic| 95th-pct floor."""
    perm_means = []
    for _ in range(n_perm):
        ics = []
        for d in reb_dates:
            if d not in resid_feat.index or d not in resid_fwd.index:
                continue
            s = resid_feat.loc[d]
            f = resid_fwd.loc[d]
            m = s.notna() & f.notna()
            if m.sum() < 10:
                continue
            fv = f[m].values.copy()
            rng.shuffle(fv)
            rho = spearmanr(s[m].values, fv).correlation
            if rho is not None and not np.isnan(rho):
                ics.append(rho)
        if ics:
            perm_means.append(np.mean(ics))
    perm_means = np.array(perm_means) if perm_means else np.array([0.0])
    return float(np.percentile(np.abs(perm_means), 95))


def scan_window(label, feats, fwd_by_h, factors, dates_by_h, rng, n_perm,
                marg_floor_feature):
    """Run the standalone + proper-FWL marginal IC scan over a set of rebalance dates
    per horizon. `marg_floor_feature` is the feature whose residual is used to build
    the marginal placebo floor (one floor per horizon, feature-agnostic null)."""
    results = []
    marg_floor = {}
    for h in HORIZONS:
        fwd = fwd_by_h[h]
        nonover = dates_by_h[h]
        if len(nonover) < 5:
            continue
        # residualize the forward return ONCE per horizon (shared controls)
        resid_fwd = residualize_panel(fwd, factors, nonover)
        # marginal placebo floor: residual-of-a-feature vs residual-return null
        resid_floor_feat = residualize_panel(feats[marg_floor_feature], factors, nonover)
        marg_floor[h] = marginal_placebo_floor(resid_floor_feat, resid_fwd, nonover, rng, n_perm)
        for name, sig in feats.items():
            ic = daily_ic(sig, fwd, nonover)
            if len(ic) < 5:
                continue
            mean_ic = ic.mean()
            n = len(ic)
            tstat = nw_tstat(ic.values, lag=min(5, n - 1))
            hit = (ic > 0).mean()
            # PROPER FWL: residualize the FEATURE on the same controls, then correlate
            # residual feature vs residual forward return.
            resid_feat = residualize_panel(sig, factors, nonover)
            ic_marg = daily_ic(resid_feat, resid_fwd, nonover)
            marg_mean = ic_marg.mean() if len(ic_marg) else np.nan
            marg_t = nw_tstat(ic_marg.values, lag=min(5, len(ic_marg) - 1)) if len(ic_marg) >= 3 else np.nan
            results.append(dict(
                window=label, feature=name, horizon=h, n_obs=n,
                mean_ic=mean_ic, nw_t=tstat, hit_rate=hit,
                marg_ic=marg_mean, marg_nw_t=marg_t,
            ))
    return results, marg_floor


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars + labels end here.")
    ap.add_argument("--out", default="/tmp/rq206f_out", help="Output directory.")
    ap.add_argument("--min-cache", default="/tmp/minfeat_out/minbars.parquet",
                    help="Cached intraday bar parquet. If present and --refresh is "
                         "not set, read WITHOUT Alpaca credentials.")
    ap.add_argument("--daily-bars", default="/tmp/sighunt/bars.parquet",
                    help="Daily close-panel parquet (reused from sighunt) for "
                         "forward returns + daily factors.")
    ap.add_argument("--refresh", action="store_true",
                    help="Force a fresh Alpaca pull (needs credentials), overwriting the cache.")
    ap.add_argument("--minutes", type=int, default=15,
                    help="Intraday bar size in minutes (15 default; smaller = larger pull).")
    ap.add_argument("--years", type=float, default=2.5,
                    help="Minute-bar window length in years ending at --as-of.")
    ap.add_argument("--coverage", type=float, default=0.55,
                    help="Min full-period DAILY coverage to keep a name (shared w/ sighunt).")
    ap.add_argument("--oos-frac", type=float, default=OOS_FRAC,
                    help="Fraction of sessions used for DISCOVERY (rest = OOS holdout).")
    ap.add_argument("--config", default=DEFAULT_CFG,
                    help="renquant-104 golden watchlist json (universe source).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    as_of = pd.Timestamp(args.as_of).normalize()
    end = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of
    start = end - timedelta(days=int(365 * args.years) + 5)

    universe = load_universe(args.config)

    # ---- daily close panel (reused) for labels + daily factors + coverage ----
    px = pd.read_parquet(args.daily_bars).sort_index()
    px = px[px.index <= as_of.tz_localize(None)]
    cov = px.notna().mean()
    kept = sorted(cov[cov > args.coverage].index.tolist())
    px = px[[c for c in kept if c in px.columns]]
    print(f"[daily] panel {px.shape[0]}d x {px.shape[1]}n "
          f"{px.index.min().date()}->{px.index.max().date()}", flush=True)

    # ---- minute bars: cache-first ----
    cache = args.min_cache or os.path.join(args.out, "minbars.parquet")
    use_cache = os.path.exists(cache) and not args.refresh
    if use_cache:
        mb = pd.read_parquet(cache)
        print(f"[data] loaded cached intraday panel {mb.shape} from {cache} "
              f"(no credentials used)", flush=True)
    else:
        mb = fetch_minute_bars(universe, start, end, args.minutes)
        mb.to_parquet(cache)
        print(f"[data] intraday panel {mb.shape} -> {cache}", flush=True)

    # PIT: never use bars after the as-of close
    ts = mb.index.get_level_values("timestamp")
    mb = mb[ts.tz_convert("UTC").normalize().tz_localize(None) <= as_of]
    # DST-correct RTH filter via the XNYS exchange calendar (half-days included).
    mb = rth_filter(mb)
    n_sess = mb["session"].nunique()
    print(f"[data] RTH intraday rows={len(mb)} sessions={n_sess} "
          f"{mb['session'].min().date()}->{mb['session'].max().date()} "
          f"(DST-correct XNYS calendar filter)", flush=True)

    feats, day_open = build_features(mb, px, set(px.columns))
    for name, fr in feats.items():
        nz = fr.notna().sum().sum()
        print(f"[feat] {name:18s} non-null cells={nz}", flush=True)

    factors = daily_factors(px)

    # ---- NEXT-SESSION TRADABLE forward returns (no look-ahead) ----
    # Feature for day D known after D's close -> ENTER at OPEN of session D+1.
    # horizon-h forward return = close[D+h] / open[D+1] - 1  (entry t+1 open).
    # day_open[D+1] is aligned to the daily index; shift to map D -> D+1 open.
    next_open = day_open.shift(-1)  # open at the NEXT session, indexed at D

    def fwd_ret_next(h):
        # exit at close of session D+h, entry at open of session D+1
        exit_close = px.shift(-h)
        return exit_close / next_open - 1.0

    # restrict scoring to days that have a minute signal AND a tradable next open
    min_days = feats["intraday_rvol"].dropna(how="all").index
    sessions = [d for d in px.index if d in set(min_days)]
    sessions = sorted(sessions)

    # chronological OOS split
    cut = int(len(sessions) * args.oos_frac)
    disc_dates = set(sessions[:cut])
    oos_dates = set(sessions[cut:])
    split_date = sessions[cut] if cut < len(sessions) else None
    print(f"[oos] {len(sessions)} signal-sessions -> DISCOVERY {len(disc_dates)} "
          f"(<= {sessions[cut-1].date()}) | OOS {len(oos_dates)} (>= {split_date.date()})",
          flush=True)

    fwd_by_h = {h: fwd_ret_next(h) for h in HORIZONS}

    def dates_for(h, pool):
        # need a realized exit: close[D+h] must exist AND entry open[D+1] must exist
        valid = [d for d in sessions if d in pool]
        last_ok = px.index[max(0, len(px.index) - 1 - h)]
        valid = [d for d in valid if d <= last_ok]
        # de-overlap by horizon for the t-stat
        return valid[::h]

    disc_dates_by_h = {h: dates_for(h, disc_dates) for h in HORIZONS}
    oos_dates_by_h = {h: dates_for(h, oos_dates) for h in HORIZONS}

    rng = np.random.default_rng(42)

    # DISCOVERY scan (select winners here)
    disc_res, disc_floor = scan_window(
        "discovery", feats, fwd_by_h, factors, disc_dates_by_h, rng, N_PERM,
        marg_floor_feature="intraday_rvol")
    # OOS scan (report the SAME features, untouched holdout)
    oos_res, oos_floor = scan_window(
        "oos", feats, fwd_by_h, factors, oos_dates_by_h, rng, N_PERM,
        marg_floor_feature="intraday_rvol")

    df = pd.DataFrame(disc_res + oos_res)
    df["marg_floor_p95"] = df.apply(
        lambda r: (disc_floor if r["window"] == "discovery" else oos_floor).get(r["horizon"], np.nan),
        axis=1)
    df["marg_over_floor"] = df["marg_ic"].abs() / df["marg_floor_p95"]
    df["marg_clears_floor"] = df["marg_ic"].abs() > df["marg_floor_p95"]
    df = df.sort_values(["window", "horizon", "marg_over_floor"],
                        ascending=[True, True, False]).reset_index(drop=True)
    df.to_csv(os.path.join(args.out, "results.csv"), index=False)

    floors = dict(
        discovery={int(h): disc_floor.get(h) for h in HORIZONS},
        oos={int(h): oos_floor.get(h) for h in HORIZONS},
    )
    with open(os.path.join(args.out, "marginal_placebo_floor.json"), "w") as f:
        json.dump(floors, f, indent=2)

    # ---- select short-horizon winners on DISCOVERY, test them on OOS ----
    disc = df[df.window == "discovery"]
    winners = disc[(disc.horizon.isin([1, 3])) & (disc.marg_clears_floor)
                   & (disc.marg_ic > 0) & (disc.marg_nw_t >= 3.0)]
    winner_keys = sorted(set(zip(winners.feature, winners.horizon)))
    oos = df[df.window == "oos"].set_index(["feature", "horizon"])
    survived = []
    for feat, h in winner_keys:
        row = oos.loc[(feat, h)] if (feat, h) in oos.index else None
        ok = bool(row is not None and row["marg_clears_floor"] and row["marg_ic"] > 0)
        survived.append(dict(
            feature=feat, horizon=int(h),
            disc_marg_ic=float(disc.set_index(["feature", "horizon"]).loc[(feat, h), "marg_ic"]),
            disc_marg_t=float(disc.set_index(["feature", "horizon"]).loc[(feat, h), "marg_nw_t"]),
            oos_marg_ic=float(row["marg_ic"]) if row is not None else None,
            oos_marg_t=float(row["marg_nw_t"]) if row is not None else None,
            oos_floor=float(oos_floor.get(h)) if oos_floor.get(h) is not None else None,
            survived_oos=ok,
        ))
    with open(os.path.join(args.out, "oos_winners.json"), "w") as f:
        json.dump(survived, f, indent=2)

    symbols = list(px.columns)
    manifest = dict(
        script="scripts/minute_feature_scan.py",
        kind="renquant-104 minute-derived cross-sectional feature IC scan "
             "(DST-correct RTH, next-session entry, proper FWL marginal IC, chronological OOS)",
        as_of=args.as_of,
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        universe_config=args.config,
        universe_config_sha256=sha256_file(args.config),
        min_cache=cache,
        min_cache_sha256=sha256_file(cache),
        daily_bars=args.daily_bars,
        daily_bars_sha256=sha256_file(args.daily_bars),
        used_cache_without_credentials=bool(use_cache),
        rth_filter="XNYS exchange_calendars [session_open, session_close) UTC (half-days included)",
        entry_timing="next-session OPEN (feature known after close[D]; enter open[D+1]); "
                     "fwd ret = close[D+h]/open[D+1] - 1",
        marginal_ic="proper FWL: residualize BOTH feature and forward return on the "
                    "5 rank-standardized daily factors, then Spearman-correlate residuals",
        oos="chronological %.0f/%.0f split; winners selected on DISCOVERY, reported on OOS"
            % (args.oos_frac * 100, (1 - args.oos_frac) * 100),
        parameters=dict(
            minutes=args.minutes, years=args.years, coverage=args.coverage,
            horizons=HORIZONS, n_perm=N_PERM, seed=42, oos_frac=args.oos_frac,
            daily_factors=DAILY_FACTOR_NAMES,
        ),
        intraday_panel=dict(
            sessions=int(n_sess), rth_rows=int(len(mb)),
            start=str(mb["session"].min().date()), end=str(mb["session"].max().date()),
        ),
        daily_panel=dict(days=int(px.shape[0]), names=int(px.shape[1])),
        discovery_sessions=int(len(disc_dates)),
        oos_sessions=int(len(oos_dates)),
        oos_split_date=str(split_date.date()) if split_date is not None else None,
        kept_symbols=symbols,
        kept_symbols_sha256=sha256_text(",".join(symbols)),
    )
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    print("\n========= DISCOVERY: marginal (proper FWL) + standalone IC =========")
    cols = ["feature", "horizon", "n_obs", "mean_ic", "nw_t",
            "marg_ic", "marg_nw_t", "marg_over_floor", "marg_clears_floor"]
    print(df[df.window == "discovery"][cols].to_string(index=False))
    print("\n========= OOS HOLDOUT (untouched): same features =========")
    print(df[df.window == "oos"][cols].to_string(index=False))
    print("\n========= MARGINAL PLACEBO FLOOR (|mean_ic| 95th pct) =========")
    for w, fl in (("discovery", disc_floor), ("oos", oos_floor)):
        print(f"  {w:9s}: " + "  ".join(f"h{h}={fl.get(h, float('nan')):.4f}" for h in HORIZONS))
    print("\n========= DISCOVERY winners -> OOS survival =========")
    if survived:
        for s in survived:
            verdict = "SURVIVED" if s["survived_oos"] else "DID NOT SURVIVE"
            print(f"  {s['feature']:18s} h{s['horizon']}: disc marg_IC {s['disc_marg_ic']:+.4f} "
                  f"(t {s['disc_marg_t']:.2f}) -> OOS marg_IC "
                  f"{(s['oos_marg_ic'] if s['oos_marg_ic'] is not None else float('nan')):+.4f} "
                  f"(t {(s['oos_marg_t'] if s['oos_marg_t'] is not None else float('nan')):.2f}, "
                  f"floor {(s['oos_floor'] if s['oos_floor'] is not None else float('nan')):.4f}) "
                  f"=> {verdict}")
    else:
        print("  (no discovery winner cleared marg-floor + marg t>=3 at 1d/3d)")
    print(f"\nWrote: {args.out}/results.csv, marginal_placebo_floor.json, "
          f"oos_winners.json, manifest.json")


if __name__ == "__main__":
    main()
