#!/usr/bin/env python
"""Horizon x Features x Regime — FACTORIAL, with interaction tests.

Implements `doc/research/2026-07-24-factorial-horizon-features-regime-prereg.md`.
Nothing here may diverge from that document without a superseding prereg.

Why factorial: three preceding studies each varied ONE factor and held the
others at an arbitrary constant. If the factors interact, all three
conclusions are unsound. The PRIMARY hypotheses here are the interactions
(prereg §5 I1/I2/I3); main effects are read only after the corresponding
interaction is resolved.

Response is PLACEBO-CLEAN IC, not raw IC. Each cell carries its own matched
placebo (same horizon/features/regime/folds/seed, training labels shuffled
within date) because the leakage floor differs per horizon: fwd_60d
self-predicts at +0.049, fwd_20d at +0.009, fwd_5d at ~0. Comparing raw IC
across horizons compares floors, not skills — very likely why E35 picked 60d.

Read-only against production; refuses to write near production paths.

Usage::

    python scripts/research_factorial_hfr.py --probe          # sizing only
    python scripts/research_factorial_hfr.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from functools import partial
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Prereg-frozen constants ──────────────────────────────────────────
HORIZONS = ("fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess")
FEATURE_SETS = ("all_172", "dedup_r70", "nontechnical_14", "random_14")
REGIME_MODES = ("pooled", "specialist")

PRIMARY_EVAL = "fwd_20d_excess"     # §5: live book exits winners ~8d, 69% out by 20d
EMBARGO_DAYS = 60                   # §4: held constant across cells to isolate the target
N_SPLITS = 5
ANCHOR_SPLITS = 3
N_ROUNDS = 100
SEEDS = (42, 43, 44)
N_BOOT = 10_000
BOOT_SEED = 20260724
FAMILY_ALPHA = 0.10                 # Holm family-wise over the 7 registered tests
DELTA = 0.005
MIN_SPECIALIST_DATES = 60           # below this a specialist is not estimable
REGISTRABLE_REGIMES = ("BULL_CALM", "BEAR")   # §4, measured — others underpowered
ALL_REGIMES = ("BULL_CALM", "BEAR", "BULL_VOLATILE", "CHOPPY")
ANCHOR_IC_EXPECTED = 0.0488
ANCHOR_TOLERANCE = 0.010

NONTECHNICAL = [
    "earnings_yield", "book_to_price", "gross_profitability", "roe", "asset_growth",
    "days_since_earnings", "pead_signal", "pead_quintile_rank", "sue_signal",
    "surprise_momentum", "surprise_streak",
    "sentiment_pos_share", "mean_sentiment", "n_articles_log",
]

_FORBIDDEN_OUT = ("artifacts/prod", "artifacts/sim", "strategy_config",
                  "/data/", "walkforward", "panel-ltr")


def refuse_production_output_path(p: Path) -> Path:
    s = str(p.resolve())
    for bad in _FORBIDDEN_OUT:
        if bad in s:
            raise SystemExit(f"refusing research output at {s!r}: contains {bad!r}")
    return p


def greedy_dedup(corr: np.ndarray, feats: list[str], thr: float) -> list[str]:
    """Label-FREE de-duplication — never touches the label."""
    order = np.argsort(-np.abs(corr).sum(axis=0))
    kept: list[int] = []
    for i in order:
        if all(abs(corr[i, j]) <= thr for j in kept):
            kept.append(int(i))
    return [feats[i] for i in kept]


def moving_block_bootstrap(x: np.ndarray, block: int, alpha: float,
                           n_boot: int = N_BOOT, seed: int = BOOT_SEED):
    """Percentile CI on the mean of a serially dependent series."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n <= block or n == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    starts = np.arange(n - block + 1)
    n_blocks = int(np.ceil(n / block))
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.choice(starts, size=n_blocks, replace=True)
        means[b] = np.concatenate([x[i:i + block] for i in idx])[:n].mean()
    return (float(np.percentile(means, 100 * alpha / 2)),
            float(np.percentile(means, 100 * (1 - alpha / 2))))


def holm(pvals: dict[str, float], alpha: float) -> dict[str, bool]:
    """Holm-Bonferroni step-down. Returns name -> rejected(bool)."""
    order = sorted(pvals, key=lambda k: pvals[k])
    m = len(order)
    out, still = {}, True
    for i, name in enumerate(order):
        thresh = alpha / (m - i)
        if still and pvals[name] <= thresh:
            out[name] = True
        else:
            still = False
            out[name] = False
    return out


def boot_pvalue(diff: np.ndarray, block: int) -> float:
    """Two-sided bootstrap p for mean(diff) != 0."""
    diff = np.asarray(diff, dtype=float)
    n = len(diff)
    if n <= block or n == 0:
        return float("nan")
    rng = np.random.default_rng(BOOT_SEED)
    starts = np.arange(n - block + 1)
    n_blocks = int(np.ceil(n / block))
    obs = diff.mean()
    centred = diff - obs
    means = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.choice(starts, size=n_blocks, replace=True)
        means[b] = np.concatenate([centred[i:i + block] for i in idx])[:n].mean()
    return float((np.abs(means) >= abs(obs)).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="/Users/renhao/git/github/RenQuant/data")
    ap.add_argument("--regimes", default=None,
                    help="parquet of production regime labels (date, regime)")
    ap.add_argument("--out")
    ap.add_argument("--probe", action="store_true", help="sizing only, no training")
    ap.add_argument("--n-splits", type=int, default=N_SPLITS)
    ap.add_argument("--skip-anchor", action="store_true",
                    help="DEBUG ONLY — exploratory-only, not primary-eligible")
    args = ap.parse_args()

    from renquant_model_gbdt.panel_data import load_panel, build_normalization
    from renquant_model_gbdt.panel_trainer import (
        PANEL_LTR_PARAMS, panel_training_matrix, train_xgb)
    import xgboost as xgb

    dd = Path(args.data_dir)
    panel, feats, _ = load_panel(dd, label="fwd_60d_excess")
    if args.regimes:
        reg = pd.read_parquet(args.regimes)[["date", "regime"]]
        reg["date"] = pd.to_datetime(reg["date"])
        panel = panel.merge(reg, on="date", how="left")
    else:
        raise SystemExit("--regimes is required: production regime labels from the "
                         "5-task chain (Hurst->CUSUM->GMM->BEAROverride->Finalize). "
                         "A vol/trend proxy is NOT the production labeller.")
    print(f"panel {len(panel):,} rows · {len(feats)} feats · "
          f"regime coverage {panel['regime'].notna().mean():.1%}")

    nb = partial(build_normalization, data_dir=dd)
    dates = np.array(sorted(pd.to_datetime(panel["date"].unique())))
    folds = []
    for vi in np.array_split(np.arange(len(dates)), args.n_splits + 1)[1:]:
        end = int(vi[0]) - EMBARGO_DAYS
        if end > 0 and len(vi):
            folds.append({"train": set(dates[:end]), "val": set(dates[vi])})

    # ── Feature-set levels (all structural / label-free) ─────────────
    g = panel.groupby("date")[feats]
    z = ((panel[feats] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
         ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    corr = np.nan_to_num(np.corrcoef(z.values, rowvar=False), nan=0.0)
    nontech = [f for f in NONTECHNICAL if f in feats]
    LEVELS = {
        "all_172": feats,
        "dedup_r70": greedy_dedup(corr, feats, 0.70),
        "nontechnical_14": nontech,
        # size-matched control for nontechnical_14 (prereg §2): if these tie,
        # the finding is about model CAPACITY, not feature quality (per D3).
        "random_14": list(np.random.default_rng(20260724).choice(
            feats, size=len(nontech), replace=False)),
    }
    for k, v in LEVELS.items():
        print(f"  F={k:18} k={len(v)}")

    if args.probe:
        print(f"\ncells={len(HORIZONS)*len(FEATURE_SETS)*len(REGIME_MODES)} "
              f"x2(placebo) x{len(folds)} folds x{len(SEEDS)} seeds")
        for r in ALL_REGIMES:
            est = sum(1 for f in folds
                      if panel[panel["date"].isin(f["train"]) &
                               (panel["regime"] == r)]["date"].nunique()
                      >= MIN_SPECIALIST_DATES)
            vd = sum(panel[panel["date"].isin(f["val"]) &
                           (panel["regime"] == r)]["date"].nunique() for f in folds)
            tag = "" if r in REGISTRABLE_REGIMES else "  NOT REGISTRABLE (prereg §4)"
            print(f"  {r:15} estimable {est}/{len(folds)} folds · "
                  f"{vd:5} val dates · ~{vd // 60} blocks{tag}")
        return 0
    if not args.out:
        raise SystemExit("--out is required unless --probe")
    out_path = refuse_production_output_path(Path(args.out))

    def fit_one(tr, cols, label, seed):
        mu, sd, kind, _, _ = nb(tr, cols)
        booster, _ = train_xgb(tr, cols, label=label,
                               params=dict(PANEL_LTR_PARAMS, seed=seed),
                               num_boost_round=N_ROUNDS, feature_means=mu,
                               feature_stds=sd, feature_norm_kind=kind)
        return booster, mu, sd, kind

    def run_cell(h, f, r_mode, placebo, seed):
        """One (H,F,R) cell at one seed -> {eval_horizon: {date: ic}}."""
        cols = LEVELS[f]
        acc = {ev: {} for ev in HORIZONS}
        fallbacks = 0
        for fold in folds:
            tr_all = panel[panel["date"].isin(fold["train"])].dropna(subset=[h])
            va = panel[panel["date"].isin(fold["val"])]
            if tr_all["date"].nunique() < 20 or va.empty:
                continue
            if placebo:
                tr_all = tr_all.copy()
                rng = np.random.default_rng(seed)
                tr_all[h] = tr_all.groupby("date")[h].transform(
                    lambda s: rng.permutation(s.values))
            models = {}
            if r_mode == "specialist":
                for rg in ALL_REGIMES:
                    sub = tr_all[tr_all["regime"] == rg]
                    if sub["date"].nunique() >= MIN_SPECIALIST_DATES:
                        models[rg] = fit_one(sub, cols, h, seed)
            glob = fit_one(tr_all, cols, h, seed)
            for rg, va_r in ([(None, va)] if r_mode == "pooled"
                             else list(va.groupby("regime"))):
                m = models.get(rg, glob)
                if r_mode == "specialist" and rg not in models:
                    fallbacks += 1
                booster, mu, sd, kind = m
                pred = booster.predict(xgb.DMatrix(
                    panel_training_matrix(va_r, cols, mu, sd, kind
                                          ).values.astype(np.float64)))
                for ev in HORIZONS:
                    s = va_r[[ev, "date", "regime"]].copy()
                    s["p"] = pred
                    s = s.dropna(subset=[ev, "p"])
                    for d, gg in s.groupby("date"):
                        if len(gg) >= 5 and gg["p"].std() > 0 and gg[ev].std() > 0:
                            acc[ev][d] = (float(gg["p"].corr(gg[ev], method="spearman")),
                                          str(gg["regime"].iloc[0]))
        return acc, fallbacks

    cells, t_start = {}, time.time()
    combos = list(product(HORIZONS, FEATURE_SETS, REGIME_MODES))
    for n, (h, f, r_mode) in enumerate(combos, 1):
        key = f"{h}|{f}|{r_mode}"
        t0 = time.time()
        real, fb = {ev: {} for ev in HORIZONS}, 0
        plac = {ev: {} for ev in HORIZONS}
        for seed in SEEDS:
            a, k = run_cell(h, f, r_mode, False, seed)
            fb += k
            for ev in HORIZONS:
                for d, (v, rg) in a[ev].items():
                    real[ev].setdefault(d, [rg, []])[1].append(v)
            b, _ = run_cell(h, f, r_mode, True, seed)
            for ev in HORIZONS:
                for d, (v, rg) in b[ev].items():
                    plac[ev].setdefault(d, [rg, []])[1].append(v)
        clean = {}
        for ev in HORIZONS:
            clean[ev] = {d: (rg, float(np.mean(vs)) -
                             float(np.mean(plac[ev][d][1])) if d in plac[ev] else np.nan)
                         for d, (rg, vs) in real[ev].items()}
        cells[key] = {"clean": clean, "fallbacks": fb,
                      "raw_primary": float(np.mean(
                          [np.mean(v[1]) for v in real[PRIMARY_EVAL].values()])),
                      "placebo_primary": float(np.mean(
                          [np.mean(v[1]) for v in plac[PRIMARY_EVAL].values()]))}
        cp = [v for _, v in cells[key]["clean"][PRIMARY_EVAL].values()]
        print(f"[{n:2d}/{len(combos)}] {key:46} clean@{PRIMARY_EVAL.split('_')[1]}="
              f"{np.nanmean(cp):+.4f}  raw={cells[key]['raw_primary']:+.4f}  "
              f"placebo={cells[key]['placebo_primary']:+.4f}  "
              f"fb={fb}  [{time.time()-t0:.0f}s]", flush=True)

    # ── Anchor (prereg §5) — fail closed off the validated fold count ──
    anchor_key = "fwd_60d_excess|all_172|pooled"
    anchor = cells[anchor_key]["raw_primary"]
    if args.n_splits == ANCHOR_SPLITS:
        ok = abs(anchor - ANCHOR_IC_EXPECTED) <= ANCHOR_TOLERANCE
        print(f"\nANCHOR {anchor:+.4f} vs {ANCHOR_IC_EXPECTED:+.4f} -> "
              f"{'OK' if ok else 'FAIL'}")
        if not ok and not args.skip_anchor:
            raise SystemExit("anchor did not reproduce — run VOID (prereg §5)")
    elif not args.skip_anchor:
        raise SystemExit(
            f"no validated anchor at --n-splits {args.n_splits} (only "
            f"{ANCHOR_SPLITS} is anchor-validated) — run VOID per the "
            "fail-closed default. Pass --skip-anchor for exploratory-only.")

    json.dump({"prereg": "doc/research/2026-07-24-factorial-horizon-features-regime-prereg.md",
               "primary_eval": PRIMARY_EVAL, "embargo": EMBARGO_DAYS,
               "n_splits": args.n_splits, "seeds": list(SEEDS),
               "registrable_regimes": list(REGISTRABLE_REGIMES),
               "feature_levels": {k: len(v) for k, v in LEVELS.items()},
               "anchor_raw_ic": anchor,
               "cells": {k: {"raw_primary": v["raw_primary"],
                             "placebo_primary": v["placebo_primary"],
                             "fallbacks": v["fallbacks"],
                             "clean": {ev: {str(d): [rg, val]
                                            for d, (rg, val) in c.items()}
                                       for ev, c in v["clean"].items()}}
                         for k, v in cells.items()}},
              open(out_path, "w"), indent=2, default=str)
    print(f"\nwrote {out_path}  [{(time.time()-t_start)/60:.0f} min]")
    print("Interaction tests (I1/I2/I3) and Holm correction run in the "
          "results PR against this artifact — the prereg forbids reading "
          "verdicts in the same PR that freezes the design.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
