#!/usr/bin/env python
"""
MVP cross-sectional MINUTE-DERIVED feature IC scan on the renquant-104 universe.

READ-ONLY: pulls intraday (15-minute) bars for the single-name universe over a
BOUNDED recent window, derives ~8 point-in-time cross-sectional features per name
per day (as-of each day's close), and measures raw Spearman rank-IC vs forward
1d/3d (short / intraday-adjacent) AND 5d/20d (multi-day, the renquant-105 goal).
It reports, for every feature x horizon:
  - mean IC, Newey-West / block t-stat, hit-rate, IC / within-date-shuffle-floor
  - MARGINAL IC: IC against the forward return RESIDUALIZED on the daily price
    factors (mom_12_1, mom_6_1, st_rev_21, ma200_dist, pct_52w_high) -- i.e. does
    the minute feature add cross-sectional signal ON TOP of the daily factors.
No orders. No git. No canonical writes. Output/cache under --out (default /tmp).

WHY 15-MINUTE BARS: 1-minute over 134 names x ~2.5y RTH is ~26M rows -- too large
to pull reliably and rate-limit-prone. 15-min (26 RTH bars/day) is ample to derive
intraday realized vol, opening-range, last-30/60-min momentum, VWAP deviation,
range / close-location-in-range, overnight gap, and an Amihud illiquidity / signed
order-flow proxy. The granularity choice is stated in the manifest and the doc.

PIT / NO LOOK-AHEAD: every feature for day D uses ONLY bars with timestamp <= D's
RTH close. Forward returns use the DAILY close panel (reused from sighunt's
bars.parquet) shifted -h, so the label is strictly in the future. RTH only
(13:30-20:00 UTC). The pinned --as-of caps both the minute pull and the labels.

CAVEATS (stated, not hidden): bounded recent window (survivorship: current
watchlist applied back); 15-min granularity (coarser than 1-min microstructure);
overlapping forward windows for the headline are de-overlapped (step==horizon) for
the t-stat, naive-overlap IC reported alongside. This is a CHEAP GATE, not proof.

Reproducibility mirrors scripts/sighunt.py: pinned --as-of (NO datetime.now in the
math), cache-first minute parquet (read WITHOUT Alpaca creds when present and
--refresh is unset), and a manifest.json pinning as-of, universe-file hash,
min-bar-cache hash, daily-bars hash, kept-symbol list+hash, all parameters, and
code commit.
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

DEFAULT_CFG = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.golden.json"
# ETFs / non-single-name members dropped so the cross-section is comparable stocks.
ETFS = {"SPY", "GLD", "TLT", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY", "XLV"}

# Short / intraday-adjacent AND multi-day (the renquant-105 goal).
HORIZONS = [1, 3, 5, 20]
N_PERM = 200
# RTH in UTC (US equities 09:30-16:00 ET; data is UTC). DST-naive but the cross
# section is computed per-day from whatever RTH bars exist; a 1h DST shift does not
# bias a same-day cross-sectional rank. We keep 13:30-20:00 UTC (EDT) and also
# admit 14:30-21:00 (EST) by simply taking bars within the union session window.
RTH_START_UTC = "13:30"
RTH_END_UTC = "21:00"  # union upper bound to admit both EDT/EST; pre-market excluded


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


def to_rth(df):
    """Filter a (symbol,timestamp) bar frame to RTH (UTC) and add a session date."""
    ts = df.index.get_level_values("timestamp")
    # Keep bars whose UTC wall-clock time is within the union RTH window.
    tt = ts.tz_convert("UTC").time
    lo = pd.Timestamp(RTH_START_UTC).time()
    hi = pd.Timestamp(RTH_END_UTC).time()
    mask = np.array([(t >= lo) and (t <= hi) for t in tt])
    df = df[mask].copy()
    sess = df.index.get_level_values("timestamp").tz_convert("UTC").normalize().tz_localize(None)
    df["session"] = sess
    return df


def build_features(minbars, daily_close, kept):
    """From RTH intraday bars, build PIT cross-sectional features as-of each day's
    close. Returns dict feature_name -> (date x symbol) DataFrame aligned to the
    daily-close panel's date index."""
    feats = {name: {} for name in (
        "intraday_rvol", "intraday_mom_last", "open_range", "vwap_dev",
        "overnight_gap", "range_pct", "close_loc", "amihud_illiq",
    )}
    prev_close = daily_close.shift(1)

    # group once per (symbol, session)
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
        # overnight gap needs prev daily close (PIT: known at today's open)
        pc = prev_close.get(sym)
        if pc is not None and sess in prev_close.index:
            pcv = prev_close.at[sess, sym] if sym in prev_close.columns else np.nan
            if pd.notna(pcv) and pcv > 0:
                feats["overnight_gap"].setdefault(sess, {})[sym] = float(day_o / pcv - 1.0)

    # assemble into date x symbol frames aligned to daily index
    idx = daily_close.index
    out = {}
    for name, dd in feats.items():
        frame = pd.DataFrame.from_dict(dd, orient="index")
        frame = frame.reindex(index=idx, columns=daily_close.columns)
        out[name] = frame.sort_index()
    return out


def daily_factors(px):
    """The same canonical daily price factors used by sighunt, for marginal-IC."""
    f = {}
    f["mom_12_1"] = (px.shift(21) / px.shift(252) - 1.0)
    f["mom_6_1"] = (px.shift(21) / px.shift(126) - 1.0)
    f["st_rev_21"] = -1.0 * (px / px.shift(21) - 1.0)
    sma200 = px.rolling(200, min_periods=150).mean()
    f["ma200_dist"] = px / sma200 - 1.0
    hi252 = px.rolling(252, min_periods=200).max()
    f["pct_52w_high"] = px / hi252
    return f


def residualize_fwd(fwd, factors, dates):
    """Cross-sectionally regress forward return on rank-standardized daily factors
    per date; return residual forward return (date x symbol). This isolates the
    component of the label NOT explained by the daily factors -> marginal IC."""
    resid = pd.DataFrame(index=fwd.index, columns=fwd.columns, dtype=float)
    fac_names = list(factors.keys())
    for d in dates:
        y = fwd.loc[d]
        m = y.notna()
        if m.sum() < 15:
            continue
        cols = []
        ok = m.copy()
        for fn in fac_names:
            fv = factors[fn].loc[d]
            ok = ok & fv.notna()
        if ok.sum() < 15:
            continue
        yv = y[ok].values.astype(float)
        X = []
        for fn in fac_names:
            r = factors[fn].loc[d][ok].rank()
            r = (r - r.mean()) / (r.std(ddof=0) + 1e-12)
            X.append(r.values)
        X = np.column_stack([np.ones(ok.sum())] + X)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars + labels end here.")
    ap.add_argument("--out", default="/tmp/minfeat_out", help="Output directory.")
    ap.add_argument("--min-cache", default=None,
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
    mb = to_rth(mb)
    n_sess = mb["session"].nunique()
    print(f"[data] RTH intraday rows={len(mb)} sessions={n_sess} "
          f"{mb['session'].min().date()}->{mb['session'].max().date()}", flush=True)

    feats = build_features(mb, px, set(px.columns))
    for name, fr in feats.items():
        nz = fr.notna().sum().sum()
        print(f"[feat] {name:18s} non-null cells={nz}", flush=True)

    factors = daily_factors(px)

    def fwd_ret(h):
        return px.shift(-h) / px - 1.0

    # restrict scoring to days that have minute coverage
    min_days = feats["intraday_rvol"].dropna(how="all").index
    rng = np.random.default_rng(42)
    results = []
    for h in HORIZONS:
        fwd = fwd_ret(h)
        valid = [d for d in min_days if d in px.index]
        valid = [d for d in valid if d <= px.index[-1]]
        # drop tail where label is unavailable
        valid = [d for d in valid if d <= px.index[max(0, len(px.index) - 1 - h)]]
        nonover = valid[::h]  # de-overlapped rebalance dates for the t-stat
        resid = residualize_fwd(fwd, factors, valid)
        for name, sig in feats.items():
            ic = daily_ic(sig, fwd, nonover)
            if len(ic) < 5:
                continue
            mean_ic = ic.mean()
            std_ic = ic.std(ddof=1)
            n = len(ic)
            tstat = nw_tstat(ic.values, lag=min(5, n - 1))
            hit = (ic > 0).mean()
            ic_overlap = daily_ic(sig, fwd, valid)
            # marginal IC vs residualized forward return
            ic_marg = daily_ic(sig, resid, nonover)
            marg_mean = ic_marg.mean() if len(ic_marg) else np.nan
            marg_t = nw_tstat(ic_marg.values, lag=min(5, len(ic_marg) - 1)) if len(ic_marg) >= 3 else np.nan
            results.append(dict(
                feature=name, horizon=h, n_obs=n,
                mean_ic=mean_ic, ic_std=std_ic, nw_t=tstat, hit_rate=hit,
                mean_ic_overlap=ic_overlap.mean(),
                marg_ic=marg_mean, marg_nw_t=marg_t,
            ))

    # ---- shuffle placebo floor (within-date label shuffle) ----
    placebo_floor = {}
    print("[placebo] building within-date shuffle noise floor...", flush=True)
    sig0 = feats["intraday_rvol"]
    for h in HORIZONS:
        fwd = fwd_ret(h)
        valid = [d for d in min_days if d in px.index]
        valid = [d for d in valid if d <= px.index[max(0, len(px.index) - 1 - h)]]
        nonover = valid[::h]
        perm_means = []
        for _ in range(N_PERM):
            ics = []
            for d in nonover:
                if d not in sig0.index or d not in fwd.index:
                    continue
                s = sig0.loc[d]
                f = fwd.loc[d]
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
        perm_means = np.array(perm_means)
        placebo_floor[h] = dict(
            mean=float(perm_means.mean()), std=float(perm_means.std(ddof=1)),
            p95_abs=float(np.percentile(np.abs(perm_means), 95)),
            p05=float(np.percentile(perm_means, 5)), p95=float(np.percentile(perm_means, 95)),
        )
        print(f"[placebo] h={h}: |mean_ic| p95 floor={placebo_floor[h]['p95_abs']:.4f}", flush=True)

    df = pd.DataFrame(results)
    df["floor_p95_abs"] = df["horizon"].map(lambda h: placebo_floor[h]["p95_abs"])
    df["ic_over_floor"] = df["mean_ic"].abs() / df["floor_p95_abs"]
    df["clears_floor"] = df["mean_ic"].abs() > df["floor_p95_abs"]
    df["marg_over_floor"] = df["marg_ic"].abs() / df["floor_p95_abs"]
    df["marg_clears_floor"] = df["marg_ic"].abs() > df["floor_p95_abs"]
    df = df.sort_values(["horizon", "ic_over_floor"], ascending=[True, False]).reset_index(drop=True)
    df.to_csv(os.path.join(args.out, "results.csv"), index=False)
    with open(os.path.join(args.out, "placebo_floor.json"), "w") as f:
        json.dump(placebo_floor, f, indent=2)

    symbols = list(px.columns)
    manifest = dict(
        script="scripts/minute_feature_scan.py",
        kind="renquant-104 minute-derived cross-sectional feature IC scan (cheap gate)",
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
        parameters=dict(
            minutes=args.minutes, years=args.years, coverage=args.coverage,
            horizons=HORIZONS, n_perm=N_PERM, seed=42,
            rth_start_utc=RTH_START_UTC, rth_end_utc=RTH_END_UTC,
        ),
        intraday_panel=dict(
            sessions=int(n_sess), rth_rows=int(len(mb)),
            start=str(mb["session"].min().date()), end=str(mb["session"].max().date()),
        ),
        daily_panel=dict(days=int(px.shape[0]), names=int(px.shape[1])),
        kept_symbols=symbols,
        kept_symbols_sha256=sha256_text(",".join(symbols)),
    )
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    print("\n================ FEATURE x HORIZON IC (standalone + marginal) ================")
    cols = ["feature", "horizon", "n_obs", "mean_ic", "nw_t", "hit_rate",
            "ic_over_floor", "clears_floor", "marg_ic", "marg_nw_t",
            "marg_over_floor", "marg_clears_floor"]
    print(df[cols].to_string(index=False))
    print("\n================ PLACEBO NOISE FLOOR ================")
    for h in HORIZONS:
        pf = placebo_floor[h]
        print(f"h={h:>3}: perm mean_ic={pf['mean']:+.4f}  |mean_ic| 95th-pct={pf['p95_abs']:.4f}  "
              f"[5%,95%]=[{pf['p05']:+.4f},{pf['p95']:+.4f}]")
    print(f"\nKept-symbols sha256={manifest['kept_symbols_sha256'][:12]} (coverage={args.coverage})")
    print(f"Wrote: {args.out}/results.csv, placebo_floor.json, manifest.json")


if __name__ == "__main__":
    main()
