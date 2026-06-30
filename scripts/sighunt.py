#!/usr/bin/env python
"""
MVP cross-sectional multi-day TREND signal scan.
READ-ONLY: computes ~5 canonical price factors on a daily close panel, measures
raw cross-sectional Spearman rank-IC vs forward multi-day returns, with ONE
shuffle-placebo noise-floor guard. No orders. No git. No canonical writes.

IMPORTANT — this is a RETROSPECTIVE DIAGNOSTIC, not a clean backtest. It applies
the CURRENT renquant-104 golden watchlist back to 2018 and coverage-filters by
realized full-period coverage, which is a survivorship / look-ahead screen. It
CANNOT prove the absence of edge; treat results as a quick directional probe.

Honest overlap handling: the headline IC t-stat is computed on NON-OVERLAPPING
forward windows (step == horizon) so the daily-IC samples are independent. We
also report the naive overlapping IC for transparency.

Reproducibility: pass `--as-of` (pinned end date, NO datetime.now), `--out`,
`--bars-cache`, `--coverage`, and `--refresh`. When `--bars-cache` points at an
existing parquet and `--refresh` is NOT set, the cache is read WITHOUT
instantiating the Alpaca client or requiring credentials. Alpaca is touched only
when refreshing or when no cache is supplied. A `manifest.json` (as-of,
universe-file hash, bar-cache hash, kept-symbol list + hash, all parameters,
code commit) is written next to the outputs.
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

HORIZONS = [5, 20, 60]
COST_BPS = 11.0  # round-trip cost to subtract from L/S decile spread
N_PERM = 200


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


def fetch_bars(universe, start, end):
    """Pull split/dividend-adjusted daily bars from Alpaca. Only called on a
    refresh / cache-miss; requires ALPACA_API_KEY + ALPACA_SECRET_KEY."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment

    try:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
    except KeyError as e:
        sys.exit(f"[fatal] need {e} to fetch bars; supply --bars-cache to read a "
                 f"cached panel without credentials instead.")
    client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    req = StockBarsRequest(
        symbol_or_symbols=universe,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment=Adjustment.ALL,  # split + dividend adjusted
    )
    bars = client.get_stock_bars(req).df
    print(f"[data] raw bars rows={len(bars)}", flush=True)
    close = bars["close"].reset_index()
    close["date"] = pd.to_datetime(close["timestamp"]).dt.tz_localize(None).dt.normalize()
    return close.pivot(index="date", columns="symbol", values="close").sort_index()


def daily_ic(sig, fwd, dates):
    """Spearman rank-IC per date over the cross-section."""
    out = {}
    for d in dates:
        s = sig.loc[d]
        f = fwd.loc[d]
        m = s.notna() & f.notna()
        if m.sum() < 10:
            continue
        rho = spearmanr(s[m].values, f[m].values).correlation
        if rho is not None and not np.isnan(rho):
            out[d] = rho
    return pd.Series(out)


def ls_decile_spread(sig, fwd, dates):
    """Top-decile minus bottom-decile mean forward return per rebalance."""
    spreads = []
    for d in dates:
        s = sig.loc[d].dropna()
        f = fwd.loc[d]
        common = s.index.intersection(f.dropna().index)
        if len(common) < 20:
            continue
        s = s.loc[common]
        f = f.loc[common]
        q = s.rank(pct=True)
        top = f[q >= 0.9].mean()
        bot = f[q <= 0.1].mean()
        if np.isnan(top) or np.isnan(bot):
            continue
        spreads.append(top - bot)
    return np.array(spreads)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars end here.")
    ap.add_argument("--out", default="/tmp/sighunt", help="Output directory.")
    ap.add_argument("--bars-cache", default=None,
                    help="Path to a cached close-panel parquet. If present and "
                         "--refresh is not set, read WITHOUT Alpaca credentials.")
    ap.add_argument("--refresh", action="store_true",
                    help="Force a fresh Alpaca pull (needs credentials), overwriting the cache.")
    ap.add_argument("--coverage", type=float, default=0.55,
                    help="Min full-period coverage to keep a name (shared with robustness.py).")
    ap.add_argument("--config", default=DEFAULT_CFG,
                    help="renquant-104 golden watchlist json (universe source).")
    ap.add_argument("--years", type=int, default=8, help="Panel length in years ending at --as-of.")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    as_of = pd.Timestamp(args.as_of).normalize()
    end = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of
    start = end - timedelta(days=365 * args.years + 30)

    universe = load_universe(args.config)

    cache = args.bars_cache or os.path.join(args.out, "bars.parquet")
    use_cache = os.path.exists(cache) and not args.refresh
    if use_cache:
        # READ-ONLY cache path: NO Alpaca client, NO credentials required.
        px = pd.read_parquet(cache).sort_index()
        # Respect the pinned as-of: never use bars after it.
        px = px[px.index <= as_of.tz_localize(None)]
        print(f"[data] loaded cached close panel {px.shape} from {cache} "
              f"(no credentials used)", flush=True)
    else:
        px = fetch_bars(universe, start, end)
        px.to_parquet(cache)
        print(f"[data] close panel {px.shape} -> {cache}", flush=True)

    # require reasonable coverage (shared --coverage threshold)
    cov = px.notna().mean()
    keep = sorted(cov[cov > args.coverage].index.tolist())
    dropped = sorted(set(px.columns) - set(keep))
    if dropped:
        print(f"[data] dropping {len(dropped)} names with <{args.coverage:.0%} "
              f"coverage: {dropped}", flush=True)
    px = px[keep]
    print(f"[data] final panel: {px.shape[0]} days x {px.shape[1]} names; "
          f"{px.index.min().date()} -> {px.index.max().date()}", flush=True)

    # ---- candidate signals (per day, cross-sectional) ----
    signals = {}
    signals["mom_12_1"] = (px.shift(21) / px.shift(252) - 1.0)
    signals["mom_6_1"] = (px.shift(21) / px.shift(126) - 1.0)
    signals["st_rev_21"] = -1.0 * (px / px.shift(21) - 1.0)
    sma200 = px.rolling(200, min_periods=150).mean()
    signals["ma200_dist"] = px / sma200 - 1.0
    hi252 = px.rolling(252, min_periods=200).max()
    signals["pct_52w_high"] = px / hi252

    def fwd_ret(h):
        return px.shift(-h) / px - 1.0

    rng = np.random.default_rng(42)
    results = []
    for h in HORIZONS:
        fwd = fwd_ret(h)
        valid = px.index[252:-h]
        nonover_dates = valid[::h]  # NON-OVERLAPPING rebalance dates
        for name, sig in signals.items():
            ic = daily_ic(sig, fwd, nonover_dates)
            if len(ic) < 5:
                continue
            mean_ic = ic.mean()
            std_ic = ic.std(ddof=1)
            n = len(ic)
            tstat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else np.nan
            hit = (ic > 0).mean()
            spreads = ls_decile_spread(sig, fwd, nonover_dates)
            gross_bps = np.nanmean(spreads) * 1e4 if len(spreads) else np.nan
            net_bps = gross_bps - COST_BPS if not np.isnan(gross_bps) else np.nan
            ic_daily = daily_ic(sig, fwd, valid)
            results.append(dict(
                signal=name, horizon=h, n_obs=n,
                mean_ic=mean_ic, ic_std=std_ic, t_stat=tstat, hit_rate=hit,
                gross_ls_bps=gross_bps, net_ls_bps=net_bps,
                mean_ic_overlap=ic_daily.mean(),
            ))

    # ---- ONE placebo guard: shuffle forward returns within each date ----
    placebo_floor = {}
    print("[placebo] building shuffle noise floor...", flush=True)
    for h in HORIZONS:
        fwd = fwd_ret(h)
        valid = px.index[252:-h]
        nonover_dates = valid[::h]
        sig = signals["mom_12_1"]  # permutation geometry; null is signal-agnostic
        perm_mean_ics = []
        for _ in range(N_PERM):
            ics = []
            for d in nonover_dates:
                s = sig.loc[d]
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
                perm_mean_ics.append(np.mean(ics))
        perm_mean_ics = np.array(perm_mean_ics)
        placebo_floor[h] = dict(
            mean=float(perm_mean_ics.mean()),
            std=float(perm_mean_ics.std(ddof=1)),
            p95_abs=float(np.percentile(np.abs(perm_mean_ics), 95)),
            p05=float(np.percentile(perm_mean_ics, 5)),
            p95=float(np.percentile(perm_mean_ics, 95)),
        )
        print(f"[placebo] h={h}: floor |mean_ic| p95={placebo_floor[h]['p95_abs']:.4f} "
              f"(perm mean={placebo_floor[h]['mean']:.4f} std={placebo_floor[h]['std']:.4f})", flush=True)

    df = pd.DataFrame(results)
    df["floor_p95_abs"] = df["horizon"].map(lambda h: placebo_floor[h]["p95_abs"])
    df["clears_floor"] = df["mean_ic"].abs() > df["floor_p95_abs"]
    df["ic_over_floor"] = df["mean_ic"].abs() / df["floor_p95_abs"]
    df = df.sort_values(["horizon", "mean_ic"], ascending=[True, False]).reset_index(drop=True)
    df.to_csv(os.path.join(args.out, "results.csv"), index=False)
    with open(os.path.join(args.out, "placebo_floor.json"), "w") as f:
        json.dump(placebo_floor, f, indent=2)

    # ---- manifest: pin everything needed to reproduce / audit this run ----
    symbols = list(px.columns)
    manifest = dict(
        script="scripts/sighunt.py",
        kind="current-watchlist coverage-filtered price-only retrospective diagnostic",
        as_of=args.as_of,
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        universe_config=args.config,
        universe_config_sha256=sha256_file(args.config),
        bars_cache=cache,
        bars_cache_sha256=sha256_file(cache),
        used_cache_without_credentials=bool(use_cache),
        parameters=dict(
            coverage=args.coverage, years=args.years, horizons=HORIZONS,
            cost_bps=COST_BPS, n_perm=N_PERM, seed=42,
        ),
        panel=dict(
            days=int(px.shape[0]), names=int(px.shape[1]),
            start=str(px.index.min().date()), end=str(px.index.max().date()),
        ),
        kept_symbols=symbols,
        kept_symbols_sha256=sha256_text(",".join(symbols)),
    )
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    print("\n================ RANKED RESULTS ================")
    cols = ["signal", "horizon", "n_obs", "mean_ic", "t_stat", "hit_rate",
            "gross_ls_bps", "net_ls_bps", "floor_p95_abs", "ic_over_floor", "clears_floor"]
    print(df[cols].to_string(index=False))
    print("\n================ PLACEBO NOISE FLOOR ================")
    for h in HORIZONS:
        pf = placebo_floor[h]
        print(f"h={h:>3}: perm mean_ic={pf['mean']:+.4f}  std={pf['std']:.4f}  "
              f"|mean_ic| 95th-pct={pf['p95_abs']:.4f}  [5%,95%]=[{pf['p05']:+.4f},{pf['p95']:+.4f}]")
    print(f"\nKept-symbols sha256={manifest['kept_symbols_sha256'][:12]}  "
          f"(shared coverage={args.coverage})")
    print(f"Wrote: {args.out}/results.csv, {args.out}/placebo_floor.json, {args.out}/manifest.json")


if __name__ == "__main__":
    main()
