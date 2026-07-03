#!/usr/bin/env python3
"""S-REL audit item V6, STEP 2 — adversarial independent recompute of the Phase -1
intraday-alpha soft NO-GO.

Target verdict (standing, on main via #267):
  `doc/research/2026-06-27-renquant105-phase-minus-1-results.md` — sigma_oc ~= 152.5 bps
  (std) / 114-115 bps (robust); net edge -6.4 bps @ IC 0.03 / -3.4 bps @ IC 0.05 against the
  conservative 11 bps round-trip cost (breakeven sigma_oc = cost/IC ~= 367 / 220 bps)
  => soft NO-GO on intraday open->close DIRECTIONAL alpha.

Mandate (R1 recheck protocol): fresh implementation from the frozen spec — this script shares
NO code with `scripts/research_phase_minus_1_feasibility.py` and reads a DIFFERENT substrate
(the durable local daily bars `/Users/renhao/git/github/RenQuant/data/ohlcv/<T>/1d.parquet`,
not the Alpaca SIP API). Explicit brief: try to OVERTURN.

Checks implemented (the V6 step-2 brief):
  1. sigma_oc — per-date cross-sectional dispersion of close/open - 1, median across dates;
     std + robust (MAD/IQR) + winsorized; window sensitivity (their 2021-06-22..2026-06-27
     window vs full history vs recent sub-windows) + universe variants (all 142 / ex-ETF /
     full-coverage subset).
  2. Breakeven algebra — net = IC * sigma_oc * factor - cost re-derived; the memo's exact
     rows reproduced; breakeven sigma = cost / (IC * factor).
  3. IC premise — breakeven IC = cost / (sigma_oc * factor) over the factor range
     [1.0 pinned .. idealized top-3-of-142 order-statistic ceiling], with the concentration
     factor measured by Monte Carlo (NOT assumed 1.0 — the adversarial angle).
  4. POSITIVE CONTROL — plant a +30 bps mean open->close edge on a marked subset of the REAL
     cross-section; prove this harness detects a positive net edge (and reports none on the
     unplanted null arm). Decision rule frozen below (PC_*).
  5. Sensitivity grid — sigma in {robust, std} x cost {11, 22, 40} x IC {0.01, 0.03, 0.05,
     0.08} x factor {1.0, top-decile, top-3}; the flip boundary quantified.

Read-only everywhere: the umbrella tree is only ever READ (bars + strategy config); no git,
no writes outside this repo checkout. Evidence JSON (input hashes + code sha) written to
`doc/research/evidence/2026-07-03-v6-phase-minus-1-recompute/verification.json`.

Usage:
    v6_phase_minus_1_recompute.py [--json PATH] [--quick]

Pure helpers are import-safe and dependency-free (stdlib only); pandas/pyarrow are imported
lazily ONLY inside the bar loader; numpy lazily ONLY inside the Monte Carlo. Unit tests
(network- and data-free, incl. the committed positive-control fixture):
`tests/test_v6_phase_minus_1_recompute.py`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import statistics
import sys

# ---------------------------------------------------------------------------
# PINNED constants — the frozen numbers of the verdict under audit (do NOT tune)
# ---------------------------------------------------------------------------
UMBRELLA = "/Users/renhao/git/github/RenQuant"
BARS_ROOT = os.path.join(UMBRELLA, "data", "ohlcv")
STRATEGY_CONFIG = os.path.join(UMBRELLA, "backtesting", "renquant_104", "strategy_config.json")
GOLDEN_CONFIG = os.path.join(UMBRELLA, "backtesting", "renquant_104", "strategy_config.golden.json")

THEIR_WINDOW = ("2021-06-22", "2026-06-27")   # the memo's 1258-session window
THEIR_SESSIONS = 1258
THEIR_SIGMA_STD_MEDIAN_BPS = 152.5
THEIR_SIGMA_MAD_MEDIAN_BPS = 114.0
THEIR_SIGMA_IQR_MEDIAN_BPS = 115.1
THEIR_NET_EDGE_ROWS = {0.03: -6.4, 0.05: -3.4}   # memo §6 (factor 1.0, cost 11, sigma 152.5)
THEIR_BREAKEVEN_SIGMA = {0.03: 367.0, 0.05: 220.0}

COST_PRIOR_BPS = 11.0             # memo's conservative round-trip prior (floor)
COST_GRID_BPS = (11.0, 22.0, 40.0)
IC_GRID = (0.01, 0.03, 0.05, 0.08)
EDGE_FACTOR_PINNED = 1.0          # the memo's pinned factor (its identity's lower bound)
TOP_K_LIVE = 3                    # live strategy panel_buy_top_n = 3 (the concentration case)

MAD_TO_STD = 1.4826
IQR_TO_STD = 1.349
WINSOR_ABS_RET = 0.10             # winsorized-sigma variant: clip |r| at 10% (data-error guard)

# Positive-control frozen decision rule (R2: near decision scale, not 10x it)
PC_PLANT_BPS = 30.0               # planted mean open->close edge on the marked subset
PC_MARKED_PER_DATE = 30           # marked names per date (seeded)
PC_SIGNAL_NOISE_STD = 0.35        # noise added to the marker indicator signal
PC_SEED = 20260703
PC_DETECT_T = 3.0                 # planted arm: gross t-stat must be >= this AND net > 0
                                  # null arm: |gross t| < this AND net < 0

ETFS = {"GLD", "SPY", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY"}


# ---------------------------------------------------------------------------
# Pure, dependency-free helpers (unit tested in tests/test_v6_phase_minus_1_recompute.py)
# ---------------------------------------------------------------------------
def valid_oc_return(o, c) -> float | None:
    """close/open - 1 iff both legs are finite and strictly positive, else None."""
    try:
        o = float(o)
        c = float(c)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(o) and math.isfinite(c)) or o <= 0.0 or c <= 0.0:
        return None
    return c / o - 1.0


def _q(sorted_xs: list[float], q: float) -> float:
    """Linear-interpolation quantile on a pre-sorted list (own implementation)."""
    n = len(sorted_xs)
    if n == 1:
        return sorted_xs[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def xs_dispersion_bps(returns: list[float]) -> dict[str, float] | None:
    """One date's cross-sectional dispersion in bps: population std, MAD->std, IQR->std,
    winsorized std, breadth. None if < 2 valid names."""
    rs = [r for r in returns if r is not None and math.isfinite(r)]
    n = len(rs)
    if n < 2:
        return None
    mean = sum(rs) / n
    std = math.sqrt(sum((r - mean) ** 2 for r in rs) / n)      # population (ddof=0)
    srt = sorted(rs)
    med = _q(srt, 0.5)
    mad = _q(sorted(abs(r - med) for r in rs), 0.5)
    iqr = _q(srt, 0.75) - _q(srt, 0.25)
    wrs = [max(-WINSOR_ABS_RET, min(WINSOR_ABS_RET, r)) for r in rs]
    wmean = sum(wrs) / n
    wstd = math.sqrt(sum((r - wmean) ** 2 for r in wrs) / n)
    return {
        "breadth": float(n),
        "std_bps": std * 1e4,
        "mad_std_bps": mad * MAD_TO_STD * 1e4,
        "iqr_std_bps": iqr / IQR_TO_STD * 1e4,
        "winsor_std_bps": wstd * 1e4,
    }


def series_summary(values: list[float]) -> dict[str, float]:
    vs = [v for v in values if v is not None and math.isfinite(v)]
    if not vs:
        return {"n": 0}
    srt = sorted(vs)
    return {
        "n": len(vs),
        "median": _q(srt, 0.5),
        "p25": _q(srt, 0.25),
        "p75": _q(srt, 0.75),
        "mean": sum(vs) / len(vs),
        "min": srt[0],
        "max": srt[-1],
    }


def net_edge_bps(ic: float, sigma_bps: float, factor: float, cost_bps: float) -> float:
    """The memo's edge identity: net = gross - cost, gross = IC * sigma_oc * factor."""
    return ic * sigma_bps * factor - cost_bps


def breakeven_ic(cost_bps: float, sigma_bps: float, factor: float) -> float:
    """IC at which net edge crosses zero: IC* = cost / (sigma * factor)."""
    return cost_bps / (sigma_bps * factor)


def breakeven_sigma_bps(cost_bps: float, ic: float, factor: float) -> float:
    """sigma_oc at which net edge crosses zero: sigma* = cost / (IC * factor)."""
    return cost_bps / (ic * factor)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def top_k_mean(returns: list[float], signal: list[float], k: int) -> float:
    """Mean realized return of the top-k names by signal (the concentrated-pick estimator)."""
    order = sorted(range(len(signal)), key=lambda i: signal[i], reverse=True)[:k]
    return sum(returns[i] for i in order) / len(order)


def positive_control(returns_by_date: dict[str, list[float]],
                     plant_bps: float = PC_PLANT_BPS,
                     marked_per_date: int = PC_MARKED_PER_DATE,
                     noise_std: float = PC_SIGNAL_NOISE_STD,
                     cost_bps: float = COST_PRIOR_BPS,
                     top_k: int = TOP_K_LIVE,
                     seed: int = PC_SEED) -> dict:
    """Plant a +plant_bps mean o->c edge on a seeded marked subset each date; run the SAME
    top-k / IC estimator on the planted arm and on an unplanted null arm.

    Detection rule (frozen): planted arm fires iff net > 0 AND gross t >= PC_DETECT_T;
    null arm must NOT fire (net < 0, |gross t| < PC_DETECT_T).
    """
    rng = random.Random(seed)
    arms = {"null": [], "planted": []}      # per-date top-k mean return (bps)
    ics = {"null": [], "planted": []}
    for date in sorted(returns_by_date):
        base = [r for r in returns_by_date[date] if r is not None and math.isfinite(r)]
        n = len(base)
        if n < max(top_k + 2, marked_per_date + 2):
            continue
        marked = set(rng.sample(range(n), marked_per_date))
        planted = [r + (plant_bps / 1e4 if i in marked else 0.0) for i, r in enumerate(base)]
        sig = [(1.0 if i in marked else 0.0) + rng.gauss(0.0, noise_std) for i in range(n)]
        nullsig = [rng.gauss(0.0, 1.0) for _ in range(n)]
        arms["planted"].append(top_k_mean(planted, sig, top_k) * 1e4)
        arms["null"].append(top_k_mean(base, nullsig, top_k) * 1e4)
        ic_p = pearson(sig, planted)
        ic_n = pearson(nullsig, base)
        if ic_p is not None:
            ics["planted"].append(ic_p)
        if ic_n is not None:
            ics["null"].append(ic_n)

    out: dict = {"plant_bps": plant_bps, "cost_bps": cost_bps, "top_k": top_k,
                 "marked_per_date": marked_per_date, "seed": seed}
    for arm in ("null", "planted"):
        xs = arms[arm]
        n = len(xs)
        mean = sum(xs) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
        se = sd / math.sqrt(n)
        t = mean / se if se > 0 else 0.0
        out[arm] = {
            "n_dates": n,
            "gross_bps": mean,
            "gross_se_bps": se,
            "gross_t": t,
            "net_bps": mean - cost_bps,
            "mean_ic": sum(ics[arm]) / len(ics[arm]),
        }
    out["mde_gross_bps_t3"] = 3.0 * out["null"]["gross_se_bps"]
    out["planted_detected"] = bool(
        out["planted"]["net_bps"] > 0.0 and out["planted"]["gross_t"] >= PC_DETECT_T)
    out["null_clean"] = bool(
        out["null"]["net_bps"] < 0.0 and abs(out["null"]["gross_t"]) < PC_DETECT_T)
    out["pass"] = bool(out["planted_detected"] and out["null_clean"])
    return out


def sensitivity_grid(sigmas: dict[str, float], factors: dict[str, float],
                     costs=COST_GRID_BPS, ics=IC_GRID) -> list[dict]:
    """Full net-edge grid + per-(sigma, factor, cost) flip-boundary IC*."""
    rows = []
    for sname, sigma in sigmas.items():
        for fname, factor in factors.items():
            for cost in costs:
                row = {"sigma": sname, "sigma_bps": sigma, "factor": fname,
                       "factor_value": factor, "cost_bps": cost,
                       "breakeven_ic": breakeven_ic(cost, sigma, factor)}
                for ic in ics:
                    row[f"net_bps_ic_{ic:g}"] = net_edge_bps(ic, sigma, factor, cost)
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Data loading (lazy pandas import; READ-ONLY)
# ---------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_watchlist() -> tuple[list[str], dict]:
    with open(STRATEGY_CONFIG) as f:
        live = json.load(f)
    with open(GOLDEN_CONFIG) as f:
        golden = json.load(f)
    wl = sorted(live["watchlist"])
    meta = {
        "live_config_sha256": sha256_file(STRATEGY_CONFIG),
        "golden_config_sha256": sha256_file(GOLDEN_CONFIG),
        "n_live": len(live["watchlist"]),
        "n_golden": len(golden["watchlist"]),
        "live_equals_golden_set": set(live["watchlist"]) == set(golden["watchlist"]),
    }
    return wl, meta


def load_bars(watchlist: list[str]) -> tuple[dict[str, dict[str, tuple[float, float]]], dict]:
    """Returns {date_iso: {ticker: (open, close)}} plus per-file hash/coverage metadata."""
    import pandas as pd  # lazy: only the loader needs it

    by_date: dict[str, dict[str, tuple[float, float]]] = {}
    files = {}
    missing = []
    coverage = {}
    for t in watchlist:
        path = os.path.join(BARS_ROOT, t, "1d.parquet")
        if not os.path.exists(path):
            missing.append(t)
            continue
        df = pd.read_parquet(path, columns=["open", "close"])
        files[t] = {"path": path, "sha256": sha256_file(path), "rows": int(len(df))}
        idx = df.index
        coverage[t] = {"first": str(idx.min())[:10], "last": str(idx.max())[:10]}
        opens = df["open"].to_list()
        closes = df["close"].to_list()
        for i, ts in enumerate(idx):
            d = str(ts)[:10]
            by_date.setdefault(d, {})[t] = (opens[i], closes[i])
    meta = {"files": files, "missing_tickers": missing, "coverage": coverage}
    return by_date, meta


def window_dispersion(by_date: dict[str, dict[str, tuple[float, float]]],
                      universe: set[str], start: str, end: str) -> dict:
    """Per-date cross-sectional dispersion medians over [start, end] for a universe."""
    per_date = {"std_bps": [], "mad_std_bps": [], "iqr_std_bps": [],
                "winsor_std_bps": [], "breadth": []}
    n_dates = 0
    for d in sorted(by_date):
        if not (start <= d <= end):
            continue
        rets = [valid_oc_return(*oc) for t, oc in by_date[d].items() if t in universe]
        disp = xs_dispersion_bps([r for r in rets if r is not None])
        if disp is None:
            continue
        n_dates += 1
        for k in per_date:
            per_date[k].append(disp[k])
    return {
        "start": start, "end": end, "n_dates": n_dates,
        "std": series_summary(per_date["std_bps"]),
        "mad": series_summary(per_date["mad_std_bps"]),
        "iqr": series_summary(per_date["iqr_std_bps"]),
        "winsor": series_summary(per_date["winsor_std_bps"]),
        "breadth": series_summary(per_date["breadth"]),
    }


def mc_concentration_factors(n_names: int = 142, trials: int = 200_000,
                             seed: int = 4242) -> dict[str, float]:
    """Monte Carlo E[mean of top-k standardized scores] for k=1,3,14 of n_names — the
    idealized (joint-normal, exactly linear tail) concentration ceiling of the edge identity."""
    import numpy as np  # lazy
    rng = np.random.default_rng(seed)
    top1 = top3 = top14 = 0.0
    done = 0
    batch = 20_000
    while done < trials:
        b = min(batch, trials - done)
        z = rng.standard_normal((b, n_names))
        z.sort(axis=1)
        top1 += float(z[:, -1].sum())
        top3 += float(z[:, -3:].mean(axis=1).sum())
        top14 += float(z[:, -14:].mean(axis=1).sum())
        done += b
    return {"top1": top1 / trials, "top3_mean": top3 / trials, "top14_mean": top14 / trials,
            "n_names": n_names, "trials": trials, "seed": seed}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="write evidence JSON to this path")
    ap.add_argument("--quick", action="store_true", help="smaller MC (CI smoke)")
    args = ap.parse_args(argv)

    watchlist, wl_meta = load_watchlist()
    by_date, bars_meta = load_bars(watchlist)
    all_dates = sorted(by_date)

    # --- Check 1: sigma_oc, window sensitivity, universe variants -----------
    uni_all = set(watchlist) - set(bars_meta["missing_tickers"])
    uni_ex_etf = uni_all - ETFS
    w_start, w_end = THEIR_WINDOW
    full_cov = {t for t in uni_all
                if bars_meta["coverage"][t]["first"] <= w_start
                and bars_meta["coverage"][t]["last"] >= w_end}

    windows = {
        "theirs_2021-06-22_2026-06-27": (w_start, w_end, uni_all),
        "full_2016_to_latest": (all_dates[0], all_dates[-1], uni_all),
        "last8y": ("2018-07-03", all_dates[-1], uni_all),
        "last3y": ("2023-07-03", all_dates[-1], uni_all),
        "last1y": ("2025-07-03", all_dates[-1], uni_all),
        "today5y_2021-07-03_latest": ("2021-07-03", all_dates[-1], uni_all),
        "theirs_ex_etf": (w_start, w_end, uni_ex_etf),
        "theirs_full_coverage_names": (w_start, w_end, full_cov),
    }
    dispersion = {name: window_dispersion(by_date, uni, s, e)
                  for name, (s, e, uni) in windows.items()}

    prim = dispersion["theirs_2021-06-22_2026-06-27"]
    sigma_std = prim["std"]["median"]
    sigma_mad = prim["mad"]["median"]

    # --- Check 2: breakeven algebra vs the memo ------------------------------
    algebra = {
        "memo_rows_reproduced": {
            f"IC={ic:g}": {
                "net_bps_at_their_sigma": net_edge_bps(ic, THEIR_SIGMA_STD_MEDIAN_BPS,
                                                       EDGE_FACTOR_PINNED, COST_PRIOR_BPS),
                "their_net_bps": THEIR_NET_EDGE_ROWS[ic],
                "breakeven_sigma_bps": breakeven_sigma_bps(COST_PRIOR_BPS, ic,
                                                           EDGE_FACTOR_PINNED),
                "their_breakeven_sigma_bps": THEIR_BREAKEVEN_SIGMA[ic],
            } for ic in (0.03, 0.05)
        },
        "net_bps_at_my_sigma_factor1_cost11": {
            f"IC={ic:g}": net_edge_bps(ic, sigma_std, EDGE_FACTOR_PINNED, COST_PRIOR_BPS)
            for ic in IC_GRID
        },
    }

    # --- Check 3: IC premise + the concentration-factor adversarial angle ----
    factors_mc = mc_concentration_factors(n_names=len(uni_all),
                                          trials=20_000 if args.quick else 200_000)
    factors = {"pinned_1.0": 1.0,
               "top_decile_ideal": factors_mc["top14_mean"],
               "top3_ideal_ceiling": factors_mc["top3_mean"]}
    ic_premise = {
        sname: {fname: {f"cost_{c:g}": breakeven_ic(c, sigma, f) for c in COST_GRID_BPS}
                for fname, f in factors.items()}
        for sname, sigma in (("std", sigma_std), ("mad_robust", sigma_mad))
    }

    # --- Check 4: positive control on the REAL cross-section -----------------
    window_rets = {d: [valid_oc_return(*oc) for t, oc in by_date[d].items() if t in uni_all]
                   for d in all_dates if w_start <= d <= w_end}
    pc = positive_control(window_rets)

    # --- Check 5: sensitivity grid -------------------------------------------
    grid = sensitivity_grid({"std": sigma_std, "mad_robust": sigma_mad}, factors)
    n_pos = sum(1 for row in grid for ic in IC_GRID if row[f"net_bps_ic_{ic:g}"] > 0)
    n_cells = len(grid) * len(IC_GRID)

    result = {
        "meta": {
            "run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "script_sha256": sha256_file(os.path.abspath(__file__)),
            "watchlist": wl_meta,
            "bars_root": BARS_ROOT,
            "n_bar_files": len(bars_meta["files"]),
            "missing_tickers": bars_meta["missing_tickers"],
            "input_sha256": {t: v["sha256"] for t, v in sorted(bars_meta["files"].items())},
        },
        "their_numbers": {
            "sigma_std_median_bps": THEIR_SIGMA_STD_MEDIAN_BPS,
            "sigma_mad_median_bps": THEIR_SIGMA_MAD_MEDIAN_BPS,
            "sigma_iqr_median_bps": THEIR_SIGMA_IQR_MEDIAN_BPS,
            "n_sessions": THEIR_SESSIONS,
            "net_edge_rows": THEIR_NET_EDGE_ROWS,
            "breakeven_sigma": THEIR_BREAKEVEN_SIGMA,
        },
        "check1_dispersion": dispersion,
        "check2_algebra": algebra,
        "check3_ic_premise": {"factors_mc": factors_mc, "breakeven_ic": ic_premise},
        "check4_positive_control": pc,
        "check5_sensitivity_grid": {"rows": grid, "n_net_positive_cells": n_pos,
                                    "n_cells": n_cells},
    }

    # --- human report ---------------------------------------------------------
    p = prim
    print("V6 STEP 2 — Phase -1 adversarial recompute (durable bars, independent code)")
    print(f"universe: {len(uni_all)} names (missing bars: {bars_meta['missing_tickers'] or 'none'})"
          f"; live==golden set: {wl_meta['live_equals_golden_set']}")
    print(f"\n[1] sigma_oc, their window {w_start}..{w_end}: n_dates={p['n_dates']} "
          f"(theirs {THEIR_SESSIONS})")
    print(f"    std median {p['std']['median']:.1f} bps (theirs {THEIR_SIGMA_STD_MEDIAN_BPS}); "
          f"p25 {p['std']['p25']:.1f} p75 {p['std']['p75']:.1f} mean {p['std']['mean']:.1f}")
    print(f"    MAD median {p['mad']['median']:.1f} (theirs {THEIR_SIGMA_MAD_MEDIAN_BPS}); "
          f"IQR median {p['iqr']['median']:.1f} (theirs {THEIR_SIGMA_IQR_MEDIAN_BPS}); "
          f"winsor {p['winsor']['median']:.1f}")
    for name in windows:
        d = dispersion[name]
        print(f"    {name:36s} n={d['n_dates']:5d} std_med={d['std']['median']:.1f} "
              f"mad_med={d['mad']['median']:.1f} breadth_med={d['breadth']['median']:.0f}")
    print("\n[2] algebra: memo rows reproduce ->",
          {k: round(v["net_bps_at_their_sigma"], 2)
           for k, v in algebra["memo_rows_reproduced"].items()})
    print("    net at MY sigma (factor 1.0, cost 11):",
          {k: round(v, 2) for k, v in algebra["net_bps_at_my_sigma_factor1_cost11"].items()})
    print(f"\n[3] concentration factors (MC, idealized): top1={factors_mc['top1']:.2f} "
          f"top3={factors_mc['top3_mean']:.2f} top_decile={factors_mc['top14_mean']:.2f}")
    print("    breakeven IC at my std sigma:",
          {f: {c: round(ic, 4) for c, ic in v.items()}
           for f, v in ic_premise["std"].items()})
    print(f"\n[4] positive control (+{PC_PLANT_BPS:.0f} bps planted, top-{TOP_K_LIVE}, "
          f"cost {COST_PRIOR_BPS:.0f}):")
    for arm in ("null", "planted"):
        a = pc[arm]
        print(f"    {arm:8s} gross {a['gross_bps']:+7.2f} bps (t={a['gross_t']:+6.2f}) "
              f"net {a['net_bps']:+7.2f} bps  mean IC {a['mean_ic']:+.4f}")
    print(f"    MDE(gross, t=3) ~= {pc['mde_gross_bps_t3']:.1f} bps; "
          f"planted_detected={pc['planted_detected']} null_clean={pc['null_clean']} "
          f"PASS={pc['pass']}")
    print(f"\n[5] sensitivity grid: {n_pos}/{n_cells} net-positive cells "
          f"(sigma x factor x cost x IC)")

    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1, sort_keys=True)
        print(f"\nevidence JSON -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
