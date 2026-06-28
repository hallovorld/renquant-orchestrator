#!/usr/bin/env python
"""
Robustness follow-up for mom_12_1, the only candidate that cleared the placebo
floor at usable N (h=5). Runs on the IDENTICAL panel as scripts/sighunt.py by
sharing the SAME --coverage threshold (and, when present, reusing sighunt's
manifest kept_symbols so both scripts test the exact same cross-section).

Checks, on the cached close panel (READ-ONLY, no Alpaca credentials needed):
  (A) Overlapping daily IC with Newey-West HAC t-stat (lag=h) — honest overlap correction.
  (B) Two-half sub-sample stability (is the IC present in both halves?).
  (C) Yearly IC breakdown (is it one lucky year?).

This is a RETROSPECTIVE DIAGNOSTIC on the current watchlist (survivorship /
look-ahead screen); it cannot prove absence of edge.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def daily_ic_series(sig, f, dates):
    out = {}
    for d in dates:
        s = sig.loc[d]
        fr = f.loc[d]
        m = s.notna() & fr.notna()
        if m.sum() < 10:
            continue
        rho = spearmanr(s[m].values, fr[m].values).correlation
        if rho is not None and not np.isnan(rho):
            out[d] = rho
    return pd.Series(out)


def nw_tstat(x, lag):
    x = np.asarray(x)
    n = len(x)
    mu = x.mean()
    e = x - mu
    g0 = np.dot(e, e) / n
    var = g0
    for k in range(1, lag + 1):
        if k >= n:
            break
        w = 1 - k / (lag + 1)
        gk = np.dot(e[k:], e[:-k]) / n
        var += 2 * w * gk
    se = np.sqrt(var / n)
    return mu, mu / se if se > 0 else np.nan, n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True, help="Pinned end date YYYY-MM-DD (no datetime.now).")
    ap.add_argument("--out", default="/tmp/sighunt", help="Dir with the cached panel + manifest.")
    ap.add_argument("--bars-cache", default=None, help="Cached close-panel parquet (no creds needed).")
    ap.add_argument("--coverage", type=float, default=0.55,
                    help="SHARED coverage threshold — must match sighunt.py for an identical panel.")
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of).normalize()
    cache = args.bars_cache or os.path.join(args.out, "bars.parquet")
    if not os.path.exists(cache):
        raise SystemExit(f"[fatal] bars cache not found: {cache} (run sighunt.py first or pass --bars-cache)")
    px = pd.read_parquet(cache).sort_index()
    px = px[px.index <= as_of]  # respect the pinned as-of

    # Prefer the EXACT kept-symbol list from sighunt's manifest so both scripts
    # run on the identical panel; otherwise fall back to the shared --coverage.
    manifest_path = os.path.join(args.out, "manifest.json")
    kept = None
    if os.path.exists(manifest_path):
        man = json.load(open(manifest_path))
        if abs(man.get("parameters", {}).get("coverage", -1) - args.coverage) < 1e-9:
            kept = man.get("kept_symbols")
    if kept:
        keep = [s for s in kept if s in px.columns]
        print(f"[panel] using {len(keep)} kept_symbols from {manifest_path} "
              f"(coverage={args.coverage})")
    else:
        cov = px.notna().mean()
        keep = sorted(cov[cov > args.coverage].index.tolist())
        print(f"[panel] coverage>{args.coverage} -> {len(keep)} names "
              f"(no matching manifest; recomputed)")
    px = px[keep]
    print(f"[panel] {px.shape[0]} days x {px.shape[1]} names; "
          f"{px.index.min().date()}->{px.index.max().date()}")

    sig = px.shift(21) / px.shift(252) - 1.0  # mom_12_1

    def fwd(h):
        return px.shift(-h) / px - 1.0

    for h in (5, 20):
        f = fwd(h)
        valid = px.index[252:-h]
        ic = daily_ic_series(sig, f, valid)
        mu, t_nw, n = nw_tstat(ic.values, lag=h)
        print(f"\n=== mom_12_1 @ h={h} (overlapping daily IC, Newey-West lag={h}) ===")
        hit = (ic > 0).mean()
        print(f"  n_days={n}  mean_ic={mu:+.4f}  NW t-stat={t_nw:+.2f}  hit={hit:.3f}")
        half = len(ic) // 2
        a, b = ic.iloc[:half], ic.iloc[half:]
        print(f"  half-1 ({a.index.min().date()}..{a.index.max().date()}) mean_ic={a.mean():+.4f}")
        print(f"  half-2 ({b.index.min().date()}..{b.index.max().date()}) mean_ic={b.mean():+.4f}")
        yr = ic.groupby(ic.index.year).mean()
        print("  yearly mean_ic:", {int(k): round(v, 4) for k, v in yr.items()})


if __name__ == "__main__":
    main()
