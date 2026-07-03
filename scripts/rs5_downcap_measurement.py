#!/usr/bin/env python
"""RS-5 / M7 down-cap panel measurement — FALLBACK-PANEL execution.

Frozen spec: doc/design/2026-07-02-rs5-downcap-panel-spec.md (merged PR #250,
merge commit 23dc9ff37ff1f1747e55c94363bc2794d167f482, 2026-07-02T14:14:07-07:00
— the demonstrable prospectivity freeze point per spec §7).
Machine-readable contract:
doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json — loaded at
startup; every parameter this runner executes is validated against it and the
runner REFUSES to run on any undeclared deviation (spec §7).

PANEL MODE: FALLBACK (spec §2). Norgate procurement is trial/POC-first per RS-3
r2/r3 and no trial has run, so the PRIMARY constituency-by-date panel cannot be
built. Per the frozen spec: a fallback-panel run is pipeline feasibility +
exploratory sensitivity ONLY; NEITHER a GO NOR a NO-GO computed here is
decision-grade, NEITHER may feed D3, and M7's verdict while the primary panel
is pending is INCONCLUSIVE. This runner hard-codes that: its verdict output is
"INCONCLUSIVE (fallback panel; primary pending)" regardless of what the gate
arithmetic says; gate arithmetic is still computed and reported in full as the
pipeline-feasibility demonstration the spec assigns to this branch.

READ-ONLY on all production data (umbrella stores are opened read-only; no git
commands against any primary checkout; all intermediates in --scratch).
Writes ONLY: --out (committed evidence dir) and --scratch (session scratchpad).

One-command reproduce (from this repo's root, umbrella venv for the pinned
regime chain):

    /Users/renhao/git/github/RenQuant/.venv/bin/python \
        scripts/rs5_downcap_measurement.py \
        --scratch <dir with membership+profile snapshots> \
        --out doc/research/evidence/2026-07-03-rs5-downcap
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Frozen constants (every value below is validated against the prereg contract
# at startup — see validate_against_contract; mismatch => refuse to run).
# ---------------------------------------------------------------------------
PANEL_WINDOW_START = "2014-01-01"
LIQ_FLOOR_ADV_USD = 5_000_000
LIQ_FLOOR_WINDOW = 63
PRICE_FLOOR_USD = 5.0
MIN_HISTORY_SESSIONS = 252
TARGET_SIZE = (800, 1400)
HARD_BOUNDS = (500, 1600)

COST_BUCKETS = [  # (adv_min, adv_max, round_trip_bps)
    (25_000_000, None, 25.0),   # A
    (10_000_000, 25_000_000, 40.0),  # B
    (5_000_000, 10_000_000, 60.0),   # C
]

HEADLINES = {"MOM": "mom_12_1", "REV": "st_rev_21"}
# VAL / QUAL: declared INCONCLUSIVE-by-coverage BEFORE any IC computation —
# no admissible-timestamp small-cap fundamentals store exists locally (the FMP
# harvests cover the 291-name large-cap universe only) and the subscribed FMP
# Starter tier caps history at ~5y < 60% of the 2014->2026 panel x date grid
# (contract admissibility.vaL_qual_timestamp_coverage_floor_pct = 60). This
# declaration is coverage-arithmetic only; no VAL/QUAL IC is ever computed here.
INCONCLUSIVE_BY_COVERAGE_FAMILIES = {"VAL", "QUAL"}
MOM_SIBLINGS = ["mom_6_1", "ma200_dist", "pct_52w_high"]

HORIZON_GATE = 60
HORIZON_SUPPORT = 20
LABEL_CLIP = 0.5  # C3/repo label convention (fwd excess clipped +/-0.5)

BLOCK = 60
N_BOOT = 2000
SEEDS = (42, 43, 44)
K_FAMILIES = 4
ALPHA_ONESIDED = 0.05 / K_FAMILIES  # 0.0125 -> one-sided 98.75% CI
N_PERM_SHUFFLE = 200

GATE_A_IC = 0.02
GATE_B_SHARPE = 0.5
GATE_B_REBAL = 60
GATE_B_OFFSETS = (0, 20, 40)
MIN_POOLED_DATES = 600
MIN_NAMES_PER_DATE = 200
PANEL_AVG_MIN_NAMES = 500
MIN_REGIME_CELL_DATES = 150
YEARLY_MIN_CLEAN_DATES = 100
YEARLY_POSITIVE_FRACTION = 0.60

POSITIVE_CONTROL_NOISE_SD = 9.95  # pre-declared: planted Pearson ~0.10 on rank-z scale
TRADING_DAYS = 252

DEFAULT_UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
FREEZE_COMMIT = "23dc9ff37ff1f1747e55c94363bc2794d167f482"
FREEZE_TIMESTAMP = "2026-07-02T14:14:07-07:00"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_head(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prereg-contract load + validate-or-refuse (spec §7)
# ---------------------------------------------------------------------------
def load_contract(repo_root: Path) -> tuple[dict, str]:
    p = repo_root / "doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json"
    return json.loads(p.read_text()), sha256_file(p)


def validate_against_contract(c: dict) -> list[str]:
    """Compare every parameter this runner executes against the contract.
    Returns the list of mismatches; caller refuses to run if non-empty."""
    errs = []

    def chk(name, mine, theirs):
        if mine != theirs:
            errs.append(f"{name}: runner={mine!r} contract={theirs!r}")

    u = c["universe"]
    chk("liquidity_floor_adv_usd", LIQ_FLOOR_ADV_USD, u["liquidity_floor_adv_usd"])
    chk("liquidity_floor_window_sessions", LIQ_FLOOR_WINDOW, u["liquidity_floor_window_sessions"])
    chk("liquidity_floor_statistic", "median_dollar_volume", u["liquidity_floor_statistic"])
    chk("price_floor_usd", PRICE_FLOOR_USD, u["price_floor_usd"])
    chk("minimum_history_sessions", MIN_HISTORY_SESSIONS, u["minimum_history_sessions"])
    chk("panel_window_start", PANEL_WINDOW_START, u["panel_window_start"])
    chk("membership_timing", "daily_truth_monthly_floor_reevaluation", u["membership_timing"])
    chk("membership_reevaluation_rule", "last_session_of_month_applied_next_session",
        u["membership_reevaluation_rule"])
    chk("target_panel_size", {"min": TARGET_SIZE[0], "max": TARGET_SIZE[1],
                              "hard_bounds": {"min": HARD_BOUNDS[0], "max": HARD_BOUNDS[1]}},
        u["target_panel_size_names_per_date"])

    sd = c["survivorship_and_delisting"]
    chk("fallback_panel_role", "pipeline_feasibility_and_exploratory_sensitivity_only",
        sd["fallback_panel_role"])
    chk("fallback_panel_may_gate_d3", False, sd["fallback_panel_may_gate_d3"])

    cm = {(b["adv_min_usd"], b["adv_max_usd"]): b["round_trip_bps"]
          for b in c["cost_model"]["buckets"]}
    mine_cm = {(lo, hi): bps for lo, hi, bps in COST_BUCKETS}
    chk("cost_buckets", mine_cm, cm)

    ff = c["factor_families"]
    chk("family_size_k", K_FAMILIES, ff["family_size_k"])
    chk("headline_MOM", HEADLINES["MOM"], ff["headline_factors"]["MOM"])
    chk("headline_REV", HEADLINES["REV"], ff["headline_factors"]["REV"])
    chk("mom_siblings", MOM_SIBLINGS, ff["diagnostic_only_factors"]["MOM"])

    e = c["estimand"]
    chk("statistic", "daily_cross_sectional_spearman_rank_ic", e["statistic"])
    chk("target", "fwd_60d_excess_vs_spy", e["target"])
    chk("gating_quantity", "placebo_clean_difference", e["gating_quantity"])
    chk("placebo_construction", "label_shifted_plus_horizon_within_ticker_defined_only_where_both_exist",
        e["placebo_construction"])

    b = c["bootstrap"]
    chk("block", BLOCK, b["block_size_sessions"])
    chk("n_boot", N_BOOT, b["n_boot"])
    chk("seeds", list(SEEDS), b["seeds"])
    chk("alpha_onesided", ALPHA_ONESIDED, b["per_family_one_sided_alpha"])
    chk("multiplicity_k", K_FAMILIES, b["multiplicity_k"])

    a = c["admissibility"]["sample_floors"]
    chk("min_pooled_clean_decision_dates", MIN_POOLED_DATES, a["min_pooled_clean_decision_dates"])
    chk("min_names_per_date", MIN_NAMES_PER_DATE, a["min_names_per_date_cross_section"])
    chk("panel_average_min_names", PANEL_AVG_MIN_NAMES, a["panel_average_min_names_per_date"])
    chk("min_regime_cell_dates", MIN_REGIME_CELL_DATES, a["per_regime_cell_min_dates_for_any_verdict"])

    v = c["verdict_logic"]
    chk("gate_a_threshold", GATE_A_IC, v["gate_a_net_relevant_placebo_clean_ic"]["point_estimate_threshold"])
    chk("gate_a_seeds", list(SEEDS), v["gate_a_net_relevant_placebo_clean_ic"]["must_hold_on_all_seeds"])
    gb = v["gate_b_net_return_round_2_corrected"]
    chk("gate_b_sharpe", GATE_B_SHARPE, gb["annualized_net_sharpe_point_estimate_threshold"])
    chk("gate_b_rebalance", GATE_B_REBAL, gb["rebalance_sessions"])
    chk("gate_b_offsets", len(GATE_B_OFFSETS), gb["staggered_start_offsets"])
    chk("gate_c1_gates", False, v["gate_c_regime_robustness_round_2_split"]["c1_largest_regime_cell_removed"]["gates"])
    return errs


# ---------------------------------------------------------------------------
# Panel construction (fallback protocol, spec §1-2)
# ---------------------------------------------------------------------------
def load_membership(scratch: Path) -> tuple[list[str], dict]:
    snap = json.loads((scratch / "vtwo_membership_snapshot.json").read_text())
    tickers = sorted(snap["tickers"].keys())
    return tickers, snap


def load_profiles(scratch: Path) -> dict:
    snap = json.loads((scratch / "fmp_profiles_snapshot.json").read_text())
    return snap["profiles"]


def apply_exclusions(tickers: list[str], profiles: dict) -> tuple[list[str], dict]:
    """Frozen §1 exclusions, implemented from the FMP profile snapshot
    (approximation of GICS/SIC codes — disclosed in the manifest)."""
    kept, excl = [], {"fund_or_etf": [], "adr_or_foreign": [], "reit": [],
                      "no_profile": [], "non_alpha_ticker": []}
    for t in tickers:
        if not t.isalpha():
            excl["non_alpha_ticker"].append(t)
            continue
        p = profiles.get(t)
        if p is None:
            excl["no_profile"].append(t)
            continue
        if p.get("isFund") or p.get("isEtf"):
            excl["fund_or_etf"].append(t)
            continue
        if p.get("isAdr") or (p.get("country") not in (None, "US")):
            excl["adr_or_foreign"].append(t)
            continue
        ind = (p.get("industry") or "")
        sec = (p.get("sector") or "")
        if ind.upper().startswith("REIT") or "REIT" in ind.upper() or sec == "Real Estate":
            excl["reit"].append(t)
            continue
        kept.append(t)
    return kept, excl


def dedupe_share_classes(tickers: list[str], profiles: dict,
                         adv_last: pd.Series) -> tuple[list[str], list[tuple[str, str]]]:
    """Secondary-share-class exclusion: among members mapping to the same
    companyName, keep the line with the higher trailing ADV (heuristic,
    disclosed)."""
    byname: dict[str, list[str]] = {}
    for t in tickers:
        nm = (profiles.get(t, {}) or {}).get("companyName") or t
        byname.setdefault(nm, []).append(t)
    kept, dropped = [], []
    for nm, ts in byname.items():
        if len(ts) == 1:
            kept.append(ts[0])
            continue
        best = max(ts, key=lambda x: float(adv_last.get(x, 0.0) or 0.0))
        kept.append(best)
        dropped.extend((t, nm) for t in ts if t != best)
    return sorted(kept), dropped


def load_bars(umbrella: Path, tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str], dict]:
    """Return (adj_close, raw_close, dollar_volume) matrices + missing list +
    per-file sha256 fingerprint inputs."""
    adj, raw, dv, missing = {}, {}, {}, []
    file_hashes = {}
    for t in tickers:
        p = umbrella / "data" / "ohlcv" / t / "1d.parquet"
        if not p.exists():
            missing.append(t)
            continue
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index).normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if "adj_close" in df.columns:
            a = df["adj_close"]
        else:
            a = df["close"]
        adj[t] = a
        raw[t] = df["close"]
        dv[t] = df["close"] * df["volume"]
        file_hashes[t] = sha256_file(p)
    A = pd.DataFrame(adj).sort_index()
    R = pd.DataFrame(raw).reindex(A.index)
    D = pd.DataFrame(dv).reindex(A.index)
    A = A[A.index >= pd.Timestamp(PANEL_WINDOW_START)]
    R = R.reindex(A.index)
    D = D.reindex(A.index)
    return A, R, D, missing, file_hashes


def monthly_membership(raw: pd.DataFrame, dv: pd.DataFrame) -> pd.DataFrame:
    """Monthly floor re-evaluation: at each last session of month, compute
    trailing-63-session median dollar volume >= $5M, price >= $5, >= 252
    sessions of history; APPLIED NEXT SESSION until the next evaluation
    (spec §1 membership timing)."""
    idx = raw.index
    month_key = idx.to_period("M")
    is_month_end = pd.Series(month_key, index=idx).groupby(month_key).transform(
        lambda s: s.index == s.index.max())
    eval_dates = idx[is_month_end.to_numpy()]

    med_dv = dv.rolling(LIQ_FLOOR_WINDOW, min_periods=LIQ_FLOOR_WINDOW).median()
    hist_count = raw.notna().cumsum()

    member = pd.DataFrame(False, index=idx, columns=raw.columns)
    pos = {d: i for i, d in enumerate(idx)}
    for k, e in enumerate(eval_dates):
        elig = ((med_dv.loc[e] >= LIQ_FLOOR_ADV_USD)
                & (raw.loc[e] >= PRICE_FLOOR_USD)
                & (hist_count.loc[e] >= MIN_HISTORY_SESSIONS)).fillna(False)
        start_i = pos[e] + 1
        end_i = pos[eval_dates[k + 1]] + 1 if k + 1 < len(eval_dates) else len(idx)
        if start_i >= len(idx):
            break
        member.iloc[start_i:end_i] = elig.to_numpy()[None, :].repeat(end_i - start_i, axis=0)
    return member


# ---------------------------------------------------------------------------
# Factors (canonical sighunt formulas, spec §4) + labels (C3 convention)
# ---------------------------------------------------------------------------
def compute_factors(px: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    out["mom_12_1"] = px.shift(21) / px.shift(252) - 1.0
    out["mom_6_1"] = px.shift(21) / px.shift(126) - 1.0
    out["st_rev_21"] = -1.0 * (px / px.shift(21) - 1.0)
    sma200 = px.rolling(200, min_periods=150).mean()
    out["ma200_dist"] = px / sma200 - 1.0
    hi252 = px.rolling(252, min_periods=200).max()
    out["pct_52w_high"] = px / hi252
    return out


def fwd_excess(close: pd.DataFrame, spy_close: pd.Series, horizon: int) -> pd.DataFrame:
    """fwd_h PRICE-return excess vs SPY, clipped +/-0.5 (C3 repo convention)."""
    f_stock = close.shift(-horizon) / close - 1.0
    f_spy = spy_close.shift(-horizon) / spy_close - 1.0
    return f_stock.sub(f_spy, axis=0).clip(-LABEL_CLIP, LABEL_CLIP)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = math.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def per_date_ic(score: pd.DataFrame, label: pd.DataFrame,
                placebo: pd.DataFrame, min_names: int) -> pd.DataFrame:
    """Per-date real IC, placebo IC (label shifted +horizon), clean = real -
    placebo, defined only where both exist (C3 convention; gate-(d) min-names
    floor applied per date)."""
    rows = []
    sv = score.to_numpy()
    lv = label.reindex(columns=score.columns).to_numpy()
    pv = placebo.reindex(columns=score.columns).to_numpy()
    for i, dt in enumerate(score.index):
        s = sv[i]
        ms = np.isfinite(s)
        if ms.sum() < min_names:
            continue
        rec = {"date": dt, "n_scored": int(ms.sum())}
        m1 = ms & np.isfinite(lv[i])
        if m1.sum() >= min_names:
            rec["real_ic"] = _spearman(s[m1], lv[i][m1])
            rec["n_real"] = int(m1.sum())
        m2 = ms & np.isfinite(pv[i])
        if m2.sum() >= min_names:
            rec["placebo_ic"] = _spearman(s[m2], pv[i][m2])
            rec["n_placebo"] = int(m2.sum())
        if "real_ic" in rec and "placebo_ic" in rec:
            rec["clean_ic"] = rec["real_ic"] - rec["placebo_ic"]
        rows.append(rec)
    df = pd.DataFrame(rows)
    return df.set_index("date") if len(df) else df


def block_bootstrap_stats(a: np.ndarray, *, block: int, n_boot: int, seed: int,
                          stat: str = "mean") -> dict:
    """Moving-block bootstrap on the FULL series (pooled gate — no cell
    pre-filtering, so the naive full-series draw is the correct geometry).
    Returns point estimate + one-sided Bonferroni-k4 98.75% bounds + 95% CI."""
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n <= block or n < 2:
        return {"error": f"series too short (n={n})"}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    res = a[idx]
    if stat == "mean":
        dist = res.mean(axis=1)
        point = float(a.mean())
    elif stat == "sharpe":
        mu = res.mean(axis=1)
        sd = res.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            dist = np.where(sd > 0, mu / sd * np.sqrt(TRADING_DAYS), np.nan)
        dist = dist[np.isfinite(dist)]
        point = float(a.mean() / a.std(ddof=1) * np.sqrt(TRADING_DAYS)) if a.std(ddof=1) > 0 else float("nan")
    else:
        raise ValueError(stat)
    return {
        "point": point,
        "n": n,
        "onesided_lb_98_75": float(np.quantile(dist, ALPHA_ONESIDED)),
        "onesided_ub_98_75": float(np.quantile(dist, 1.0 - ALPHA_ONESIDED)),
        "ci95": [float(np.quantile(dist, 0.025)), float(np.quantile(dist, 0.975))],
        "seed": seed,
    }


def bootstrap_mask_removed_mean(vals: np.ndarray, keep_mask: np.ndarray, *,
                                block: int, n_boot: int, seed: int) -> dict:
    """Carried-mask conditional bootstrap (C3 round-2 pattern): resample
    date-blocks of the FULL series, then average only kept (out-of-removed-cell)
    values inside each resample — never a pre-filtered subseries."""
    fin = np.isfinite(vals)
    a, k = vals[fin], keep_mask[fin].astype(bool)
    n = len(a)
    if n <= block or k.sum() < 2:
        return {"error": "too short"}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    av, kv = a[idx], k[idx]
    with np.errstate(invalid="ignore"):
        dist = np.where(kv.sum(axis=1) >= 2,
                        (av * kv).sum(axis=1) / np.maximum(kv.sum(axis=1), 1), np.nan)
    dist = dist[np.isfinite(dist)]
    return {
        "point": float(a[k].mean()),
        "n_kept": int(k.sum()),
        "onesided_lb_98_75": float(np.quantile(dist, ALPHA_ONESIDED)),
        "onesided_ub_98_75": float(np.quantile(dist, 1.0 - ALPHA_ONESIDED)),
        "seed": seed,
    }


def shuffle_floor(score: pd.DataFrame, label: pd.DataFrame, dates: pd.DatetimeIndex,
                  min_names: int, seed: int = 42) -> dict:
    """sighunt-native within-date shuffle noise floor on NON-OVERLAPPING
    (stride-60) dates, N_PERM=200: permute the label cross-section per date."""
    rng = np.random.default_rng(seed)
    sv = score.reindex(dates).to_numpy()
    lv = label.reindex(index=dates, columns=score.columns).to_numpy()
    reals, perm_means = [], []
    keep = []
    for i in range(len(dates)):
        m = np.isfinite(sv[i]) & np.isfinite(lv[i])
        if m.sum() >= min_names:
            keep.append((sv[i][m], lv[i][m]))
            reals.append(_spearman(sv[i][m], lv[i][m]))
    if not keep:
        return {"error": "no dates"}
    for _ in range(N_PERM_SHUFFLE):
        ics = []
        for s, f in keep:
            fp = f.copy()
            rng.shuffle(fp)
            ics.append(_spearman(s, fp))
        perm_means.append(float(np.mean(ics)))
    pm = np.asarray(perm_means)
    return {
        "n_dates": len(keep),
        "real_mean_ic": float(np.mean(reals)),
        "perm_mean": float(pm.mean()),
        "perm_std": float(pm.std(ddof=1)),
        "clears_2sigma": bool(abs(np.mean(reals)) > abs(pm.mean()) + 2 * pm.std(ddof=1)),
        "n_perm": N_PERM_SHUFFLE,
    }


# ---------------------------------------------------------------------------
# Gate (b): long-only top-decile-minus-SPY with §3 realized costs
# ---------------------------------------------------------------------------
def adv_bucket_rt_bps(adv: float, shift_bps: float = 0.0) -> float:
    for lo, hi, bps in COST_BUCKETS:
        if adv >= lo and (hi is None or adv < hi):
            return bps + shift_bps
    return COST_BUCKETS[-1][2] + shift_bps  # below-floor drift => bucket C


def portfolio_gate_b(factor: pd.DataFrame, member: pd.DataFrame, adj: pd.DataFrame,
                     med_dv: pd.DataFrame, spy_tr_ret: pd.Series,
                     scored_dates: pd.DatetimeIndex, *, cost_shift_bps: float = 0.0,
                     long_short: bool = False) -> dict:
    """60-session-rebalance top-decile long-only portfolio vs SPY TR, §3 bucket
    costs charged at realized turnover, 3 staggered offsets averaged.
    long_short=True gives the zero-borrow-fee L/S decile DIAGNOSTIC (no costs)."""
    # ffill + fill_method=None == the classic pad semantics (a gapped bar's
    # move is recovered at the next real bar), version-stable and warning-free
    rets = adj.ffill().pct_change(fill_method=None)
    idx = adj.index
    pos = {d: i for i, d in enumerate(idx)}
    per_offset = {}
    daily_series = {}
    for off in GATE_B_OFFSETS:
        rebal = list(scored_dates[off::GATE_B_REBAL])
        if len(rebal) < 4:
            per_offset[off] = {"error": "too few rebalances"}
            continue
        w = pd.Series(dtype=float)
        w_short = pd.Series(dtype=float)
        out_dates, out_ret, missing_ret_days = [], [], 0
        turnover_sum, cost_sum, n_reb = 0.0, 0.0, 0
        start_i = pos[rebal[0]]
        end_i = len(idx)
        ri = 0
        for i in range(start_i, end_i):
            d = idx[i]
            # portfolio return for day d from held weights
            day_ret = 0.0
            if len(w):
                r = rets.loc[d, w.index]
                nmiss = int(r.isna().sum())
                missing_ret_days += nmiss
                r = r.fillna(0.0)
                day_ret = float((w * r).sum())
                w = w * (1.0 + r)
                s = w.sum()
                gross = float((w_short * rets.loc[d, w_short.index].fillna(0.0)).sum()) if len(w_short) else 0.0
                if long_short:
                    day_ret = day_ret - gross
                if s > 0:
                    w = w / s
                if len(w_short):
                    ws = w_short * (1.0 + rets.loc[d, w_short.index].fillna(0.0))
                    if ws.sum() > 0:
                        w_short = ws / ws.sum()
            cost_today = 0.0
            if ri < len(rebal) and d == rebal[ri]:
                s = factor.loc[d].dropna()
                mem = member.loc[d]
                s = s[[t for t in s.index if bool(mem.get(t, False))]]
                if len(s) >= MIN_NAMES_PER_DATE:
                    ndec = max(int(len(s) // 10), 1)
                    top = s.sort_values(ascending=False).index[:ndec]
                    tgt = pd.Series(1.0 / ndec, index=top)
                    union = tgt.index.union(w.index)
                    dw = tgt.reindex(union).fillna(0.0) - w.reindex(union).fillna(0.0)
                    advs = med_dv.loc[d].reindex(union)
                    rt = advs.map(lambda a: adv_bucket_rt_bps(a if np.isfinite(a) else 0.0,
                                                              cost_shift_bps))
                    cost_today = float((dw.abs() * (rt / 2.0 / 1e4)).sum())
                    turnover_sum += float(dw.abs().sum())
                    cost_sum += cost_today
                    n_reb += 1
                    w = tgt
                    if long_short:
                        bot = s.sort_values(ascending=True).index[:ndec]
                        w_short = pd.Series(1.0 / ndec, index=bot)
                ri += 1
            bench = float(spy_tr_ret.get(d, np.nan))
            if not np.isfinite(bench):
                bench = 0.0
            if long_short:
                net = day_ret  # zero-borrow, zero-cost diagnostic construct
            else:
                net = day_ret - cost_today - bench
            out_dates.append(d)
            out_ret.append(net)
        ser = pd.Series(out_ret, index=out_dates)
        sd = ser.std(ddof=1)
        sharpe = float(ser.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")
        boots = {s: block_bootstrap_stats(ser.to_numpy(), block=BLOCK, n_boot=N_BOOT,
                                          seed=s, stat="sharpe") for s in SEEDS}
        per_offset[off] = {
            "n_days": int(len(ser)),
            "n_rebalances": n_reb,
            "ann_net_sharpe": sharpe,
            "ann_net_return": float(ser.mean() * TRADING_DAYS),
            "avg_turnover_per_rebalance": float(turnover_sum / max(n_reb, 1)),
            "avg_cost_bps_per_rebalance": float(cost_sum / max(n_reb, 1) * 1e4),
            "missing_return_days_filled_zero": missing_ret_days,
            "bootstrap_sharpe": boots,
        }
        daily_series[off] = ser
    sharpes = [v["ann_net_sharpe"] for v in per_offset.values() if "ann_net_sharpe" in v]
    return {
        "per_offset": per_offset,
        "avg_ann_net_sharpe": float(np.mean(sharpes)) if sharpes else float("nan"),
        "cost_shift_bps": cost_shift_bps,
        "construction": "long_short_zero_borrow_diagnostic" if long_short
        else "long_only_top_decile_minus_spy_tr",
    }, daily_series


# ---------------------------------------------------------------------------
# Controls (S-REL P0): positive plant + true-null, through the SAME machinery
# ---------------------------------------------------------------------------
def build_control_factor(label: pd.DataFrame, base_factor: pd.DataFrame,
                         kind: str, seed: int) -> pd.DataFrame:
    """Positive: rank-z(label) + sd*N(0,1) where the base factor is defined
    (same missingness geometry). Null: pure seeded noise on the same grid."""
    rng = np.random.default_rng(seed)
    mask = base_factor.notna() & label.notna()
    noise = pd.DataFrame(rng.standard_normal(label.shape), index=label.index,
                         columns=label.columns)
    if kind == "positive":
        rz = label.rank(axis=1)
        rz = rz.sub(rz.mean(axis=1), axis=0).div(rz.std(axis=1).replace(0, np.nan), axis=0)
        f = rz + POSITIVE_CONTROL_NOISE_SD * noise
    elif kind == "null":
        f = noise
    else:
        raise ValueError(kind)
    return f.where(mask)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scratch", required=True, help="dir with membership/profile snapshots")
    ap.add_argument("--umbrella", default=str(DEFAULT_UMBRELLA))
    ap.add_argument("--out", required=True, help="evidence output dir (committed)")
    ap.add_argument("--quick", action="store_true",
                    help="dev mode: n_boot=100, skip regime chain (never for evidence)")
    ap.add_argument("--skip-regime", action="store_true",
                    help="skip the exploratory per-regime diagnostic (disclosed)")
    ap.add_argument("--regime-cache", default=None,
                    help="path to cached regime series JSON (scratch)")
    args = ap.parse_args()

    t0 = time.time()
    scratch = Path(args.scratch)
    umbrella = Path(args.umbrella)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parent.parent

    print("[0/8] prereg contract: load + validate-or-refuse ...", flush=True)
    contract, contract_sha = load_contract(repo_root)
    errs = validate_against_contract(contract)
    if errs:
        sys.exit("[REFUSE] runner parameters deviate from the prereg contract "
                 "(spec §7 refuse-to-run duty):\n  " + "\n  ".join(errs))
    print(f"    contract ok (sha256={contract_sha[:16]}...) — 0 deviations", flush=True)

    # quick mode is a DEV SHAKEDOWN ONLY: it is applied AFTER the frozen
    # configuration validates, is stamped into every output, and must never be
    # used for committed evidence.
    global N_BOOT
    if args.quick:
        N_BOOT = 100
        print("    [QUICK MODE] n_boot=100 — dev shakedown, NOT evidence", flush=True)

    print("[1/8] membership + profiles + exclusions (fallback protocol §2) ...", flush=True)
    tickers, mem_snap = load_membership(scratch)
    profiles = load_profiles(scratch)
    kept, excl = apply_exclusions(tickers, profiles)
    print(f"    members={len(tickers)} kept-after-exclusions={len(kept)} "
          f"excl={ {k: len(v) for k, v in excl.items()} }", flush=True)

    print("[2/8] bars from the read-only local store ...", flush=True)
    adj, raw, dv, missing_bars, file_hashes = load_bars(umbrella, kept)
    print(f"    bars loaded for {adj.shape[1]} names on {adj.shape[0]} sessions; "
          f"missing-from-store={len(missing_bars)}", flush=True)

    med_dv = dv.rolling(LIQ_FLOOR_WINDOW, min_periods=LIQ_FLOOR_WINDOW).median()
    adv_last = med_dv.iloc[-1]
    deduped, dropped_classes = dedupe_share_classes(list(adj.columns), profiles, adv_last)
    adj, raw, dv = adj[deduped], raw[deduped], dv[deduped]
    med_dv = med_dv[deduped]
    print(f"    secondary-class dedup dropped {len(dropped_classes)}", flush=True)

    print("[3/8] monthly floor re-evaluation -> membership matrix ...", flush=True)
    member = monthly_membership(raw, dv)
    psize = member.sum(axis=1)
    psize_scored = psize[psize >= MIN_NAMES_PER_DATE]
    panel_stats = {
        "dates_with_any_members": int((psize > 0).sum()),
        "panel_size_mean": float(psize[psize > 0].mean()),
        "panel_size_min": int(psize[psize > 0].min()) if (psize > 0).any() else 0,
        "panel_size_max": int(psize.max()),
        "target": list(TARGET_SIZE),
        "hard_bounds": list(HARD_BOUNDS),
        "within_hard_bounds": bool(
            (psize_scored.min() >= HARD_BOUNDS[0]) and (psize_scored.max() <= HARD_BOUNDS[1])
        ) if len(psize_scored) else False,
    }
    print(f"    panel size mean={panel_stats['panel_size_mean']:.0f} "
          f"min={panel_stats['panel_size_min']} max={panel_stats['panel_size_max']}", flush=True)

    print("[4/8] factors + labels + placebos ...", flush=True)
    spy_df = pd.read_parquet(umbrella / "data" / "ohlcv" / "SPY" / "1d.parquet")
    spy_df.index = pd.to_datetime(spy_df.index).normalize()
    spy_close = spy_df["close"].reindex(adj.index)
    spy_div = spy_df.get("dividend", pd.Series(0.0, index=spy_df.index)).reindex(adj.index).fillna(0.0)
    spy_tr_ret = (spy_close + spy_div) / spy_close.shift(1) - 1.0

    factors = compute_factors(adj)
    factors = {k: v.where(member) for k, v in factors.items()}
    label60 = fwd_excess(adj, spy_close, HORIZON_GATE)
    label20 = fwd_excess(adj, spy_close, HORIZON_SUPPORT)
    placebo60 = label60.shift(-HORIZON_GATE)
    placebo20 = label20.shift(-HORIZON_SUPPORT)

    biotech = [t for t in adj.columns
               if "BIOTECH" in ((profiles.get(t, {}) or {}).get("industry") or "").upper()]

    print("[5/8] per-date ICs (headlines + siblings + supporting horizon) ...", flush=True)
    ics: dict[str, pd.DataFrame] = {}
    for name in list(HEADLINES.values()) + MOM_SIBLINGS:
        ics[name] = per_date_ic(factors[name], label60, placebo60, MIN_NAMES_PER_DATE)
    ics_20 = {name: per_date_ic(factors[name], label20, placebo20, MIN_NAMES_PER_DATE)
              for name in HEADLINES.values()}
    ics_exbio = {name: per_date_ic(factors[name].drop(columns=biotech, errors="ignore"),
                                   label60, placebo60, MIN_NAMES_PER_DATE)
                 for name in HEADLINES.values()}

    clean60 = {n: df["clean_ic"].dropna() for n, df in ics.items() if len(df) and "clean_ic" in df}
    scored_dates = ics[HEADLINES["MOM"]].index

    print("[6/8] gates (a)-(d) arithmetic (feasibility demonstration only) ...", flush=True)
    results: dict = {"families": {}}
    for fam, name in HEADLINES.items():
        ser = clean60.get(name, pd.Series(dtype=float))
        boots = {s: block_bootstrap_stats(ser.to_numpy(), block=BLOCK, n_boot=N_BOOT, seed=s)
                 for s in SEEDS}
        halves = {}
        if len(ser) >= 4:
            h = len(ser) // 2
            halves = {"half1_mean": float(ser.iloc[:h].mean()),
                      "half2_mean": float(ser.iloc[h:].mean()),
                      "both_positive": bool(ser.iloc[:h].mean() > 0 and ser.iloc[h:].mean() > 0)}
        yr = ser.groupby(ser.index.year)
        yearly = {int(y): {"mean_clean_ic": float(v.mean()), "n": int(len(v))}
                  for y, v in yr}
        elig_years = {y: d for y, d in yearly.items() if d["n"] >= YEARLY_MIN_CLEAN_DATES}
        frac_pos = (np.mean([d["mean_clean_ic"] > 0 for d in elig_years.values()])
                    if elig_years else float("nan"))
        gate_a = {
            "point": float(ser.mean()) if len(ser) else float("nan"),
            "passes_point_ge_0.02": bool(len(ser) and ser.mean() >= GATE_A_IC),
            "lb_gt_0_all_seeds": bool(all(
                b.get("onesided_lb_98_75", -1) > 0 for b in boots.values())),
            "per_seed": boots,
        }
        results["families"][fam] = {
            "headline": name,
            "n_clean_dates": int(len(ser)),
            "gate_a": gate_a,
            "gate_c2_two_half": halves,
            "gate_c3_yearly": {"per_year": yearly,
                               "eligible_years": len(elig_years),
                               "fraction_positive": float(frac_pos),
                               "passes": bool(elig_years and frac_pos >= YEARLY_POSITIVE_FRACTION)},
            "kill_leg_ub_lt_0.02_all_seeds": bool(all(
                b.get("onesided_ub_98_75", 1) < GATE_A_IC for b in boots.values())),
            "shuffle_floor_nonoverlap": shuffle_floor(
                factors[name], label60, scored_dates[::HORIZON_GATE], MIN_NAMES_PER_DATE),
            "fwd20_supporting": {
                "point": float(ics_20[name]["clean_ic"].dropna().mean())
                if len(ics_20[name]) else float("nan"),
                "seed42_bootstrap": block_bootstrap_stats(
                    ics_20[name]["clean_ic"].dropna().to_numpy(), block=BLOCK,
                    n_boot=N_BOOT, seed=42) if len(ics_20[name]) else {"error": "empty"},
            },
            "ex_biotech_sensitivity": {
                "point": float(ics_exbio[name]["clean_ic"].dropna().mean())
                if len(ics_exbio[name]) else float("nan"),
                "n": int(len(ics_exbio[name])),
                "seed42_bootstrap": block_bootstrap_stats(
                    ics_exbio[name]["clean_ic"].dropna().to_numpy(), block=BLOCK,
                    n_boot=N_BOOT, seed=42) if len(ics_exbio[name]) else {"error": "empty"},
            },
        }
    results["mom_siblings_diagnostic"] = {
        n: {"pooled_clean_ic": float(clean60[n].mean()), "n": int(len(clean60[n]))}
        for n in MOM_SIBLINGS if n in clean60
    }

    # ---- gate (b) ----
    print("    gate (b) long-only top-decile vs SPY TR + cost sensitivity ...", flush=True)
    # benchmark requires SPY: restrict gate-(b) dates to the SPY-covered era
    # (local SPY history starts 2016-01-04 — deviation D6, disclosed)
    spy_start = spy_close.dropna().index.min()
    scored_dates_b = scored_dates[scored_dates >= spy_start]
    gate_b = {}
    for fam, name in HEADLINES.items():
        base, _ = portfolio_gate_b(factors[name], member, adj, med_dv, spy_tr_ret,
                                   scored_dates_b)
        plus10, _ = portfolio_gate_b(factors[name], member, adj, med_dv, spy_tr_ret,
                                     scored_dates_b, cost_shift_bps=10.0)
        minus10, _ = portfolio_gate_b(factors[name], member, adj, med_dv, spy_tr_ret,
                                      scored_dates_b, cost_shift_bps=-10.0)
        ls, _ = portfolio_gate_b(factors[name], member, adj, med_dv, spy_tr_ret,
                                 scored_dates_b, long_short=True)
        gate_b[fam] = {
            "base": base,
            "sensitivity_plus_10bps": {"avg_ann_net_sharpe": plus10["avg_ann_net_sharpe"]},
            "sensitivity_minus_10bps": {"avg_ann_net_sharpe": minus10["avg_ann_net_sharpe"]},
            "ls_zero_borrow_diagnostic": {"avg_ann_sharpe": ls["avg_ann_net_sharpe"]},
            "passes_point_gt_0.5": bool(np.isfinite(base["avg_ann_net_sharpe"])
                                        and base["avg_ann_net_sharpe"] > GATE_B_SHARPE),
        }
    results["gate_b"] = gate_b
    results["gate_b_capacity_note"] = (
        "position sizes this pipeline takes are <=$2k; vs the $5M ADV floor that is "
        "<0.04% of ADV per name — capacity non-binding at current book size")

    # ---- gate (d) ----
    n_pooled = int(len(clean60.get(HEADLINES["MOM"], [])))
    results["gate_d"] = {
        "pooled_clean_dates_MOM": n_pooled,
        "pooled_clean_dates_REV": int(len(clean60.get(HEADLINES["REV"], []))),
        "min_pooled_required": MIN_POOLED_DATES,
        "panel_average_names_scored_dates": float(
            ics[HEADLINES["MOM"]]["n_real"].mean()) if n_pooled else float("nan"),
        "panel_average_min_required": PANEL_AVG_MIN_NAMES,
        "per_date_min_names_enforced": MIN_NAMES_PER_DATE,
        "val_qual_coverage": {
            "status": "INCONCLUSIVE-by-coverage (declared BEFORE any IC computation)",
            "local_smallcap_fundamentals_coverage_pct": 0.0,
            "fmp_starter_history_cap_years": 5,
            "panel_window_years": 12.5,
            "max_attainable_coverage_pct": 40.0,
            "floor_pct": 60.0,
        },
    }

    # ---- (c1) exploratory per-regime diagnostic ----
    regime_counts, c1 = {}, {}
    if args.skip_regime:
        results["regime_diagnostic"] = {"skipped": True,
                                        "reason": "explicitly skipped (disclosed)"}
    else:
        print("[7/8] exploratory per-regime diagnostic (production chain replay; "
              "NOT point-in-time — diagnostic only) ...", flush=True)
        cache = Path(args.regime_cache) if args.regime_cache else scratch / "rs5_regime_series.json"
        if cache.exists():
            reg = pd.read_json(cache)
            reg["date"] = pd.to_datetime(reg["date"])
        else:
            sys.path.insert(0, str(repo_root / "scripts"))
            from c3_residual_momentum import build_regime_series  # noqa: PLC0415
            spy_frame = spy_df.copy()
            reg = build_regime_series(
                list(scored_dates),
                spy_frame=spy_frame,
                pinned_config=umbrella / ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json",
                gmm_artifact=umbrella / "backtesting/renquant_104/artifacts/prod/spy-gmm-regime.json",
                pipeline_src=umbrella / ".subrepo_runtime/repos/renquant-pipeline/src",
                common_src=umbrella / ".subrepo_runtime/repos/renquant-common/src",
            )
            reg[["date", "regime"]].assign(date=reg["date"].astype(str)).to_json(cache)
        reg_map = dict(zip(pd.to_datetime(reg["date"]), reg["regime"]))
        for fam, name in HEADLINES.items():
            ser = clean60[name]
            labels = pd.Series([reg_map.get(d) for d in ser.index], index=ser.index)
            counts = labels.value_counts().to_dict()
            regime_counts[fam] = {str(k): int(v) for k, v in counts.items()}
            per_cell = {str(r): {"n": int((labels == r).sum()),
                                 "mean_clean_ic": float(ser[labels == r].mean())}
                        for r in labels.dropna().unique()}
            largest = max(counts, key=counts.get) if counts else None
            keep = (labels != largest).to_numpy()
            c1[fam] = {
                "per_cell": per_cell,
                "largest_cell": str(largest),
                "largest_cell_removed": {
                    s: bootstrap_mask_removed_mean(ser.to_numpy(), keep, block=BLOCK,
                                                   n_boot=N_BOOT, seed=s) for s in SEEDS},
                "cells_below_150_dates_cannot_pass_or_fail": [
                    str(r) for r, v in per_cell.items() if v["n"] < MIN_REGIME_CELL_DATES],
            }
        results["regime_diagnostic"] = {
            "note": "EXPLORATORY ONLY (spec §5c round-2: c1 does not gate; regime labels "
                    "are not point-in-time — GMM artifact trained 2026-05-22, replayed back)",
            "regime_counts": regime_counts,
            "c1_largest_cell_removed": c1,
        }

    # ---- exploratory liquidity-core diagnostic (M8 #264 §5 mirror-geometry) ----
    print("    exploratory bucket-A liquidity-core cut ...", flush=True)
    core_mask = med_dv >= COST_BUCKETS[0][0]  # bucket A: ADV >= $25M
    lc = {}
    for fam, name in HEADLINES.items():
        f_core = factors[name].where(core_mask)
        icc = per_date_ic(f_core, label60, placebo60, min_names=100)  # NOT a gate; smaller floor disclosed
        if len(icc) and "clean_ic" in icc:
            s = icc["clean_ic"].dropna()
            lc[fam] = {"n_dates": int(len(s)), "pooled_clean_ic": float(s.mean()),
                       "avg_names": float(icc["n_real"].mean()),
                       "note": "exploratory-only; min-names floor 100 (not the gate's 200)"}
        else:
            lc[fam] = {"error": "insufficient cross-section at ADV>=25M"}
    results["exploratory_liquidity_core_bucketA"] = lc

    # ---- controls ----
    print("[8/8] harness controls: positive plant + true-null, all seeds ...", flush=True)
    controls = {"positive": {}, "null": {}}
    base_f = factors[HEADLINES["MOM"]]
    for seed in SEEDS:
        for kind in ("positive", "null"):
            cf = build_control_factor(label60, base_f, kind, seed)
            icc = per_date_ic(cf, label60, placebo60, MIN_NAMES_PER_DATE)
            ser = icc["clean_ic"].dropna() if len(icc) and "clean_ic" in icc else pd.Series(dtype=float)
            b = block_bootstrap_stats(ser.to_numpy(), block=BLOCK, n_boot=N_BOOT, seed=seed)
            detected = bool(len(ser) and ser.mean() >= GATE_A_IC
                            and b.get("onesided_lb_98_75", -1) > 0)
            kill_fires = bool(b.get("onesided_ub_98_75", 1) < GATE_A_IC)
            controls[kind][str(seed)] = {
                "pooled_clean_ic": float(ser.mean()) if len(ser) else float("nan"),
                "bootstrap": b,
                "gate_a_detected": detected,
                "kill_branch_fires": kill_fires,
            }
    controls["positive"]["expected"] = "gate_a_detected=True on all seeds (planted ~0.1 effect)"
    controls["null"]["expected"] = "gate_a_detected=False AND kill_branch_fires=True on all seeds"
    controls["positive"]["pass"] = all(v["gate_a_detected"] for k, v in controls["positive"].items()
                                       if k not in ("expected", "pass"))
    controls["null"]["pass"] = all((not v["gate_a_detected"]) and v["kill_branch_fires"]
                                   for k, v in controls["null"].items()
                                   if k not in ("expected", "pass"))
    results["controls"] = controls

    # ---- verdict (frozen vocabulary; fallback panel => INCONCLUSIVE) ----
    results["verdict"] = {
        "panel_mode": "FALLBACK",
        "m7_verdict": "INCONCLUSIVE (fallback panel; primary constituency-by-date panel "
                      "pending Norgate trial per spec §2/§5)",
        "d3_authority": "NONE — spec §5: neither a GO nor a NO-GO computed on the fallback "
                        "panel is decision-grade; neither may feed D3 under any circumstance",
        "feasibility": "pipeline ran end-to-end on the fallback panel; gate arithmetic "
                       "computed and reported as exploratory sensitivity only",
    }

    # ---- evidence ----
    ev_dates = [str(d.date()) for d in scored_dates]
    per_date_out = {
        name: {
            "dates": [str(d.date()) for d in df.index],
            "real_ic": [round(float(x), 8) if np.isfinite(x) else None for x in df.get("real_ic", pd.Series(dtype=float))],
            "placebo_ic": [round(float(x), 8) if np.isfinite(x) else None for x in df.get("placebo_ic", pd.Series(dtype=float))],
            "clean_ic": [round(float(x), 8) if np.isfinite(x) else None for x in df.get("clean_ic", pd.Series(dtype=float))],
            "n_real": [int(x) if np.isfinite(x) else None for x in df.get("n_real", pd.Series(dtype=float))],
        }
        for name, df in ics.items() if len(df)
    }
    (out / "per_date_ics.json").write_text(json.dumps(per_date_out))

    store_fp = hashlib.sha256(
        json.dumps(sorted(file_hashes.items())).encode()).hexdigest()
    manifest = {
        "runner": "scripts/rs5_downcap_measurement.py",
        "panel_mode": "FALLBACK (spec §2 protocol; Norgate primary unavailable — "
                      "trial/POC not yet run per RS-3 r2/r3)",
        "spec_doc": "doc/design/2026-07-02-rs5-downcap-panel-spec.md",
        "prereg_contract_sha256": contract_sha,
        "freeze_point": {"merge_commit": FREEZE_COMMIT, "merged_at": FREEZE_TIMESTAMP,
                         "pr": 250},
        "code_commit": repo_head(repo_root),
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {
            "membership_snapshot": {
                "file": "inputs/vtwo_membership_snapshot.json",
                "sha256": sha256_file(scratch / "vtwo_membership_snapshot.json"),
                "source": mem_snap.get("source"),
                "as_of": mem_snap.get("as_of"),
                "n_tickers": len(tickers),
            },
            "profiles_snapshot": {
                "file": "inputs/fmp_profiles_snapshot.json",
                "sha256": sha256_file(scratch / "fmp_profiles_snapshot.json"),
            },
            "bar_store": {
                "path": str(umbrella / "data" / "ohlcv"),
                "n_files_loaded": len(file_hashes),
                "combined_fingerprint_sha256": store_fp,
                "spy_file_sha256": sha256_file(umbrella / "data/ohlcv/SPY/1d.parquet"),
            },
        },
        "panel_stats": panel_stats,
        "exclusion_counts": {k: len(v) for k, v in excl.items()},
        "secondary_class_dedup_dropped": len(dropped_classes),
        "missing_from_store": {"n": len(missing_bars), "tickers": missing_bars},
        "biotech_tagged": len(biotech),
        "delisting_return_paths": {
            "vendor_proceeds": 0, "disclosed_consideration": 0, "minus_100_convention": 0,
            "note": "fallback panel is current-membership (survivor-conditioned) by "
                    "construction — no delisted names exist in it; the frozen §2 "
                    "delisting-return machinery is exercisable only on the primary panel",
        },
        "evidence_boundary": {
            "panel_window": [PANEL_WINDOW_START, str(adj.index.max().date())],
            "scored_dates": [ev_dates[0] if ev_dates else None,
                             ev_dates[-1] if ev_dates else None],
            "n_scored_dates": len(ev_dates),
            "resolved_outcome_era_ends": str(adj.index.max().date()),
            "spy_history_starts": str(spy_close.dropna().index.min().date()),
            "n_per_regime": regime_counts.get("MOM", {}),
            "bar_store_stale_note": "broad store bars end 2026-05-08 (spec §2's own "
                                    "staleness note); no refresh performed this run",
        },
        "multiple_comparisons_frame": {
            "family": "k=4 (MOM/REV/VAL/QUAL) Bonferroni, one-sided alpha 0.0125 "
                      "(98.75% CI) — held at k=4 even though VAL/QUAL are "
                      "INCONCLUSIVE-by-coverage (conservative, frozen)",
            "seeds": list(SEEDS),
            "seeds_role": "robustness check on one corrected result, not extra looks",
        },
        "parameters": {
            "horizon_gate": HORIZON_GATE, "horizon_support": HORIZON_SUPPORT,
            "label_clip": LABEL_CLIP, "block": BLOCK, "n_boot": N_BOOT,
            "seeds": list(SEEDS), "alpha_onesided": ALPHA_ONESIDED,
            "gate_a_ic": GATE_A_IC, "gate_b_sharpe": GATE_B_SHARPE,
            "rebalance": GATE_B_REBAL, "offsets": list(GATE_B_OFFSETS),
            "n_perm_shuffle": N_PERM_SHUFFLE,
            "positive_control_noise_sd": POSITIVE_CONTROL_NOISE_SD,
            "quick_mode": bool(args.quick),
        },
        "deviations_disclosed": [
            "D1 PANEL: fallback panel (local survivor-conditioned store x current VTWO "
            "membership), not the primary Norgate constituency-by-date panel — the "
            "spec-native branch when procurement has not run; verdict is INCONCLUSIVE "
            "and nothing here feeds D3",
            "D2 NAMING: runner file is scripts/rs5_downcap_measurement.py (dispatch-"
            "directed deliverable name) not spec §6's scripts/m7_downcap_scan.py; all "
            "§6-item-3 duties (contract load + refuse-on-deviation) are implemented",
            "D3 MEMBERSHIP: free current-day list = Vanguard VTWO holdings as-of "
            "2026-05-31 (R2000 proxy, ~1 month stale vs run date)",
            "D4 EXCLUSIONS: REIT/security-type/ADR screens from FMP profile "
            "sector/industry/isAdr/isFund/isEtf flags, not GICS 60 / SIC 6798 codes",
            "D5 BIOTECH: ex-biotech cut keys on FMP industry containing 'biotech'",
            "D6 SPY: local SPY history starts 2016-01-04, so clean scored dates start "
            "2016 (not ~2015-01); n still well above the 600 floor",
            "D7 PANEL PERSISTENCE: panel intermediates live in the session scratchpad, "
            "not umbrella data/exp (hard rule: no writes outside scratchpad this run); "
            "input hashes recorded here instead",
            "D8 STALE BARS: no bar refresh performed (machine-landing actions are "
            "ask-first); resolved-outcome era ends 2026-05-08",
            "D9 VAL/QUAL: no admissible-timestamp small-cap fundamentals exist locally "
            "and the FMP Starter 5y cap bounds attainable coverage at ~40% < 60% floor "
            "=> INCONCLUSIVE-by-coverage, declared before any IC computation",
            "D10 SHARE CLASSES: secondary-class dedup via companyName + higher-ADV "
            "heuristic",
            "D11 LABEL CLIP: +/-0.5 label clip inherited from the C3/repo convention "
            "(not an explicit contract field)",
            "D12 SHUFFLE FLOOR: computed on stride-60 non-overlapping dates "
            "(sighunt-native geometry)",
        ],
        "reopening_conditions": [
            "R1 (required next step, not optional): Norgate trial/POC passes its 4 "
            "acceptance criteria (spec §6 item 1) => build the PRIMARY constituency-by-"
            "date panel and re-measure under THIS SAME spec and thresholds (no re-freeze); "
            "that run, not this one, renders M7's decision-grade verdict",
            "R2: a fundamentals source with >=60% admissible-timestamp coverage of the "
            "panel x date grid => VAL/QUAL families run (INCONCLUSIVE-by-coverage does "
            "not vote and re-running after fixing coverage is not a re-pitch, spec §5)",
            "R3: bar-store refresh extends the resolved-outcome era past 2026-05-08",
        ],
        "prospectivity_affirmation": (
            "No prior script in this repo's history has computed these factor x "
            "down-cap-panel combinations (every committed scan ran on the 104/142-name "
            "large-cap watchlist). Per spec §4 this is necessary but NOT sufficient; the "
            "sufficient freeze mechanism is the prereg contract merged at "
            f"{FREEZE_COMMIT} ({FREEZE_TIMESTAMP}), which this runner loaded and "
            "validated against at startup (0 deviations)."),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (out / "results.json").write_text(json.dumps(results, indent=1, default=str))
    print(f"[done] {time.time()-t0:.1f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
