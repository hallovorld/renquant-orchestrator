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


def _eval_block(ev: str) -> int:
    """Bootstrap block = the evaluation label's own horizon (prereg §5) —
    not a constant 60; a 5d label's dependence range is 5 days."""
    return {"fwd_5d_excess": 5, "fwd_20d_excess": 20, "fwd_60d_excess": 60}[ev]


def _cell_series(cells: dict, key: str, ev: str, regime: str | None = None) -> dict:
    """{date: clean_ic} for one cell/eval-horizon, optionally filtered to one
    realized-regime stratum. Drops NaN dates (no placebo match / std==0)."""
    out = {}
    for d, (rg, v) in cells[key]["clean"][ev].items():
        if regime is not None and rg != regime:
            continue
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        out[d] = v
    return out


def _cell_series_by_seed(cells: dict, key: str, ev: str,
                         regime: str | None = None) -> dict:
    """{seed: {date: clean_ic}} — per-seed granularity for the seed-stability
    check (prereg §5: any registered verdict needs sign agreement across all
    3 seeds, which the seed-averaged `clean` series alone cannot answer)."""
    out = {}
    for seed, by_date in cells[key]["clean_by_seed"][ev].items():
        s = {}
        for d, (rg, v) in by_date.items():
            if regime is not None and rg != regime:
                continue
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            s[d] = v
        out[seed] = s
    return out


def _diff_series(cells: dict, key_a: str, key_b: str, ev: str,
                 regime: str | None = None) -> np.ndarray:
    """clean_IC(key_a) - clean_IC(key_b), paired by the date common to both."""
    a = _cell_series(cells, key_a, ev, regime)
    b = _cell_series(cells, key_b, ev, regime)
    common = sorted(set(a) & set(b))
    return np.array([a[d] - b[d] for d in common])


def _double_diff_series(cells: dict, key_hi_a: str, key_lo_a: str,
                        key_hi_b: str, key_lo_b: str, ev: str) -> np.ndarray:
    """[clean(hi_a)-clean(lo_a)] - [clean(hi_b)-clean(lo_b)], paired by the
    date common to all four cells. Valid for I2/I3: all four cells there
    share ONE unstratified date universe (only F/R or F/H vary, not the
    regime stratum), unlike I1 (see `_two_group_diff_of_means`)."""
    a1, a2 = _cell_series(cells, key_hi_a, ev), _cell_series(cells, key_lo_a, ev)
    b1, b2 = _cell_series(cells, key_hi_b, ev), _cell_series(cells, key_lo_b, ev)
    common = sorted(set(a1) & set(a2) & set(b1) & set(b2))
    return np.array([(a1[d] - a2[d]) - (b1[d] - b2[d]) for d in common])


def _two_group_diff_of_means(cells: dict, key_hi: str, key_lo: str, ev: str,
                             group_a: str, group_b: str):
    """Per-regime-stratum paired diff (key_hi - key_lo), one series per
    group. I1's two regime strata (BEAR / BULL_CALM) are DISJOINT date sets,
    so this is a two-independent-groups comparison, not one paired series."""
    da = _diff_series(cells, key_hi, key_lo, ev, group_a)
    db = _diff_series(cells, key_hi, key_lo, ev, group_b)
    return da, db


def _boot_pvalue_two_sample(da: np.ndarray, db: np.ndarray, block: int) -> float:
    """Two-sided moving-block-bootstrap p for mean(da) - mean(db) != 0. Each
    side is resampled with its own block scheme and the two are combined by
    subtraction across bootstrap draws — valid because I1's two regime-date
    universes are disjoint (§4), not because they are assumed independent
    in the stronger statistical sense; this is the standard two-sample
    block-bootstrap difference-in-means construction."""
    da, db = np.asarray(da, dtype=float), np.asarray(db, dtype=float)
    if len(da) <= block or len(db) <= block or len(da) == 0 or len(db) == 0:
        return float("nan")
    obs = da.mean() - db.mean()

    def _boot_means(x: np.ndarray, seed_offset: int) -> np.ndarray:
        n = len(x)
        rng = np.random.default_rng(BOOT_SEED + seed_offset)
        starts = np.arange(n - block + 1)
        n_blocks = int(np.ceil(n / block))
        means = np.empty(N_BOOT)
        for b in range(N_BOOT):
            idx = rng.choice(starts, size=n_blocks, replace=True)
            means[b] = np.concatenate([x[i:i + block] for i in idx])[:n].mean()
        return means

    boot_diff = _boot_means(da, 0) - _boot_means(db, 1)
    centred = boot_diff - boot_diff.mean()
    return float((np.abs(centred) >= abs(obs)).mean())


def _seed_stable_paired(cells: dict, key_a: str, key_b: str, ev: str,
                        regime: str | None = None) -> bool:
    means = []
    for seed in SEEDS:
        sa = _cell_series_by_seed(cells, key_a, ev, regime).get(seed, {})
        sb = _cell_series_by_seed(cells, key_b, ev, regime).get(seed, {})
        common = sorted(set(sa) & set(sb))
        if not common:
            return False
        means.append(float(np.mean([sa[d] - sb[d] for d in common])))
    signs = {np.sign(m) for m in means}
    return len(signs) == 1 and 0.0 not in signs


def _seed_stable_double(cells: dict, key_hi_a: str, key_lo_a: str,
                        key_hi_b: str, key_lo_b: str, ev: str) -> bool:
    means = []
    for seed in SEEDS:
        a1 = _cell_series_by_seed(cells, key_hi_a, ev).get(seed, {})
        a2 = _cell_series_by_seed(cells, key_lo_a, ev).get(seed, {})
        b1 = _cell_series_by_seed(cells, key_hi_b, ev).get(seed, {})
        b2 = _cell_series_by_seed(cells, key_lo_b, ev).get(seed, {})
        common = sorted(set(a1) & set(a2) & set(b1) & set(b2))
        if not common:
            return False
        means.append(float(np.mean([(a1[d] - a2[d]) - (b1[d] - b2[d])
                                    for d in common])))
    signs = {np.sign(m) for m in means}
    return len(signs) == 1 and 0.0 not in signs


def run_interaction_tests(cells: dict) -> dict:
    """Prereg §5 FROZEN decision rule: I1/I2/I3 (PRIMARY) + M1/M2a/M2b/M3
    (SECONDARY — read only if the corresponding interaction is null), Holm-
    Bonferroni family-wise alpha=0.10 over all 7 registered tests. A
    registered verdict additionally requires seed-sign-agreement across all
    3 seeds (§5); split signs => INCONCLUSIVE regardless of the interval.

    Estimand note (resolves a round-1 review comment that the prereg text
    never explicitly settled): §2 defines R as the training design factor
    (pooled/specialist), which is what I2/I3 use. I1's own contrast notation
    — `clean_IC(60d, BEAR)` / `clean_IC(60d, BULL_CALM)` — takes no r_mode
    argument at all, so it cannot be evaluated under that reading; the only
    consistent reading is R-as-realized-regime-stratum of the POOLED model's
    validation dates. This also matches §4's precommit that only BULL_CALM
    and BEAR are registrable at all — exactly the two strata I1 contrasts.
    Frozen here, before any run (no results exist yet to have been peeked
    at); open to reviewer override before the results PR executes it.
    """
    ev = PRIMARY_EVAL  # fwd_20d_excess — both "primary training horizon" and eval horizon
    h_hi, h_lo = "fwd_60d_excess", "fwd_20d_excess"

    def key(h: str, f: str, r: str) -> str:
        return f"{h}|{f}|{r}"

    block = _eval_block(ev)
    tests: dict = {}

    # I1 (H x R-as-regime-stratum), pooled / all_172 — two disjoint regime groups.
    da, db = _two_group_diff_of_means(
        cells, key(h_hi, "all_172", "pooled"), key(h_lo, "all_172", "pooled"),
        ev, "BEAR", "BULL_CALM")
    tests["I1_H_x_R"] = {
        "stat": float(da.mean() - db.mean()) if len(da) and len(db) else float("nan"),
        "p": _boot_pvalue_two_sample(da, db, block),
        "seed_stable": (
            _seed_stable_paired(cells, key(h_hi, "all_172", "pooled"),
                               key(h_lo, "all_172", "pooled"), ev, "BEAR")
            and _seed_stable_paired(cells, key(h_hi, "all_172", "pooled"),
                                    key(h_lo, "all_172", "pooled"), ev, "BULL_CALM")),
    }

    # I2 (F x R=r_mode), at H=primary — single paired-by-date series.
    d = _double_diff_series(
        cells, key(h_lo, "dedup_r70", "specialist"), key(h_lo, "all_172", "specialist"),
        key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev)
    tests["I2_F_x_R"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_double(
            cells, key(h_lo, "dedup_r70", "specialist"), key(h_lo, "all_172", "specialist"),
            key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev),
    }

    # I3 (H x F), R=pooled — single paired-by-date series.
    d = _double_diff_series(
        cells, key(h_hi, "dedup_r70", "pooled"), key(h_hi, "all_172", "pooled"),
        key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev)
    tests["I3_H_x_F"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_double(
            cells, key(h_hi, "dedup_r70", "pooled"), key(h_hi, "all_172", "pooled"),
            key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev),
    }

    # M1 (H): pooled / all_172, unstratified.
    d = _diff_series(cells, key(h_hi, "all_172", "pooled"), key(h_lo, "all_172", "pooled"), ev)
    tests["M1_H"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_paired(
            cells, key(h_hi, "all_172", "pooled"), key(h_lo, "all_172", "pooled"), ev),
    }

    # M2a (dedup_r70 vs all_172): pooled, H=primary.
    d = _diff_series(cells, key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev)
    tests["M2a_F_dedup_vs_all"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_paired(
            cells, key(h_lo, "dedup_r70", "pooled"), key(h_lo, "all_172", "pooled"), ev),
    }

    # M2b (nontechnical_14 vs random_14): pooled, H=primary.
    d = _diff_series(cells, key(h_lo, "nontechnical_14", "pooled"),
                     key(h_lo, "random_14", "pooled"), ev)
    tests["M2b_F_nontechnical_vs_random"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_paired(
            cells, key(h_lo, "nontechnical_14", "pooled"),
            key(h_lo, "random_14", "pooled"), ev),
    }

    # M3 (R): specialist vs pooled, all_172, H=primary.
    d = _diff_series(cells, key(h_lo, "all_172", "specialist"),
                     key(h_lo, "all_172", "pooled"), ev)
    tests["M3_R"] = {
        "stat": float(d.mean()) if len(d) else float("nan"),
        "p": boot_pvalue(d, block),
        "seed_stable": _seed_stable_paired(
            cells, key(h_lo, "all_172", "specialist"), key(h_lo, "all_172", "pooled"), ev),
    }

    rejected = holm({k: v["p"] for k, v in tests.items()}, FAMILY_ALPHA)
    for k in tests:
        tests[k]["holm_rejected"] = rejected[k]
        tests[k]["registered_verdict"] = bool(rejected[k] and tests[k]["seed_stable"])
    return tests


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

    # Fail closed on an unvalidated fold count BEFORE training, not after —
    # otherwise the full ~87-minute sweep runs only to VOID at the end.
    if args.n_splits != ANCHOR_SPLITS and not args.skip_anchor:
        raise SystemExit(
            f"no validated anchor at --n-splits {args.n_splits} (only "
            f"{ANCHOR_SPLITS} is anchor-validated) — run VOID per the "
            "fail-closed default. Pass --skip-anchor for exploratory-only.")

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
        clean_by_seed = {ev: {} for ev in HORIZONS}
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
                # per-seed clean IC, kept separate from the seed-averaged
                # `clean` below — needed for the seed-stability check
                # (prereg §5), which the averaged series alone can't answer.
                clean_by_seed[ev][seed] = {
                    d: (rg, a[ev][d][0] - b[ev][d][0])
                    for d, (_, rg) in a[ev].items() if d in b[ev]
                }
        clean = {}
        for ev in HORIZONS:
            clean[ev] = {d: (rg, float(np.mean(vs)) -
                             float(np.mean(plac[ev][d][1])) if d in plac[ev] else np.nan)
                         for d, (rg, vs) in real[ev].items()}
        cells[key] = {"clean": clean, "clean_by_seed": clean_by_seed, "fallbacks": fb,
                      "raw_primary": float(np.mean(
                          [np.mean(v[1]) for v in real[PRIMARY_EVAL].values()])),
                      "placebo_primary": float(np.mean(
                          [np.mean(v[1]) for v in plac[PRIMARY_EVAL].values()]))}
        cp = [v for _, v in cells[key]["clean"][PRIMARY_EVAL].values()]
        print(f"[{n:2d}/{len(combos)}] {key:46} clean@{PRIMARY_EVAL.split('_')[1]}="
              f"{np.nanmean(cp):+.4f}  raw={cells[key]['raw_primary']:+.4f}  "
              f"placebo={cells[key]['placebo_primary']:+.4f}  "
              f"fb={fb}  [{time.time()-t0:.0f}s]", flush=True)

    # ── Anchor (prereg §5) — reproduction check; fold-count gate already
    # enforced above, before training started ──
    anchor_key = "fwd_60d_excess|all_172|pooled"
    anchor = cells[anchor_key]["raw_primary"]
    anchor_validated = args.n_splits == ANCHOR_SPLITS
    analysis_eligible, ineligible_reason = False, None
    if anchor_validated:
        ok = abs(anchor - ANCHOR_IC_EXPECTED) <= ANCHOR_TOLERANCE
        print(f"\nANCHOR {anchor:+.4f} vs {ANCHOR_IC_EXPECTED:+.4f} -> "
              f"{'OK' if ok else 'FAIL'}")
        if not ok and not args.skip_anchor:
            raise SystemExit("anchor did not reproduce — run VOID (prereg §5)")
        analysis_eligible = ok
        if not ok:
            ineligible_reason = (f"anchor FAILED ({anchor:+.4f} vs "
                                 f"{ANCHOR_IC_EXPECTED:+.4f} ± {ANCHOR_TOLERANCE}) "
                                 "under --skip-anchor")
    else:
        ineligible_reason = (f"--n-splits {args.n_splits} has no validated anchor "
                             f"(only {ANCHOR_SPLITS} is anchor-validated) — exploratory-only")
        print(f"\n{ineligible_reason}")

    # Interaction/Holm verdicts (prereg §5) — computed unconditionally so the
    # bundle always carries them, but `registered_verdict` is forced False
    # whenever `analysis_eligible` is False so an unvalidated / skip-anchor
    # run can never be read as a primary verdict downstream.
    interaction = run_interaction_tests(cells)
    if not analysis_eligible:
        for t in interaction.values():
            t["registered_verdict"] = False
    print()
    for name, t in interaction.items():
        print(f"  {name:28} stat={t['stat']:+.4f} p={t['p']:.4f} "
              f"seed_stable={t['seed_stable']} holm_reject={t['holm_rejected']} "
              f"registered={t['registered_verdict']}")

    json.dump({"prereg": "doc/research/2026-07-24-factorial-horizon-features-regime-prereg.md",
               "primary_eval": PRIMARY_EVAL, "embargo": EMBARGO_DAYS,
               "n_splits": args.n_splits, "seeds": list(SEEDS),
               "registrable_regimes": list(REGISTRABLE_REGIMES),
               "feature_levels": {k: len(v) for k, v in LEVELS.items()},
               "anchor_raw_ic": anchor,
               "anchor_validated": anchor_validated,
               "analysis_eligible": analysis_eligible,
               "ineligible_reason": ineligible_reason,
               "interaction_tests": interaction,
               "cells": {k: {"raw_primary": v["raw_primary"],
                             "placebo_primary": v["placebo_primary"],
                             "fallbacks": v["fallbacks"],
                             "clean": {ev: {str(d): [rg, val]
                                            for d, (rg, val) in c.items()}
                                       for ev, c in v["clean"].items()}}
                         for k, v in cells.items()}},
              open(out_path, "w"), indent=2, default=str)
    print(f"\nwrote {out_path}  [{(time.time()-t_start)/60:.0f} min]")
    print("Interaction/Holm verdicts are computed by THIS script (frozen "
          "analyzer, prereg §5) and written into the bundle above. The "
          "results PR only EXECUTES this analyzer against a fresh run; it "
          "may not redefine the estimator, the Holm family, or the block.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
