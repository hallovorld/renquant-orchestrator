#!/usr/bin/env python
"""M-SIG C4 — trend-scanning label through the REPAIRED WF gate (frozen spec #243 r4 §1.4).

Confirmatory measurement of the C4 candidate against its FROZEN thresholds:

    GO   iff the placebo-difference (trend-scan minus raw, repaired-gate semantics)
         block-bootstrap one-sided 98.33% CI lower bound > 0.02 (Bonferroni k=3, §2a),
    KILL iff the same-level upper bound < 0.02,
    else INCONCLUSIVE.

Every interpretation this script commits to was frozen BEFORE it ran, in
`doc/research/evidence/2026-07-03-c4/c4_frozen_addendum.json` (committed first — the
M8/C2 freeze-first pattern). The spec governs; deviations are disclosed as deviations
in the memo, never patched silently.

Repaired-gate semantics mirrored (cited, not reinvented):
  - genuine_ic = aligned_real_ic - placebo_ic
    (renquant-backtesting src/renquant_backtesting/wf_gate/runner.py, S3 = #61)
  - placebo leg = the SAME frozen model score evaluated against the label shifted
    -2*label_horizon sessions per ticker, clipped to +/-0.5; aligned_real_ic = same
    score vs the real (unclipped) label on rows where the shifted label exists;
    per-date cross-sectional Spearman with >=5 names
    (renquant-backtesting src/renquant_backtesting/analysis/
     analyze_manifest_sanity_placebo.py::shift_diagnostics; gate shift = 2x horizon
     per runner.py _gate_shift_days = 2 * _label_horizon)
  - estimand: delta_genuine(t) = genuine_ic_trendscan(t) - genuine_ic_raw(t),
    paired per (date, regime-cell); the mean over the gating cell (BULL_CALM,
    frozen in the addendum per spec design rule 2) is the gated quantity.

Bootstrap: carried-mask moving-block bootstrap over the FULL contiguous trading-date
axis (block=60, n_boot=2000) — adapted from scripts/c3_residual_momentum.py::
block_bootstrap_conditional_mean (the C3 round-2 corrected pattern: blocks are drawn
on the calendar axis so they can never splice regime episodes or inter-cut gaps).

Usage (umbrella venv, read-only on all data):
    .../RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 42 --out OUT
    .../RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 43 --out OUT
    .../RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 44 --out OUT
    .../RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py analyze --out OUT \
        --evidence doc/research/evidence/2026-07-03-c4

Writes ONLY under --out (scratchpad) and --evidence. Never touches production paths,
never trains in the repo tree, never git-anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("msig-c4")

# --------------------------------------------------------------------------- frozen
UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
PANEL = UMBRELLA / "data/alpha158_291_fundamental_dataset_multih.parquet"
REGIME = UMBRELLA / "data/alpha158_291_fund_regime_dataset.parquet"
RAW = "fwd_60d_excess"            # economic target; also the raw arm's training label
TS = "trendscan_label"
LABEL_HORIZON_SESS = 60
GATE_SHIFT_SESS = 2 * LABEL_HORIZON_SESS   # repaired-gate placebo shift (runner.py:2354)
EMBARGO_SESS = 65                          # > label horizon (60) + buffer, frozen
MARGIN = 0.02                              # frozen, spec §1.4
MARGIN_BRACKET = (0.015, 0.02, 0.025)      # frozen sensitivity bracket, spec §1.4
BLOCK = 60
N_BOOT = 2000
SEEDS = (42, 43, 44)
ALPHA_ONESIDED = 0.05 / 3                  # Bonferroni k=3 -> one-sided 98.33% CI
GATING_CELL = "BULL_CALM"                  # frozen in the addendum (design rule 2)
MIN_NAMES = 5                              # shift_diagnostics min_names
N_FLOOR = 600                              # spec shared default
PC_TARGET = 2 * MARGIN                     # planted effect at 2x the frozen bar
PC_W_GRID = tuple(round(w, 2) for w in np.arange(0.02, 0.41, 0.02))

PARAMS = {"objective": "rank:pairwise", "eta": 0.05, "max_depth": 5,
          "min_child_weight": 50, "subsample": 0.7, "colsample_bytree": 0.7,
          "nthread": 8, "verbosity": 0}
N_ROUNDS = 100

# 8 embargo-repaired cuts (frozen in the addendum; 3y rolling train, 1y test)
CUTS = [
    ("2016-01-04", "2017-12-31", 2018),
    ("2016-01-04", "2018-12-31", 2019),
    ("2017-01-01", "2019-12-31", 2020),
    ("2018-01-01", "2020-12-31", 2021),
    ("2019-01-01", "2021-12-31", 2022),
    ("2020-01-01", "2022-12-31", 2023),
    ("2021-01-01", "2023-12-31", 2024),
    ("2022-01-01", "2024-12-31", 2025),
]
REGIME_COLS = {"regime_p_bull_calm": "BULL_CALM",
               "regime_p_bear": "BEAR",
               "regime_p_bull_volatile": "BULL_VOLATILE"}
CELLS = ("ALL", "BULL_CALM", "BEAR", "BULL_VOLATILE")


# ------------------------------------------------------------------ label (verbatim)
def _ols_slope_t(hs, Rs):
    """Verbatim from scripts/experiments/2026-06-23-trendscan-wf-gate.py."""
    x = np.asarray(hs, float)
    n = len(x); xm = x.mean(); sxx = ((x - xm) ** 2).sum()
    rm = Rs.mean(axis=1, keepdims=True)
    b = ((x - xm)[None, :] * (Rs - rm)).sum(axis=1) / sxx
    a = rm[:, 0] - b * xm
    fit = a[:, None] + b[:, None] * x[None, :]
    sse = ((Rs - fit) ** 2).sum(axis=1)
    se_b = np.sqrt((sse / (n - 2)) / sxx) + 1e-12
    return b / se_b


def build_trendscan_label(df: pd.DataFrame) -> np.ndarray:
    """Signed t-stat of the most significant forward-trend window (verbatim 06-23)."""
    need = ["fwd_5d_excess_raw", "fwd_10d_excess_raw", "fwd_20d_excess_raw",
            "fwd_60d_excess_raw"]
    r5, r10, r20, r60 = (df[c].to_numpy(float) for c in need)
    z = np.zeros(len(df))
    t_a = _ols_slope_t([0, 5, 10, 20], np.column_stack([z, r5, r10, r20]))
    t_b = _ols_slope_t([0, 5, 10, 20, 60], np.column_stack([z, r5, r10, r20, r60]))
    lab = np.where(np.abs(t_a) >= np.abs(t_b), t_a, t_b)
    miss = ~np.isfinite(r5 + r10 + r20 + r60)
    lab[miss] = np.nan
    return lab


# ------------------------------------------------------------------------- data load
def load_merged() -> tuple[pd.DataFrame, list[str]]:
    log.info("loading panel %s", PANEL)
    df = pd.read_parquet(PANEL)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=[RAW]).copy()  # unresolved real labels never enter (0623 conv.)
    df[TS] = build_trendscan_label(df)

    reg = pd.read_parquet(REGIME, columns=["ticker", "date"] + list(REGIME_COLS))
    reg["date"] = pd.to_datetime(reg["date"])
    probs = reg[list(REGIME_COLS)].to_numpy(float)
    names = [REGIME_COLS[c] for c in REGIME_COLS]
    reg["regime"] = np.array(names)[probs.argmax(1)]
    df = df.merge(reg[["ticker", "date", "regime"]], on=["ticker", "date"], how="inner")

    # repaired-gate placebo label: real label shifted -2x horizon sessions per ticker,
    # clipped +/-0.5 (shift_diagnostics semantics). Computed on the merged frame's
    # per-ticker session axis BEFORE any cut filtering.
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df["y_placebo"] = (
        df.groupby("ticker")[RAW].shift(-GATE_SHIFT_SESS).clip(-0.5, 0.5)
    )
    excl = {"ticker", "date", "split_label", "regime", TS, "y_placebo",
            "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess",
            "fwd_5d_excess_raw", "fwd_10d_excess_raw", "fwd_20d_excess_raw",
            "fwd_60d_excess_raw"}
    feat_cols = [c for c in df.columns if c not in excl]
    log.info("merged rows=%d dates=%d feats=%d", len(df), df["date"].nunique(),
             len(feat_cols))
    return df, feat_cols


def embargoed_test_start(panel_dates: pd.DatetimeIndex, train_end: pd.Timestamp):
    after = panel_dates[panel_dates > train_end]
    if len(after) <= EMBARGO_SESS:
        return None
    return after[EMBARGO_SESS]


# -------------------------------------------------------------------------- training
def train_predict(tr: pd.DataFrame, te: pd.DataFrame, feat_cols: list[str],
                  label: str, seed: int) -> np.ndarray | None:
    """0623 conventions: winsorize label 1/99, standardize X by train stats, clip 5."""
    import xgboost as xgb
    tr = tr.dropna(subset=[label])
    if len(tr) < 1000 or len(te) < 100:
        return None
    xtr = tr[feat_cols].fillna(0).to_numpy(np.float64)
    ytr = tr[label].clip(*np.percentile(tr[label], [1, 99])).to_numpy(np.float64)
    xte = te[feat_cols].fillna(0).to_numpy(np.float64)
    mu, sd = xtr.mean(0), xtr.std(0) + 1e-9
    xtr = ((xtr - mu) / sd).clip(-5, 5)
    xte = ((xte - mu) / sd).clip(-5, 5)
    order = np.argsort(tr["date"].to_numpy(), kind="stable")
    _, gsz = np.unique(tr["date"].to_numpy()[order], return_counts=True)
    dtr = xgb.DMatrix(xtr[order], label=ytr[order])
    dtr.set_group(gsz)
    params = dict(PARAMS, seed=seed)
    booster = xgb.train(params, dtr, num_boost_round=N_ROUNDS)
    return booster.predict(xgb.DMatrix(xte))


def cmd_train(seed: int, out: Path) -> None:
    df, feat_cols = load_merged()
    panel_dates = pd.DatetimeIndex(np.sort(df["date"].unique()))
    frames = []
    for ci, (ts_, tre, test_year) in enumerate(CUTS, 1):
        tre_ts = pd.Timestamp(tre)
        test_start = embargoed_test_start(panel_dates, tre_ts)
        test_end = pd.Timestamp(f"{test_year}-12-31")
        tr = df[(df["date"] >= ts_) & (df["date"] <= tre_ts)]
        te = df[(df["date"] >= test_start) & (df["date"] <= test_end)].copy()
        if len(te) < 100:
            log.info("cut%d: test too small, skipped", ci)
            continue
        gap_sess = int((panel_dates > tre_ts).argmax())  # noqa: F841 (embargo logged below)
        log.info("cut%d train %s..%s (%d rows) | test %s..%s (%d rows, embargo=%d sess)",
                 ci, ts_, tre, len(tr), test_start.date(), te["date"].max().date(),
                 len(te), EMBARGO_SESS)
        t0 = time.time()
        p_raw = train_predict(tr, te, feat_cols, RAW, seed)
        p_ts = train_predict(tr, te, feat_cols, TS, seed)
        if p_raw is None or p_ts is None:
            log.info("cut%d: insufficient training rows, skipped", ci)
            continue
        keep = te[["ticker", "date", "regime", RAW, "y_placebo"]].copy()
        keep["cut"] = ci
        keep["score_raw"] = p_raw
        keep["score_ts"] = p_ts
        frames.append(keep)
        log.info("cut%d trained both arms in %.1fs", ci, time.time() - t0)
    scores = pd.concat(frames, ignore_index=True)
    out.mkdir(parents=True, exist_ok=True)
    fp = out / f"scores_seed{seed}.parquet"
    scores.to_parquet(fp, index=False)
    log.info("seed %d: wrote %s (%d rows)", seed, fp, len(scores))


# --------------------------------------------------------------- IC series machinery
def _spear(a: np.ndarray, b: np.ndarray) -> float:
    r = spearmanr(a, b)[0]
    return float(r) if np.isfinite(r) else np.nan


def per_date_delta_series(scores: pd.DataFrame,
                          score_cols: tuple[str, str] = ("score_ts", "score_raw"),
                          ) -> pd.DataFrame:
    """Per (date, cell): aligned real + placebo IC per arm, and delta_genuine.

    Aligned set = rows with a defined 2x-shifted placebo label (shift_diagnostics
    'common index' restriction); y_real unclipped, y_placebo already clipped.
    """
    cand_col, base_col = score_cols
    al = scores.dropna(subset=["y_placebo", RAW]).copy()
    rows = []
    for date, g in al.groupby("date", sort=True):
        for cell in CELLS:
            sub = g if cell == "ALL" else g[g["regime"] == cell]
            if len(sub) < MIN_NAMES:
                continue
            y, yp = sub[RAW].to_numpy(float), sub["y_placebo"].to_numpy(float)
            ic_r_c = _spear(sub[cand_col].to_numpy(float), y)
            ic_p_c = _spear(sub[cand_col].to_numpy(float), yp)
            ic_r_b = _spear(sub[base_col].to_numpy(float), y)
            ic_p_b = _spear(sub[base_col].to_numpy(float), yp)
            if not all(np.isfinite([ic_r_c, ic_p_c, ic_r_b, ic_p_b])):
                continue
            rows.append({"date": date, "cell": cell, "n_names": len(sub),
                         "ic_real_cand": ic_r_c, "ic_placebo_cand": ic_p_c,
                         "ic_real_base": ic_r_b, "ic_placebo_base": ic_p_b,
                         "genuine_cand": ic_r_c - ic_p_c,
                         "genuine_base": ic_r_b - ic_p_b,
                         "delta_genuine": (ic_r_c - ic_p_c) - (ic_r_b - ic_p_b)})
    return pd.DataFrame(rows)


def carried_mask_block_bootstrap(vals: np.ndarray, *, block: int, n_boot: int,
                                 seed: int) -> np.ndarray | None:
    """C3 round-2 corrected pattern (scripts/c3_residual_momentum.py::
    block_bootstrap_conditional_mean), applied on the FULL trading-date axis:
    `vals` is NaN wherever the cell is undefined (off-window, off-regime, thin
    cross-section); blocks are drawn on the full axis and average only the finite
    values inside each drawn block — a block can never splice dates that are far
    apart on the calendar."""
    a = np.asarray(vals, float)
    fin = np.isfinite(a)
    n = len(a)
    if n <= block or fin.sum() < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    means = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        av = a[idx]
        m = np.isfinite(av)
        means[i] = av[m].mean() if m.sum() >= 2 else np.nan
    means = means[np.isfinite(means)]
    return means if len(means) else None


def effective_block_coverage(vals: np.ndarray, *, block: int) -> dict:
    """C3's diagnostic: non-overlapping full-axis blocks with >=2 finite values."""
    a = np.asarray(vals, float)
    n_full = len(a) // block
    usable = sum(1 for i in range(n_full)
                 if np.isfinite(a[i * block:(i + 1) * block]).sum() >= 2)
    return {"n_full_blocks": int(n_full), "n_blocks_with_ge2_in_cell": int(usable)}


def summarize_boot(means: np.ndarray | None) -> dict | None:
    if means is None:
        return None
    lo95, hi95 = np.percentile(means, [2.5, 97.5])
    lb, ub = np.percentile(means, [100 * ALPHA_ONESIDED, 100 * (1 - ALPHA_ONESIDED)])
    return {"boot_se": float(means.std(ddof=1)),
            "ci95_two_sided": [float(lo95), float(hi95)],
            "lb_one_sided_9833": float(lb),
            "ub_one_sided_9833": float(ub),
            "n_boot_effective": int(len(means))}


def axis_series(per_date: pd.DataFrame, axis: pd.DatetimeIndex, cell: str,
                col: str = "delta_genuine") -> np.ndarray:
    sub = per_date[per_date["cell"] == cell].set_index("date")[col]
    return sub.reindex(axis).to_numpy(float)


def verdict_from_bounds(lb: float, ub: float, margin: float, n_dates: int) -> str:
    if n_dates < N_FLOOR:
        return "INCONCLUSIVE (n floor not met)"
    if lb > margin:
        return "GO"
    if ub < margin:
        return "KILL"
    return "INCONCLUSIVE"


def aggregate_verdict(per_seed: list[str]) -> str:
    if all(v == "GO" for v in per_seed):
        return "GO"
    if all(v.startswith("KILL") for v in per_seed):
        return "KILL"
    return "INCONCLUSIVE"


def evaluate_cell(per_date: pd.DataFrame, axis: pd.DatetimeIndex, cell: str,
                  boot_seed: int) -> dict:
    sub = per_date[per_date["cell"] == cell]
    vals = axis_series(per_date, axis, cell)
    boots = carried_mask_block_bootstrap(vals, block=BLOCK, n_boot=N_BOOT,
                                         seed=boot_seed)
    summ = summarize_boot(boots)
    n_dates = int(len(sub))
    out = {
        "cell": cell,
        "n_dates": n_dates,
        "block_coverage": effective_block_coverage(vals, block=BLOCK),
        "mean_delta_genuine": float(sub["delta_genuine"].mean()) if n_dates else None,
        "mean_genuine_cand": float(sub["genuine_cand"].mean()) if n_dates else None,
        "mean_genuine_base": float(sub["genuine_base"].mean()) if n_dates else None,
        "mean_aligned_real_cand": float(sub["ic_real_cand"].mean()) if n_dates else None,
        "mean_placebo_cand": float(sub["ic_placebo_cand"].mean()) if n_dates else None,
        "mean_aligned_real_base": float(sub["ic_real_base"].mean()) if n_dates else None,
        "mean_placebo_base": float(sub["ic_placebo_base"].mean()) if n_dates else None,
        "bootstrap": summ,
    }
    if summ:
        out["verdict_by_margin"] = {
            str(m): verdict_from_bounds(summ["lb_one_sided_9833"],
                                        summ["ub_one_sided_9833"], m, n_dates)
            for m in MARGIN_BRACKET}
        out["verdict_frozen_margin"] = out["verdict_by_margin"][str(MARGIN)]
    else:
        out["verdict_frozen_margin"] = "INCONCLUSIVE (bootstrap unavailable)"
    return out


# ------------------------------------------------------------------ positive controls
def _cs_rank_z(g: pd.Series) -> pd.Series:
    r = g.rank(method="average")
    return (r - r.mean()) / (r.std(ddof=0) + 1e-12)


def positive_controls(scores42: pd.DataFrame, axis: pd.DatetimeIndex) -> dict:
    """Frozen in the addendum: PC-A planted at 2x bar (grid-calibrated plant size),
    PC-B candidate-arm within-date permutation, PC-C both arms permuted."""
    s = scores42.dropna(subset=["y_placebo", RAW]).copy()
    s["z_raw_score"] = s.groupby("date")["score_raw"].transform(_cs_rank_z)
    s["z_y"] = s.groupby("date")[RAW].transform(_cs_rank_z)

    # --- PC-A: sweep w for a BULL_CALM planted delta_genuine closest to +0.04
    sweep = []
    for w in PC_W_GRID:
        s["score_pc"] = s["z_raw_score"] + w * s["z_y"]
        pd_pc = per_date_delta_series(s, score_cols=("score_pc", "score_raw"))
        cellm = pd_pc[pd_pc["cell"] == GATING_CELL]["delta_genuine"].mean()
        sweep.append({"w": w, "bull_calm_delta_genuine": float(cellm)})
    best = min(sweep, key=lambda r: abs(r["bull_calm_delta_genuine"] - PC_TARGET))
    w_star = best["w"]
    s["score_pc"] = s["z_raw_score"] + w_star * s["z_y"]
    pd_pc = per_date_delta_series(s, score_cols=("score_pc", "score_raw"))
    pc_a = {}
    for bseed in SEEDS:
        cell = evaluate_cell(pd_pc, axis, GATING_CELL, bseed)
        pc_a[str(bseed)] = {"verdict": cell["verdict_frozen_margin"],
                            "lb_9833": cell["bootstrap"]["lb_one_sided_9833"],
                            "mean": cell["mean_delta_genuine"],
                            "n_dates": cell["n_dates"]}
    pc_a_pass = all(v["verdict"] == "GO" for v in pc_a.values())

    # --- PC-B: candidate arm permuted within date
    rng = np.random.default_rng(7)
    s["score_perm"] = s.groupby("date")["score_ts"].transform(
        lambda g: g.to_numpy()[rng.permutation(len(g))])
    pd_b = per_date_delta_series(s, score_cols=("score_perm", "score_raw"))
    pc_b = {}
    for bseed in SEEDS:
        cell = evaluate_cell(pd_b, axis, GATING_CELL, bseed)
        pc_b[str(bseed)] = {"verdict": cell["verdict_frozen_margin"],
                            "lb_9833": cell["bootstrap"]["lb_one_sided_9833"],
                            "mean": cell["mean_delta_genuine"]}
    pc_b_pass = all(v["verdict"] != "GO" for v in pc_b.values())

    # --- PC-C: both arms permuted within date (independent permutations)
    rng2 = np.random.default_rng(8)
    s["score_perm_base"] = s.groupby("date")["score_raw"].transform(
        lambda g: g.to_numpy()[rng2.permutation(len(g))])
    pd_c = per_date_delta_series(s, score_cols=("score_perm", "score_perm_base"))
    pc_c = {}
    for bseed in SEEDS:
        cell = evaluate_cell(pd_c, axis, GATING_CELL, bseed)
        pc_c[str(bseed)] = {"verdict": cell["verdict_frozen_margin"],
                            "ub_9833": cell["bootstrap"]["ub_one_sided_9833"],
                            "mean": cell["mean_delta_genuine"]}
    pc_c_pass = all(v["verdict"] != "GO" for v in pc_c.values())

    return {
        "level": "score-level (frozen addendum; disclosed deviation D4)",
        "pc_a_planted_detection": {"target": PC_TARGET, "w_grid_sweep": sweep,
                                   "w_star": w_star, "per_boot_seed": pc_a,
                                   "acceptance": "GO on all 3 bootstrap seeds",
                                   "pass": bool(pc_a_pass)},
        "pc_b_permuted_candidate": {"per_boot_seed": pc_b,
                                    "acceptance": "not GO on any seed",
                                    "pass": bool(pc_b_pass)},
        "pc_c_both_permuted": {"per_boot_seed": pc_c,
                               "acceptance": "not GO on any seed",
                               "pass": bool(pc_c_pass)},
        "all_pass": bool(pc_a_pass and pc_b_pass and pc_c_pass),
    }


# ------------------------------------------------------------------- proxy sim spread
def proxy_spread(scores: pd.DataFrame) -> dict:
    """Diagnostic-only proxy (frozen addendum: can NEVER satisfy the frozen sim
    secondary condition). Top-minus-bottom quintile mean fwd_60d_excess per date."""
    al = scores.dropna(subset=[RAW]).copy()
    out = {}
    for arm, col in (("trendscan", "score_ts"), ("raw", "score_raw")):
        sp = []
        for _, g in al.groupby("date"):
            if len(g) < 25:
                continue
            q = len(g) // 5
            gs = g.sort_values(col)
            sp.append(gs[RAW].tail(q).mean() - gs[RAW].head(q).mean())
        sp = np.asarray(sp)
        sub = sp[::LABEL_HORIZON_SESS]  # non-overlapping 60-session subsample
        out[arm] = {
            "mean_daily_60d_spread": float(sp.mean()),
            "n_dates": int(len(sp)),
            "naive_sharpe_overlapping_CAVEAT": float(sp.mean() / (sp.std(ddof=1) + 1e-12)),
            "nonoverlap_sharpe_60d_periods": float(sub.mean() / (sub.std(ddof=1) + 1e-12)),
            "n_nonoverlap_periods": int(len(sub)),
        }
    return out


# ---------------------------------------------------------------------------- analyze
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def code_provenance(repo_root: Path) -> dict:
    def _git(*args):
        try:
            return subprocess.run(["git", "-C", str(repo_root), *args],
                                  capture_output=True, text=True, timeout=30
                                  ).stdout.strip()
        except Exception:
            return None
    return {"head": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(_git("status", "--porcelain"))}


def cmd_analyze(out: Path, evidence: Path) -> None:
    import scipy
    import xgboost
    evidence.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[1]

    per_seed_series: dict[int, pd.DataFrame] = {}
    for seed in SEEDS:
        fp = out / f"scores_seed{seed}.parquet"
        scores = pd.read_parquet(fp)
        log.info("seed %d: computing per-date IC series (%d score rows)", seed,
                 len(scores))
        per_seed_series[seed] = per_date_delta_series(scores)

    # full contiguous trading-date axis spanning all seeds' aligned dates
    all_dates = pd.concat([s["date"] for s in per_seed_series.values()])
    panel_dates = pd.DatetimeIndex(np.sort(pd.read_parquet(
        PANEL, columns=["date"])["date"].unique()))
    axis = panel_dates[(panel_dates >= all_dates.min()) & (panel_dates <= all_dates.max())]
    log.info("bootstrap axis: %s..%s (%d sessions)", axis[0].date(), axis[-1].date(),
             len(axis))

    results: dict = {"per_seed": {}}
    for seed, series in per_seed_series.items():
        cells = {c: evaluate_cell(series, axis, c, seed) for c in CELLS}
        # per-year window-artifact table (gating cell + pooled)
        per_year = {}
        for cell in ("ALL", GATING_CELL):
            sub = series[series["cell"] == cell].copy()
            sub["year"] = sub["date"].dt.year
            per_year[cell] = {
                str(y): {"mean_delta_genuine": float(g["delta_genuine"].mean()),
                         "mean_genuine_cand": float(g["genuine_cand"].mean()),
                         "mean_genuine_base": float(g["genuine_base"].mean()),
                         "n_dates": int(len(g))}
                for y, g in sub.groupby("year")}
            pre = sub[sub["year"] <= 2020]
            post = sub[sub["year"] >= 2021]
            per_year[cell]["pre_2021"] = {
                "mean_delta_genuine": float(pre["delta_genuine"].mean()),
                "n_dates": int(len(pre))}
            per_year[cell]["2021_plus"] = {
                "mean_delta_genuine": float(post["delta_genuine"].mean()),
                "n_dates": int(len(post))}
        results["per_seed"][str(seed)] = {"cells": cells, "per_year": per_year}

    gate_verdicts = [results["per_seed"][str(s)]["cells"][GATING_CELL]
                     ["verdict_frozen_margin"] for s in SEEDS]
    pooled_verdicts = [results["per_seed"][str(s)]["cells"]["ALL"]
                       ["verdict_frozen_margin"] for s in SEEDS]
    results["verdict"] = {
        "gating_cell": GATING_CELL,
        "per_seed_gating": dict(zip(map(str, SEEDS), gate_verdicts)),
        "final": aggregate_verdict(gate_verdicts),
        "pooled_sensitivity_per_seed": dict(zip(map(str, SEEDS), pooled_verdicts)),
        "pooled_sensitivity_final": aggregate_verdict(pooled_verdicts),
        "margin_bracket_final": {
            str(m): aggregate_verdict(
                [results["per_seed"][str(s)]["cells"][GATING_CELL]
                 ["verdict_by_margin"][str(m)] for s in SEEDS])
            for m in MARGIN_BRACKET},
    }

    # positive controls + proxy on seed 42
    scores42 = pd.read_parquet(out / "scores_seed42.parquet")
    log.info("running positive controls (seed-42 scores)")
    pcs = positive_controls(scores42, axis)
    results["positive_controls"] = pcs
    results["proxy_spread_diagnostic_only"] = proxy_spread(scores42)

    # evidence boundary + manifest
    n_gate = results["per_seed"]["42"]["cells"][GATING_CELL]["n_dates"]
    boot42 = results["per_seed"]["42"]["cells"][GATING_CELL]["bootstrap"]
    results["evidence_boundary"] = {
        "oos_window": [str(axis[0].date()), str(axis[-1].date())],
        "test_years": [c[2] for c in CUTS],
        "n_dates_gating_cell_seed42": n_gate,
        "n_dates_pooled_seed42": results["per_seed"]["42"]["cells"]["ALL"]["n_dates"],
        "regime_cells": list(CELLS),
        "universe": "fixed 292-name alpha158 panel universe (current constituents "
                    "applied historically; no delisting handling -> survivorship-"
                    "tilted ABSOLUTE levels; both arms share the tilt, the paired "
                    "difference is within-panel comparative)",
        "resolved_outcome_era": "real labels resolved through ~60 sessions before "
                                "panel end (2026-02-11); the 2x-shift placebo leg "
                                "additionally truncates the aligned set ~120 sessions "
                                "before panel end",
        "power_note_illustrative": {
            "boot_se_gating_cell_seed42": boot42["boot_se"] if boot42 else None,
            "note": "detecting delta >= margin at one-sided 98.33% needs roughly "
                    "mean >= margin + 2.13*SE; with the reported SE this is the "
                    "minimal detectable effect — illustrative, not authoritative "
                    "(spec section 1 power-note convention)",
        },
    }
    results["manifest"] = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "inputs": {"panel": {"path": str(PANEL), "sha256": sha256_file(PANEL)},
                   "regime": {"path": str(REGIME), "sha256": sha256_file(REGIME)}},
        "score_files": {str(s): sha256_file(out / f"scores_seed{s}.parquet")
                        for s in SEEDS},
        "code": {**code_provenance(repo_root),
                 "script_sha256": sha256_file(Path(__file__).resolve())},
        "env": {"python": sys.version.split()[0], "numpy": np.__version__,
                "pandas": pd.__version__, "scipy": scipy.__version__,
                "xgboost": xgboost.__version__},
        "frozen": {"margin": MARGIN, "margin_bracket": list(MARGIN_BRACKET),
                   "block": BLOCK, "n_boot": N_BOOT, "seeds": list(SEEDS),
                   "alpha_one_sided": ALPHA_ONESIDED, "gate_shift_sess": GATE_SHIFT_SESS,
                   "embargo_sess": EMBARGO_SESS, "n_floor": N_FLOOR,
                   "gating_cell": GATING_CELL},
    }

    (evidence / "c4_results.json").write_text(json.dumps(results, indent=2))
    # per-date series (all seeds) for audit
    frames = []
    for seed, series in per_seed_series.items():
        d = series.copy()
        d["seed"] = seed
        frames.append(d)
    pd.concat(frames, ignore_index=True).to_csv(
        evidence / "c4_per_date_series.csv.gz", index=False, compression="gzip")
    log.info("VERDICT (gating cell %s, frozen margin %.3f): %s | per-seed %s",
             GATING_CELL, MARGIN, results["verdict"]["final"], gate_verdicts)
    log.info("positive controls all_pass=%s", pcs["all_pass"])
    log.info("evidence written to %s", evidence)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--seed", type=int, required=True, choices=list(SEEDS))
    t.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--evidence", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "train":
        cmd_train(args.seed, args.out)
    else:
        cmd_analyze(args.out, args.evidence)


if __name__ == "__main__":
    main()
