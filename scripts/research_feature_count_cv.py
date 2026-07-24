#!/usr/bin/env python
"""Does the production panel-LTR need 172 features?

Implements `doc/research/2026-07-24-feature-set-dimensionality-prereg.md`.
Nothing here may diverge from that document without a superseding prereg.

Harness is production, apples-to-apples — only the feature list varies:
  label  fwd_60d_excess          model  XGB rank:pairwise (PANEL_LTR_PARAMS)
  CV     purged walk-forward     embargo 60 trading days
  norm   rebuilt train-only per fold

Primary statistic is the PER-DATE PAIRED ΔIC against the all-172 arm, with a
moving-block bootstrap (block 60) for the overlapping-label dependence.
Absolute IC is NOT evidence in this corpus (§5 of the prereg) — the standing
house finding is a ~+0.04 leakage floor under absolute IC, and the production
anchor sits on it.

Read-only against production: reads the panel parquet and the published
renquant_model_gbdt API; refuses to write anywhere near production paths.

Usage::

    # redundancy diagnostics only (no training, seconds)
    python scripts/research_feature_count_cv.py --diagnose

    # the study
    python scripts/research_feature_count_cv.py --out /path/to/results.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import warnings
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Prereg-frozen constants (§3, §5) ──────────────────────────────────
LABEL = "fwd_60d_excess"
N_ROUNDS = 100
EMBARGO_DAYS = 60
N_SPLITS = 5
ANCHOR_SPLITS = 3
SEEDS = (42, 43, 44)
BLOCK_LEN = 60          # trading days — matches the label horizon
N_BOOT = 10_000
BOOT_SEED = 20260724
DELTA = 0.005           # non-inferiority margin
ANCHOR_IC_EXPECTED = 0.0488
ANCHOR_TOLERANCE = 0.010

# §2 — the three primary tests. Bonferroni over 3 -> alpha 0.0167 two-sided.
PRIMARY_ARMS = ("used_only", "dedup_r70", "nontechnical_only")
ALPHA_PRIMARY = 0.05 / 3
ALPHA_EXPLORATORY = 0.10
# H3 compares the 14 non-technical columns against the 158 technical ones,
# not against all_172. Every other arm is read against all_172.
BASELINE_FOR = {"nontechnical_only": "technical_only"}
DEFAULT_BASELINE = "all_172"

LIVE_ARTIFACT = ("/Users/renhao/git/github/RenQuant/backtesting/renquant_104"
                 "/artifacts/prod/panel-ltr.alpha158_fund.json")

FUND_COLS = [
    "earnings_yield", "book_to_price", "gross_profitability", "roe", "asset_growth",
    "days_since_earnings", "pead_signal", "pead_quintile_rank", "sue_signal",
    "surprise_momentum", "surprise_streak",
    "sentiment_pos_share", "mean_sentiment", "n_articles_log",
]

_FORBIDDEN_OUT = ("artifacts/prod", "artifacts/sim", "strategy_config",
                  "/data/", "walkforward", "panel-ltr")


def refuse_production_output_path(p: Path) -> Path:
    """Hard guard — this is a research script; it may not write near production."""
    s = str(p.resolve())
    for bad in _FORBIDDEN_OUT:
        if bad in s:
            raise SystemExit(
                f"refusing to write research output to {s!r}: contains {bad!r}. "
                "This script is read-only against production (prereg §8)."
            )
    return p


# ── Feature-space diagnostics (§1 of the prereg; label-free) ──────────

def standardize_per_date(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    g = df.groupby("date")[feats]
    z = (df[feats] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def diagnose(df: pd.DataFrame, feats: list[str]) -> dict:
    z = standardize_per_date(df, feats)
    corr = np.nan_to_num(np.corrcoef(z.values, rowvar=False), nan=0.0)
    ev = np.clip(np.linalg.eigvalsh(corr)[::-1], 0, None)
    cum = np.cumsum(ev) / ev.sum()
    pr = float((ev.sum() ** 2) / (ev ** 2).sum())
    p = ev / ev.sum()
    p = p[p > 0]
    windowed = [f for f in feats if re.match(r"^[A-Z]+(5|10|20|30|60)$", f)]
    fam: dict[str, list[str]] = {}
    for f in windowed:
        m = re.match(r"^([A-Z]+?)(\d+)$", f)
        if m:
            fam.setdefault(m.group(1), []).append(f)
    idx = {c: i for i, c in enumerate(feats)}
    within = []
    for cols in fam.values():
        ii = [idx[c] for c in cols]
        sub = corr[np.ix_(ii, ii)]
        within.extend(np.abs(sub[np.triu_indices(len(ii), 1)]).tolist())
    return {
        "n_features": len(feats),
        "pca_components_for": {f"{t:.2f}": int(np.searchsorted(cum, t) + 1)
                               for t in (0.50, 0.80, 0.90, 0.95, 0.99)},
        "participation_ratio_rank": pr,
        "entropy_rank": float(np.exp(-(p * np.log(p)).sum())),
        "redundancy_multiple": len(feats) / pr,
        "n_windowed_features": len(windowed),
        "windowed_share": len(windowed) / len(feats),
        "within_family_median_abs_r": float(np.median(within)) if within else None,
        "_corr": corr,
    }


def split_census(artifact_path: str) -> dict:
    """Decode the live booster and count splits per feature.

    A feature with ZERO splits provably cannot affect that booster's output.
    This is a structural fact, NOT an importance attribution, and so is not
    subject to the correlated-predictor identification critique (prereg §1).
    The gain shares reported alongside ARE attributions and are descriptive
    only.
    """
    import xgboost as xgb

    art = json.loads(Path(artifact_path).read_text())
    booster = xgb.Booster()
    booster.load_model(bytearray(art["booster_raw_json"].encode("utf-8")))
    cols = art["feature_cols"]
    gain = booster.get_score(importance_type="gain")
    weight = booster.get_score(importance_type="weight")
    g = {f: gain.get(f"f{i}", 0.0) for i, f in enumerate(cols)}
    w = {f: weight.get(f"f{i}", 0.0) for i, f in enumerate(cols)}
    total = sum(g[f] * w[f] for f in cols) or 1.0
    used = [f for f in cols if w[f] > 0]
    zero = [f for f in cols if w[f] == 0]
    ranked = sorted(cols, key=lambda f: -(g[f] * w[f]))
    cum = np.cumsum([g[f] * w[f] for f in ranked]) / total
    nontech = [f for f in cols if f in set(FUND_COLS)]
    return {
        "artifact": artifact_path,
        "trained_date": art.get("trained_date"),
        "artifact_oos_mean_ic": art.get("oos_mean_ic"),
        "n_features": len(cols),
        "n_used": len(used), "n_zero_split": len(zero),
        "zero_split_share": len(zero) / len(cols),
        "nontechnical_gain_share": sum(g[f] * w[f] for f in nontech) / total,
        "gain_concentration": {f"{t:.2f}": int(np.searchsorted(cum, t) + 1)
                               for t in (0.50, 0.80, 0.90, 0.95, 0.99)},
        "top15": [(f, round(g[f] * w[f] / total, 4), int(w[f])) for f in ranked[:15]],
        "used": used, "zero": zero,
    }


def greedy_dedup(corr: np.ndarray, feats: list[str], thr: float) -> list[str]:
    """Label-FREE: keep a feature only if |r| to every already-kept one <= thr.
    Seeded most-connected-first so the survivors are the space's spanning set."""
    order = np.argsort(-np.abs(corr).sum(axis=0))
    kept: list[int] = []
    for i in order:
        if all(abs(corr[i, j]) <= thr for j in kept):
            kept.append(int(i))
    return [feats[i] for i in kept]


# ── Inference (§5) ───────────────────────────────────────────────────

def moving_block_bootstrap(x: np.ndarray, block: int, n_boot: int,
                           seed: int, alpha: float) -> tuple[float, float]:
    """Percentile CI on the mean of a serially dependent series."""
    rng = np.random.default_rng(seed)
    n = len(x)
    if n <= block:
        return float("nan"), float("nan")
    starts = np.arange(n - block + 1)
    n_blocks = int(np.ceil(n / block))
    means = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.choice(starts, size=n_blocks, replace=True)
        samp = np.concatenate([x[i:i + block] for i in s])[:n]
        means[b] = samp.mean()
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return lo, hi


def verdict(lo: float, hi: float, delta: float) -> str:
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "UNDEFINED"
    if lo > 0:
        return "SUPERIOR"
    if lo > -delta:
        return "NON-INFERIOR"
    if hi < -delta:
        return "INFERIOR"
    return "INCONCLUSIVE"


# ── The study ────────────────────────────────────────────────────────

def build_folds(dates: np.ndarray, n_splits: int, embargo: int) -> list[dict]:
    out = []
    for i, vi in enumerate(np.array_split(np.arange(len(dates)), n_splits + 1)[1:], 1):
        if len(vi) == 0:
            continue
        end = int(vi[0]) - embargo
        if end <= 0:
            continue
        out.append({"fold": i, "train": set(dates[:end]), "val": set(dates[vi])})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="/Users/renhao/git/github/RenQuant/data")
    ap.add_argument("--out", help="research output JSON path")
    ap.add_argument("--diagnose", action="store_true",
                    help="feature-space redundancy only; no training")
    ap.add_argument("--census", action="store_true",
                    help="split census of the live production booster; no training")
    ap.add_argument("--artifact", default=LIVE_ARTIFACT,
                    help="artifact to census (read-only)")
    ap.add_argument("--n-splits", type=int, default=N_SPLITS)
    ap.add_argument("--skip-anchor", action="store_true",
                    help="DEBUG ONLY — the prereg voids a run whose anchor fails")
    args = ap.parse_args()

    if args.census:
        c = split_census(args.artifact)
        print(f"artifact {c['artifact']}")
        print(f"trained_date {c['trained_date']}  oos_mean_ic {c['artifact_oos_mean_ic']}")
        print(f"ZERO-SPLIT (provably inert): {c['n_zero_split']}/{c['n_features']} "
              f"({c['zero_split_share']:.0%})   used: {c['n_used']}")
        print(f"non-technical gain share (descriptive, not identified): "
              f"{c['nontechnical_gain_share']:.1%} from 14 of {c['n_features']} columns")
        for t, k in c["gain_concentration"].items():
            print(f"  {float(t):.0%} of total gain in top {k} features")
        print("  top 15:")
        for f, share, splits in c["top15"]:
            print(f"    {f:<24} {share:6.2%}  splits={splits}")
        return 0

    from renquant_model_gbdt.panel_data import load_panel, build_normalization
    from renquant_model_gbdt.panel_trainer import (
        PANEL_LTR_PARAMS, panel_training_matrix, train_xgb)
    import xgboost as xgb

    data_dir = Path(args.data_dir)
    train_all, feats, label = load_panel(data_dir, label=LABEL)
    if label != LABEL:
        raise SystemExit(f"label drift: got {label!r}, prereg froze {LABEL!r}")
    print(f"panel {len(train_all):,} rows · {len(feats)} features · label {label}")

    diag = diagnose(train_all, feats)
    corr = diag.pop("_corr")
    print(f"effective rank {diag['participation_ratio_rank']:.1f} "
          f"({diag['redundancy_multiple']:.1f}x redundant) · "
          f"{diag['windowed_share']:.0%} of columns are one operator at another window")
    if args.diagnose:
        print(json.dumps(diag, indent=2))
        return 0
    if not args.out:
        raise SystemExit("--out is required unless --diagnose")
    out_path = refuse_production_output_path(Path(args.out))

    nb = partial(build_normalization, data_dir=data_dir)
    dates = np.array(sorted(pd.to_datetime(train_all["date"].unique())))
    folds = build_folds(dates, args.n_splits, EMBARGO_DAYS)
    print(f"{len(folds)} purged walk-forward folds · embargo {EMBARGO_DAYS}d")

    def fit_predict(tr, va, cols, seed):
        params = dict(PANEL_LTR_PARAMS, seed=seed)
        mu, sd, kind, _, _ = nb(tr, cols)
        booster, _ = train_xgb(tr, cols, label=LABEL, params=params,
                               num_boost_round=N_ROUNDS, feature_means=mu,
                               feature_stds=sd, feature_norm_kind=kind)
        x_va = panel_training_matrix(va, cols, mu, sd, kind)
        return booster, booster.predict(xgb.DMatrix(x_va.values.astype(np.float64)))

    def per_date_ic(pred, va) -> dict[pd.Timestamp, float]:
        y = va[LABEL].clip(-5, 5).values.astype(np.float64)
        frame = pd.DataFrame({"p": pred, "y": y, "d": va["date"].values})
        out = {}
        for d, g in frame.groupby("d"):
            if len(g) >= 5 and g["p"].std() > 0 and g["y"].std() > 0:
                out[d] = float(g["p"].corr(g["y"], method="spearman"))
        return out

    def gain_top(tr, k, seed):
        booster, _ = fit_predict(tr, tr.head(1), feats, seed)
        gain = booster.get_score(importance_type="gain")
        score = {f: gain.get(f"f{i}", 0.0) for i, f in enumerate(feats)}
        return sorted(feats, key=lambda f: -score[f])[:k]

    dedup_sets = {t: greedy_dedup(corr, feats, t) for t in (0.95, 0.90, 0.80, 0.70, 0.60)}
    for t, cols in dedup_sets.items():
        print(f"  dedup |r|<={t:.2f} -> {len(cols)} features")
    windows = {w: [f for f in feats if re.match(rf"^[A-Z]+{w}$", f)]
               for w in ("5", "10", "20", "30", "60")}
    non_windowed = [f for f in feats if not re.match(r"^[A-Z]+(5|10|20|30|60)$", f)]
    fund = [f for f in FUND_COLS if f in feats]

    census = split_census(args.artifact)
    used_only = [f for f in census["used"] if f in feats]
    zero_only = [f for f in census["zero"] if f in feats]
    print(f"  split census: {len(used_only)} used / {len(zero_only)} inert "
          f"(live artifact {census['trained_date']})")
    sec_fund = [f for f in ("earnings_yield", "book_to_price", "gross_profitability",
                            "roe", "asset_growth") if f in feats]
    sentiment = [f for f in ("sentiment_pos_share", "mean_sentiment", "n_articles_log")
                 if f in feats]
    pead_sue = [f for f in ("days_since_earnings", "pead_signal", "pead_quintile_rank",
                            "sue_signal", "surprise_momentum", "surprise_streak")
                if f in feats]

    # arm -> (selector(train_df, seed) -> cols, is_placebo)
    arms: dict[str, tuple] = {"all_172": (lambda tr, s: feats, False)}
    # structural / label-free
    arms["used_only"] = (lambda tr, s: used_only, False)
    arms["zero_split_only"] = (lambda tr, s: zero_only, False)
    arms["technical_only"] = (lambda tr, s: [f for f in feats if f not in fund], False)
    arms["nontechnical_only"] = (lambda tr, s: fund, False)
    arms["sec_fund_only"] = (lambda tr, s: sec_fund, False)
    arms["drop_sentiment"] = (lambda tr, s: [f for f in feats if f not in sentiment], False)
    arms["drop_pead_sue"] = (lambda tr, s: [f for f in feats if f not in pead_sue], False)
    for t, cols in dedup_sets.items():
        arms[f"dedup_r{int(t * 100)}"] = (lambda tr, s, c=cols: c, False)
    for w, cols in windows.items():
        arms[f"win{w}_only"] = (lambda tr, s, c=cols + non_windowed: c, False)
    # label-dependent — attribution-flagged (prereg §1)
    for k in (80, 40, 20, 10, 5):
        arms[f"gain_top{k}"] = (lambda tr, s, k=k: gain_top(tr, k, s), False)
    # controls
    for k in (40, 20, 10):
        for j in range(3):
            pick = list(np.random.default_rng(1000 + j).choice(feats, size=k, replace=False))
            arms[f"random{k}_s{j}"] = (lambda tr, s, p=pick: p, False)
    arms["placebo"] = (lambda tr, s: feats, True)

    results: dict[str, dict] = {}
    for name, (selector, is_placebo) in arms.items():
        t0 = time.time()
        by_seed = {}
        for seed in SEEDS:
            ic_map: dict[pd.Timestamp, float] = {}
            n_cols = []
            for f in folds:
                tr = train_all[train_all["date"].isin(f["train"])]
                va = train_all[train_all["date"].isin(f["val"])]
                if tr["date"].nunique() < 20 or va.empty:
                    continue
                if is_placebo:   # destroy TRAIN signal only; val labels stay real
                    tr = tr.copy()
                    rng = np.random.default_rng(seed)
                    tr[LABEL] = tr.groupby("date")[LABEL].transform(
                        lambda s: rng.permutation(s.values))
                cols = selector(tr, seed)
                n_cols.append(len(cols))
                _, pred = fit_predict(tr, va, cols, seed)
                ic_map.update(per_date_ic(pred, va))
            by_seed[seed] = ic_map
        common = sorted(set.intersection(*(set(m) for m in by_seed.values())))
        mean_ic_by_date = {d: float(np.mean([by_seed[s][d] for s in SEEDS])) for d in common}
        results[name] = {
            "k": int(np.mean(n_cols)),
            "n_dates": len(common),
            "mean_ic": float(np.mean(list(mean_ic_by_date.values()))),
            "per_seed_mean_ic": {str(s): float(np.mean(list(m.values())))
                                 for s, m in by_seed.items()},
            "_by_date": mean_ic_by_date,
            "_by_seed": {s: m for s, m in by_seed.items()},
        }
        print(f"  {name:20} k={results[name]['k']:3d}  "
              f"IC={results[name]['mean_ic']:+.4f}  [{time.time() - t0:.0f}s]")

    anchor = results["all_172"]["mean_ic"]
    if args.n_splits == ANCHOR_SPLITS:
        ok = abs(anchor - ANCHOR_IC_EXPECTED) <= ANCHOR_TOLERANCE
        print(f"\nANCHOR all_172 IC={anchor:+.4f} vs expected {ANCHOR_IC_EXPECTED:+.4f} "
              f"-> {'OK' if ok else 'FAIL'}")
        if not ok and not args.skip_anchor:
            raise SystemExit("anchor did not reproduce — run is VOID per prereg §3. "
                             "No arm may be read.")
    else:
        # ANCHOR_IC_EXPECTED was only validated at ANCHOR_SPLITS folds (prereg
        # §3). Comparing a different --n-splits run against it is an
        # apples-to-oranges check that can spuriously VOID a valid run or
        # spuriously pass an unvalidated one — fail closed instead: no
        # verdict may be read without an override.
        ok = None
        print(f"\nANCHOR all_172 IC={anchor:+.4f} — no validated anchor at "
              f"--n-splits {args.n_splits} (only {ANCHOR_SPLITS}-fold is "
              f"anchor-validated, expected {ANCHOR_IC_EXPECTED:+.4f}).")
        if not args.skip_anchor:
            raise SystemExit(
                f"no anchor validated at --n-splits {args.n_splits} — run is VOID "
                f"per prereg §3 fail-closed default. Re-run with "
                f"--n-splits {ANCHOR_SPLITS} for the validated anchor check, or "
                "pass --skip-anchor to run exploratory-only (not primary-eligible; "
                "prereg §5 restricts primary verdicts to the anchor-validated run).")

    print(f"\n{'arm':20} {'k':>4} {'vs':>16} {'IC':>8} {'dIC':>8} {'lo':>9} {'hi':>9} "
          f"{'seeds':>6}  verdict")
    print("-" * 104)
    for name, r in results.items():
        if name == "all_172":
            continue
        base_name = BASELINE_FOR.get(name, DEFAULT_BASELINE)
        base = results[base_name]
        shared = sorted(set(r["_by_date"]) & set(base["_by_date"]))
        diff = np.array([r["_by_date"][d] - base["_by_date"][d] for d in shared])
        is_primary = name in PRIMARY_ARMS
        alpha = ALPHA_PRIMARY if is_primary else ALPHA_EXPLORATORY
        lo, hi = moving_block_bootstrap(diff, BLOCK_LEN, N_BOOT, BOOT_SEED, alpha)
        signs = set()
        for s in SEEDS:
            ds = [r["_by_seed"][s][d] - base["_by_seed"][s][d]
                  for d in shared if d in r["_by_seed"][s] and d in base["_by_seed"][s]]
            signs.add(np.sign(np.mean(ds)) if ds else 0)
        stable = len(signs) == 1
        v = verdict(lo, hi, DELTA)
        if is_primary and not stable:
            v = "INCONCLUSIVE (seed signs split)"
        tag = "" if is_primary else "  [exploratory]"
        if name.startswith("gain_top"):
            tag += " [attribution-dependent]"
        print(f"{name:20} {r['k']:>4} {base_name:>16} {r['mean_ic']:>+8.4f} "
              f"{diff.mean():>+8.4f} {lo:>+9.4f} {hi:>+9.4f} "
              f"{'yes' if stable else 'NO':>6}  {v}{tag}")
        r["baseline"] = base_name
        r["delta_ic"] = float(diff.mean())
        r["ci_lo"], r["ci_hi"] = lo, hi
        r["alpha"] = alpha
        r["seed_stable"] = bool(stable)
        r["verdict"] = v
        r["primary"] = is_primary

    # §5 pre-committed read: does SELECTION beat RANDOM at matched k?
    print("\nselection-vs-random at matched k (prereg §5 pre-committed read):")
    for k in (40, 20, 10):
        sel = results.get(f"gain_top{k}")
        rnd = [results[f"random{k}_s{j}"] for j in range(3) if f"random{k}_s{j}" in results]
        if sel and rnd:
            r_mean = float(np.mean([x["mean_ic"] for x in rnd]))
            print(f"  k={k:3d}  gain_top {sel['mean_ic']:+.4f}  vs  "
                  f"random(mean of 3) {r_mean:+.4f}  ->  delta {sel['mean_ic'] - r_mean:+.4f}")

    payload = {
        "prereg": "doc/research/2026-07-24-feature-set-dimensionality-prereg.md",
        "label": LABEL, "params": PANEL_LTR_PARAMS, "n_rounds": N_ROUNDS,
        "n_splits": args.n_splits, "embargo_days": EMBARGO_DAYS, "seeds": list(SEEDS),
        "block_len": BLOCK_LEN, "n_boot": N_BOOT, "boot_seed": BOOT_SEED,
        "delta": DELTA, "primary_arms": list(PRIMARY_ARMS),
        "alpha_primary": ALPHA_PRIMARY, "baseline_for": BASELINE_FOR,
        "anchor_ic": anchor, "anchor_ok": ok,
        "anchor_validated_splits": ANCHOR_SPLITS if args.n_splits == ANCHOR_SPLITS else None,
        "diagnostics": diag,
        "split_census": {k: v for k, v in census.items() if k not in ("used", "zero")},
        "dedup_sets": {str(k): v for k, v in dedup_sets.items()},
        "results": {n: {k: v for k, v in r.items() if not k.startswith("_")}
                    for n, r in results.items()},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
