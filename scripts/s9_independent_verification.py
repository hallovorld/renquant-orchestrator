#!/usr/bin/env python3
"""S9 VERIFICATION — independent adversarial re-computation of the Track A NULL.

Verifies (or overturns) the S9 verdict of PR #262
(``doc/research/2026-07-03-s9-track-a-conditional.md``) by recomputing every
load-bearing number from the same primary inputs with INDEPENDENT code:

- own join (duplicate-validated ``m:1`` merge, explicit NaN accounting) —
  never trusts the S9 script's join;
- own conditioning rules (C3 recomputed directly from within-date score
  ranks, not via the S9 margin construction; C2 whitelist re-learned);
- own logistic regression (numpy IRLS with sklearn-equivalent L2, not
  sklearn) for C1;
- own date-block bootstrap (same block-13 convention — required for
  comparability — but a different seed and 4,000 resamples);
- label-semantics check the S9 script never did: proves
  ``fwd_60d_excess_raw`` is a 60-TRADING-SESSION forward return in RETURN
  units against a common per-date benchmark, by reconstructing per-name
  60-session forward returns from the durable bars panel and checking the
  residual is a per-date constant (= minus the benchmark return);
- embargo-leak check on the panel's own trading-day grid (does the last
  train label window touch the first test date?);
- fragility variants an adversary would try to flip the verdict with:
  floor split (train=304), strict ``>`` median for C3, and the LITERAL
  standardized-units label for C3's binding gate (e).

Everything is read strictly read-only. No git operation is performed.

Reproduce:

    python3 scripts/s9_independent_verification.py \
        --umbrella /Users/renhao/git/github/RenQuant \
        --out-dir doc/research/evidence/2026-07-03-s9-verification
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Frozen §4 constants (same as S9 — these ARE the spec, not S9's choices)
COST_RT = 0.0011
TRAIN_FRAC = 0.60
EMBARGO_DAYS = 60
BLOCK = 13
PERIODS_PER_YEAR = 252.0 / 60.0
TOP_DECILE = 9
GATES = {
    "a_book_lift_ann_min": 0.0050,
    "b_per_pick_lift_min": 0.0005,
    "c_hit_rate_lift_min": 0.03,
    "d_active_frac_min": 0.25,
    "e_max_winner_drop": 1.0 / 3.0,
    "e_max_turnover_multiple": 2.0,
}

# Verification-own knobs (deliberately different from S9's 2000/20260703)
N_BOOT = 4000
SEED = 71                     # independent RNG path
VOL_ADV_WINDOW = 60


# ---------------------------------------------------------------------------
# Check 1 — units + join (recomputed from scratch)
# ---------------------------------------------------------------------------
def check_units_and_join(pick_table: Path, rawlabel: Path) -> tuple[pd.DataFrame, dict]:
    table = pd.read_parquet(pick_table)
    out: dict = {
        "n_rows": int(len(table)),
        "n_dates": int(table["date"].nunique()),
        "n_names": int(table["name"].nunique()),
    }
    # regime must be a per-date label (C2/(d) depends on this)
    out["regime_constant_within_date"] = bool(
        (table.groupby("date")["regime"].nunique() == 1).all()
    )
    # decile orientation: 9 must be the BEST scores
    mean_by_decile = table.groupby("decile_rank")["score"].mean()
    out["decile9_is_top"] = bool(mean_by_decile.idxmax() == TOP_DECILE)
    # standardized-label claim
    g = table.groupby("date")["fwd_60d_excess"]
    out["table_label_per_date_mean_absmax"] = float(g.mean().abs().max())
    out["table_label_per_date_std_dev_from_1_absmax"] = float((g.std() - 1.0).abs().max())

    top = table[table["decile_rank"] == TOP_DECILE].copy()
    out["n_top_decile_rows"] = int(len(top))

    lab = pd.read_parquet(
        rawlabel, columns=["ticker", "date", "fwd_60d_excess", "fwd_60d_excess_raw"]
    ).rename(columns={"ticker": "name"})
    out["panel_duplicate_date_name_keys"] = int(lab.duplicated(["date", "name"]).sum())
    out["panel_nan_raw_label_rows"] = int(lab["fwd_60d_excess_raw"].isna().sum())
    n_before = len(top)
    top = top.merge(
        lab.rename(columns={"fwd_60d_excess": "z_panel", "fwd_60d_excess_raw": "ret_raw"}),
        on=["date", "name"],
        how="left",
        validate="m:1",  # hard-fails on duplicate panel keys (silent row inflation)
    )
    out["merge_row_count_stable"] = bool(len(top) == n_before)
    out["picks_missing_raw_label"] = int(top["ret_raw"].isna().sum())
    out["picks_nan_z_panel"] = int(top["z_panel"].isna().sum())
    out["max_abs_diff_table_z_vs_panel_z"] = float((top["fwd_60d_excess"] - top["z_panel"]).abs().max())
    # scale sanity: raw label must look like a 60d return (not standardized, not %)
    out["raw_label_std"] = float(top["ret_raw"].std())
    out["raw_label_abs_median"] = float(top["ret_raw"].abs().median())
    top["y"] = (top["ret_raw"] > COST_RT).astype(int)
    top["y_literal_z"] = (top["fwd_60d_excess"] > COST_RT).astype(int)  # fragility variant
    return top, out


def check_label_semantics(top: pd.DataFrame, ohlcv_dir: Path, panel_dates: pd.DatetimeIndex,
                          n_probe_dates: int = 6, n_names: int = 12,
                          rng: np.random.Generator | None = None) -> dict:
    """Prove fwd_60d_excess_raw = 60-TRADING-SESSION forward return minus a
    per-date common benchmark return, by reconstructing per-name forward
    returns from the bars panel. If the residual (label - own_fwd_return) is
    a per-date constant across names, the label is exactly that construction."""
    rng = rng or np.random.default_rng(SEED)
    dates = sorted(top["date"].unique())
    probe_dates = [dates[i] for i in sorted(rng.choice(len(dates) - 1, size=n_probe_dates, replace=False))]
    rows = []
    for d in probe_dates:
        picks = top[top["date"] == d]
        names = list(picks["name"].unique())[:n_names]
        for name in names:
            bars = pd.read_parquet(ohlcv_dir / name / "1d.parquet", columns=["close"]).sort_index()
            if d not in bars.index:
                continue
            i = bars.index.get_loc(d)
            if i + 60 >= len(bars):
                continue
            fwd = float(bars["close"].iloc[i + 60] / bars["close"].iloc[i] - 1.0)
            lab = float(picks.loc[picks["name"] == name, "ret_raw"].iloc[0])
            rows.append({"date": str(pd.Timestamp(d).date()), "name": name,
                         "label": lab, "own_fwd_60sess": fwd, "residual": lab - fwd})
    res = pd.DataFrame(rows)
    per_date_spread = res.groupby("date")["residual"].agg(lambda s: float(s.max() - s.min()))
    return {
        "n_probes": int(len(res)),
        "per_date_residual_spread_max": float(per_date_spread.max()),
        "per_date_residual_means": {k: float(v) for k, v in res.groupby("date")["residual"].mean().items()},
        "interpretation": (
            "residual = label - own 60-session fwd return; a per-date constant "
            "(spread ~0) proves the label is a 60-trading-session forward return "
            "in RETURN units net of a common per-date benchmark"
        ),
    }


# ---------------------------------------------------------------------------
# Check 2 — split + embargo (recomputed; leak test on the panel grid)
# ---------------------------------------------------------------------------
def make_split(top: pd.DataFrame, n_train: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dates = sorted(top["date"].unique())
    train_dates = dates[:n_train]
    embargo_dates = dates[n_train:n_train + EMBARGO_DAYS]
    test_dates = dates[n_train + EMBARGO_DAYS:]
    train = top[top["date"].isin(set(train_dates))].reset_index(drop=True)
    test = top[top["date"].isin(set(test_dates))].reset_index(drop=True)
    info = {
        "n_oos_dates": len(dates),
        "n_train_dates": len(train_dates),
        "n_embargo_dates": len(embargo_dates),
        "n_test_dates": len(test_dates),
        "train_window": [str(pd.Timestamp(train_dates[0]).date()), str(pd.Timestamp(train_dates[-1]).date())],
        "embargo_window": [str(pd.Timestamp(embargo_dates[0]).date()), str(pd.Timestamp(embargo_dates[-1]).date())],
        "test_window": [str(pd.Timestamp(test_dates[0]).date()), str(pd.Timestamp(test_dates[-1]).date())],
        "test_regime_dates": {k: int(v) for k, v in test.groupby("regime")["date"].nunique().items()},
        "test_regime_picks": {k: int(v) for k, v in test["regime"].value_counts().items()},
        "train_regime_dates": {k: int(v) for k, v in train.groupby("regime")["date"].nunique().items()},
    }
    return train, test, info


def check_embargo_leak(top: pd.DataFrame, panel_dates: pd.DatetimeIndex, n_train: int) -> dict:
    """Label horizon = 60 sessions on the PANEL grid. The last train label
    window is [train_end, panel_grid[idx(train_end)+60]]. Leak iff that end
    date >= first test date."""
    dates = sorted(top["date"].unique())
    train_end = pd.Timestamp(dates[n_train - 1])
    test_start = pd.Timestamp(dates[n_train + EMBARGO_DAYS])
    grid = panel_dates.sort_values().unique()
    i = int(np.searchsorted(grid, train_end.to_datetime64()))
    label_end = pd.Timestamp(grid[i + 60]) if i + 60 < len(grid) else None
    gaps = pd.Series(pd.DatetimeIndex(dates)).diff().dt.days.dropna()
    return {
        "pick_grid_max_gap_days": int(gaps.max()),
        "pick_grid_is_daily_trading": bool(gaps.max() <= 5),
        "train_end": str(train_end.date()),
        "last_train_label_window_end": str(label_end.date()) if label_end is not None else None,
        "test_start": str(test_start.date()),
        "train_label_overlaps_test": bool(label_end is not None and label_end >= test_start),
        "sessions_between_label_end_and_test_start": (
            int(np.searchsorted(grid, test_start.to_datetime64()) - (i + 60))
            if label_end is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Conditioning candidates — INDEPENDENT constructions
# ---------------------------------------------------------------------------
def own_logistic_irls(X: np.ndarray, y: np.ndarray, alpha: float = 1.0,
                      n_iter: int = 100, tol: float = 1e-10) -> np.ndarray:
    """L2-regularized logistic via IRLS/Newton; matches sklearn
    LogisticRegression(C=1/alpha) (intercept unpenalized)."""
    n, k = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    w = np.zeros(k + 1)
    pen = np.eye(k + 1) * alpha
    pen[-1, -1] = 0.0  # do not penalize intercept
    for _ in range(n_iter):
        z = Xb @ w
        p = 1.0 / (1.0 + np.exp(-z))
        Wdiag = p * (1 - p) + 1e-12
        grad = Xb.T @ (p - y) + pen @ w
        H = (Xb * Wdiag[:, None]).T @ Xb + pen
        step = np.linalg.solve(H, grad)
        w -= step
        if np.abs(step).max() < tol:
            break
    return w


def add_features(table: pd.DataFrame, top: pd.DataFrame, ohlcv_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    disp = table.groupby("date")["score"].std().rename("dispersion")
    cutoff = top.groupby("date")["score"].min().rename("decile_cutoff")
    top = top.merge(disp, on="date").merge(cutoff, on="date")
    top["margin"] = top["score"] - top["decile_cutoff"]
    # var5: trailing 60d vol + ADV (own implementation, exact as-of via searchsorted)
    frames = []
    for name in sorted(top["name"].unique()):
        bars = pd.read_parquet(ohlcv_dir / name / "1d.parquet", columns=["close", "volume"]).sort_index()
        ret = bars["close"].pct_change()
        vol60 = ret.rolling(VOL_ADV_WINDOW).std()
        adv60 = (bars["close"] * bars["volume"]).rolling(VOL_ADV_WINDOW).mean()
        f = pd.DataFrame({"vol60": vol60, "adv60": adv60})
        f["name"] = name
        f.index.name = "date"
        frames.append(f.reset_index())
    allf = pd.concat(frames, ignore_index=True)
    top = top.merge(allf, on=["date", "name"], how="left")
    top["adv_rank"] = top.groupby("date")["adv60"].rank(pct=True)
    med_v = top["vol60"].median()
    top["vol60"] = top["vol60"].fillna(med_v)
    top["adv_rank"] = top["adv_rank"].fillna(0.5)
    feats = ["dispersion", "margin", "vol60", "adv_rank"]
    for reg in sorted(top["regime"].unique())[:-1]:
        col = f"regime_{reg}"
        top[col] = (top["regime"] == reg).astype(float)
        feats.append(col)
    return top, feats


def build_candidates(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> dict:
    cands: dict = {}
    # C1 — own IRLS logistic, threshold = train-median predicted probability
    Xtr = train[feats].to_numpy(dtype=float)
    Xte = test[feats].to_numpy(dtype=float)
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    w = own_logistic_irls((Xtr - mu) / sd, train["y"].to_numpy(dtype=float))
    p_tr = 1.0 / (1.0 + np.exp(-(np.hstack([(Xtr - mu) / sd, np.ones((len(Xtr), 1))]) @ w)))
    p_te = 1.0 / (1.0 + np.exp(-(np.hstack([(Xte - mu) / sd, np.ones((len(Xte), 1))]) @ w)))
    tau = float(np.median(p_tr))
    cands["C1_logit_all"] = {
        "train": pd.Series(p_tr >= tau, index=train.index),
        "test": pd.Series(p_te >= tau, index=test.index),
        "tau": tau,
        "coef": {f: float(c) for f, c in zip(feats + ["intercept"], w)},
    }
    # C2 — regime whitelist learned on train
    base_hr = float(train["y"].mean())
    reg_hr = train.groupby("regime")["y"].mean()
    whitelist = sorted(reg_hr[reg_hr > base_hr].index.tolist())
    cands["C2_regime_whitelist"] = {
        "train": train["regime"].isin(whitelist),
        "test": test["regime"].isin(whitelist),
        "whitelist": whitelist,
        "train_regime_hit_rates": {k: float(v) for k, v in reg_hr.items()},
    }
    # C3 — recomputed DIRECTLY from within-date score median (mathematically
    # equivalent to margin>=median-margin iff the cutoff is per-date constant)
    def top_half(df: pd.DataFrame, strict: bool = False) -> pd.Series:
        med = df.groupby("date")["score"].transform("median")
        return df["score"] > med if strict else df["score"] >= med
    cands["C3_margin_top_half"] = {"train": top_half(train), "test": top_half(test)}
    cands["C3_strict_gt_variant"] = {"train": top_half(train, True), "test": top_half(test, True)}
    return cands


# ---------------------------------------------------------------------------
# Metrics — own implementation of the §4 suite
# ---------------------------------------------------------------------------
def evaluate(df: pd.DataFrame, mask: pd.Series, rng: np.random.Generator,
             ycol: str = "y") -> dict:
    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    m = mask.to_numpy()
    y = df[ycol].to_numpy(dtype=float)
    r = df["ret_raw"].to_numpy(dtype=float)
    date_arr = df["date"].to_numpy()

    n_base, n_cond = len(df), int(m.sum())
    capital_frac = n_cond / n_base
    active_frac = df.loc[mask, "date"].nunique() / n_dates
    hit_lift = float(y[m].mean() - y.mean())
    pick_lift = float(r[m].mean() - r.mean())
    book_lift = pick_lift * PERIODS_PER_YEAR * capital_frac

    blocks = [dates[i:i + BLOCK] for i in range(0, n_dates, BLOCK)]
    idx_by_date = {d: np.flatnonzero(date_arr == d) for d in dates}
    block_idx = [np.concatenate([idx_by_date[d] for d in blk]) for blk in blocks]
    hit_bs, pick_bs, book_bs, n_empty = [], [], [], 0
    for _ in range(N_BOOT):
        chosen = rng.integers(0, len(blocks), size=len(blocks))
        idx = np.concatenate([block_idx[j] for j in chosen])
        mm = m[idx]
        nc = int(mm.sum())
        if nc == 0:
            n_empty += 1
            continue
        hl = y[idx][mm].mean() - y[idx].mean()
        pl = r[idx][mm].mean() - r[idx].mean()
        hit_bs.append(hl)
        pick_bs.append(pl)
        book_bs.append(pl * PERIODS_PER_YEAR * (nc / len(idx)))

    def ci(v):
        return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]

    winners = int(y.sum())
    kept = int(y[m].sum())
    drop_frac = (winners - kept) / winners if winners else 0.0

    def turnover(msk: np.ndarray) -> int:
        sets = {d: frozenset(df.loc[pd.Series(msk, index=df.index) & (df["date"] == d), "name"]) for d in dates}
        return sum(len(sets[a] ^ sets[b]) for a, b in zip(dates[:-1], dates[1:]))

    t_base = turnover(np.ones(n_base, dtype=bool))
    t_cond = turnover(m)
    turnover_x = t_cond / t_base if t_base else float("inf")
    hit_ci, pick_ci, book_ci = ci(hit_bs), ci(pick_bs), ci(book_bs)
    gates = {
        "a": bool(book_lift >= GATES["a_book_lift_ann_min"] and book_ci[0] > 0),
        "b": bool(pick_lift >= GATES["b_per_pick_lift_min"] and pick_ci[0] > 0),
        "c": bool(hit_lift >= GATES["c_hit_rate_lift_min"] and hit_ci[0] > 0),
        "d": bool(active_frac >= GATES["d_active_frac_min"]),
        "e": bool(drop_frac <= GATES["e_max_winner_drop"] and turnover_x <= GATES["e_max_turnover_multiple"]),
    }
    return {
        "n_picks_baseline": n_base,
        "n_picks_conditioned": n_cond,
        "capital_fraction": capital_frac,
        "active_day_fraction": active_frac,
        "baseline_hit_rate": float(y.mean()),
        "conditioned_hit_rate": float(y[m].mean()),
        "hit_rate_lift": hit_lift,
        "hit_rate_lift_ci95": hit_ci,
        "per_pick_lift": pick_lift,
        "per_pick_lift_ci95": pick_ci,
        "book_lift_annualized": book_lift,
        "book_lift_annualized_ci95": book_ci,
        "baseline_winners": winners,
        "kept_winners": kept,
        "dropped_winners": winners - kept,
        "winner_drop_fraction": drop_frac,
        "turnover_baseline": t_base,
        "turnover_conditioned": t_cond,
        "turnover_multiple": turnover_x,
        "bootstrap_resamples_dropped_empty": n_empty,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
    }


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--umbrella", type=Path, default=Path("/Users/renhao/git/github/RenQuant"))
    ap.add_argument("--out-dir", type=Path, default=Path("doc/research/evidence/2026-07-03-s9-verification"))
    args = ap.parse_args()
    u = args.umbrella
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    pick_table = u / "data/exp/oos_pick_table_recipe_v2.parquet"
    rawlabel = u / "data/alpha158_291_fundamental_dataset_rawlabel.parquet"
    ohlcv = u / "data/ohlcv"

    print("[1] units + join (independent)")
    top, units = check_units_and_join(pick_table, rawlabel)
    panel_dates = pd.DatetimeIndex(
        pd.read_parquet(rawlabel, columns=["date"])["date"].unique()
    )
    sem = check_label_semantics(top, ohlcv, panel_dates, rng=rng)
    units["label_semantics_probe"] = sem
    print(json.dumps({k: v for k, v in units.items() if k != "label_semantics_probe"}, indent=2))
    print(json.dumps(sem, indent=2))

    print("[2] split + embargo (independent)")
    n_dates_all = int(top["date"].nunique())
    n_train_round = round(TRAIN_FRAC * n_dates_all)
    train, test, split = make_split(top, n_train_round)
    leak = check_embargo_leak(top, panel_dates, n_train_round)
    split["embargo_leak_check"] = leak
    print(json.dumps(split, indent=2))

    print("[3-5] features + candidates + §4 metric suite (independent)")
    table = pd.read_parquet(pick_table)
    top, feats = add_features(table, top, ohlcv)
    # re-split with features attached
    train, test, _ = make_split(top, n_train_round)
    cands = build_candidates(train, test, feats)

    results: dict = {}
    for cname in ["C1_logit_all", "C2_regime_whitelist", "C3_margin_top_half"]:
        c = cands[cname]
        results[cname] = {
            "train": evaluate(train, c["train"], rng),
            "test": evaluate(test, c["test"], rng),
        }
        for extra in ("tau", "coef", "whitelist", "train_regime_hit_rates"):
            if extra in c:
                results[cname][extra] = c[extra]
        t = results[cname]["test"]
        print(f"  {cname}: book={t['book_lift_annualized']*1e4:+.1f}bps/yr "
              f"CI[{t['book_lift_annualized_ci95'][0]*1e4:+.1f},{t['book_lift_annualized_ci95'][1]*1e4:+.1f}] "
              f"hit={t['hit_rate_lift']*100:+.2f}pp drop={t['winner_drop_fraction']:.4f} "
              f"active={t['active_day_fraction']:.4f} gates={t['gates']}")

    print("[6] fragility variants (adversarial)")
    variants: dict = {}
    # (i) floor split: train = 304 dates instead of round()'s 305
    tr304, te304, sp304 = make_split(top, int(TRAIN_FRAC * n_dates_all))
    c304 = build_candidates(tr304, te304, feats)
    variants["floor_split_train304"] = {
        "split": {k: sp304[k] for k in ("n_train_dates", "n_test_dates", "test_window")},
        "C3_test": evaluate(te304, c304["C3_margin_top_half"]["test"], rng),
        "C2_test_active_frac": float(
            te304.loc[c304["C2_regime_whitelist"]["test"], "date"].nunique() / te304["date"].nunique()
        ),
    }
    # (ii) C3 with strict > median
    variants["C3_strict_gt_median_test"] = evaluate(test, cands["C3_strict_gt_variant"]["test"], rng)
    # (iii) LITERAL standardized-units label for C3's binding gate (e) + (c)
    y_lit_test = evaluate(test, cands["C3_margin_top_half"]["test"], rng, ycol="y_literal_z")
    variants["C3_literal_z_label_test"] = {
        "winner_drop_fraction": y_lit_test["winner_drop_fraction"],
        "hit_rate_lift": y_lit_test["hit_rate_lift"],
        "note": "y = (standardized fwd_60d_excess > 0.0011); gates (a)/(b) are "
                "return-unit-denominated and are NOT meaningful under this label",
    }
    for k, v in variants.items():
        if "winner_drop_fraction" in v:
            print(f"  {k}: drop={v['winner_drop_fraction']:.4f}")
        elif "C3_test" in v:
            print(f"  {k}: C3 drop={v['C3_test']['winner_drop_fraction']:.4f} "
                  f"gates={v['C3_test']['gates']} C2_active={v['C2_test_active_frac']:.4f}")

    any_pass = [k for k, v in results.items() if v["test"]["all_gates_pass"]]
    verdict = "GO" if any_pass else "NULL"
    out = {
        "task": "S9 verification — independent adversarial recomputation",
        "verifies": "doc/research/2026-07-03-s9-track-a-conditional.md (PR #262)",
        "independent_choices": {
            "bootstrap": {"n": N_BOOT, "seed": SEED, "block": BLOCK},
            "logistic": "own numpy IRLS (L2 alpha=1, unpenalized intercept)",
            "C3": "recomputed from within-date score median directly",
        },
        "check1_units_and_join": units,
        "check2_split": split,
        "check3_candidates": results,
        "check6_fragility_variants": variants,
        "recomputed_verdict": verdict,
        "candidates_passing_all_gates": any_pass,
    }
    (args.out_dir / "verification.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"[V] recomputed verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
