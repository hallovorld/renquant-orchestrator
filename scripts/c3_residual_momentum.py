#!/usr/bin/env python
"""C3 — regime-conditioned RESIDUAL momentum: the M-SIG frozen-spec measurement.

Measures the first formally-voting candidate of the merged M-SIG signal-stack spec
(doc/design/2026-07-02-m-sig-signal-stack-spec.md, PR #243, thresholds FROZEN):

    C3 estimand: mom_12_1 (12-month-minus-1-month price momentum), orthogonalized
    (residualized) to sector + market beta, evaluated ONLY in the pooled
    BULL_CALM + BULL_VOLATILE regime cell, verdict on fwd_60d excess-vs-SPY,
    placebo-clean DIFFERENCES only (never absolute IC — the ~+0.04 embargo floor).

Frozen decision rule (spec section 1.3 + 2a, Bonferroni k=3 one-sided 98.33% CI):
    GO   iff (a) conditioned-cell placebo-clean IC 98.33% one-sided CI lower bound
             > 0.015, AND (b) the conditioned-minus-unconditioned placebo-clean
             difference's 98.33% one-sided CI lower bound > 0 — on ALL seeds
             {42, 43, 44} (all three reported, none cherry-picked).
    KILL iff the conditioned-cell 98.33% CI upper bound < 0.015 on all seeds,
             OR (dispatch-frozen rule) conditioned mean <= unconditioned mean.
    else MISS/INCONCLUSIVE — recorded, not re-argued.

Everything below the rule is measurement mechanics; every interpretation made is
stamped into the output JSON and documented in
doc/research/2026-07-02-c3-residual-momentum.md.

READ-ONLY on all production data. Writes ONLY into --out (committed evidence dir).
No git commands are executed against any primary checkout.

One-command reproduce (from the renquant-orchestrator repo root):

    /Users/renhao/git/github/RenQuant/.venv/bin/python \
        scripts/c3_residual_momentum.py \
        --out doc/research/evidence/2026-07-02-c3

(The umbrella venv is required: the production regime task chain is Python>=3.10.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Frozen constants (spec doc/design/2026-07-02-m-sig-signal-stack-spec.md)
# ---------------------------------------------------------------------------
IC_THRESHOLD = 0.015          # spec section 0 / 1.3: individual placebo-clean bar
BLOCK_PRIMARY = 60            # spec section 1.3 (r2/r3): block = fwd_60d label horizon
N_BOOT_PRIMARY = 2000         # spec shared default
SEEDS_PRIMARY = (42, 43, 44)  # spec shared default: all three run and reported
ALPHA_ONESIDED = 0.05 / 3     # spec section 2a: Bonferroni k=3 -> one-sided 98.33% CI
MIN_DECISION_DATES = 600      # spec shared default effective-sample floor
CONDITIONED_CELL = ("BULL_CALM", "BULL_VOLATILE")  # spec section 1.3: POOLED
HORIZON_VERDICT = 60          # verdict horizon (strategy horizon)
HORIZON_SUPPORT = 20          # supporting horizon (reported, never gates)
BETA_WINDOW_SPEC = 252        # spec section 1.3 frozen residualization fit window
LABEL_CLIP = 0.5              # repo convention (analyze_manifest_sanity_placebo)
MIN_NAMES = 30                # interpretation: >= ~2x the 17 cross-sectional params

# Dispatch-stated variant (recorded as SENSITIVITY, never the gate — the merged
# spec r2/r3 explicitly resolved block=13 -> block=60 and freezes beta at 252d):
BETA_WINDOW_DISPATCH = 120
BLOCK_DISPATCH = 13
N_BOOT_DISPATCH = 5000
SEED_DISPATCH = 42
STRIDE_DISPATCH = 21

DEFAULT_UMBRELLA = Path("/Users/renhao/git/github/RenQuant")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_default(obj):
    if isinstance(obj, (pd.Timestamp,)):
        return obj.date().isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# Data loading (read-only)
# ---------------------------------------------------------------------------
def load_universe(umbrella: Path) -> list[str]:
    panel = pd.read_parquet(
        umbrella / "data" / "transformer_v4_wl200_clean.parquet", columns=["ticker"]
    )
    return sorted(panel["ticker"].unique().tolist())


def load_close_matrix(umbrella: Path, tickers: list[str]) -> tuple[pd.DataFrame, pd.Series, dict]:
    """Wide close matrix on the SPY trading calendar + SPY close + hygiene stats.

    Interpretation (stamped): `close` in data/ohlcv/<T>/1d.parquet is
    split-adjusted (verified: NFLX 10:1 2025-11-17 shows no price seam) but NOT
    dividend-adjusted — momentum/labels are PRICE returns on both legs; the
    residual cross-sectional dividend-yield tilt is a stated limitation.
    """
    spy = pd.read_parquet(umbrella / "data" / "ohlcv" / "SPY" / "1d.parquet")
    if "date" in spy.columns:
        spy = spy.set_index("date")
    spy.index = pd.to_datetime(spy.index)
    spy = spy.sort_index()
    calendar = spy.index
    cols = {}
    missing: list[str] = []
    for t in tickers:
        p = umbrella / "data" / "ohlcv" / t / "1d.parquet"
        if not p.exists():
            missing.append(t)
            continue
        df = pd.read_parquet(p, columns=["close"])
        df.index = pd.to_datetime(df.index)
        cols[t] = df["close"].sort_index().reindex(calendar)
    close = pd.DataFrame(cols, index=calendar)
    rets = close.pct_change()
    big = (rets.abs() > 0.40).sum()
    hygiene = {
        "n_tickers_requested": len(tickers),
        "n_tickers_loaded": len(cols),
        "tickers_missing_ohlcv": missing,
        "calendar_start": calendar.min(),
        "calendar_end": calendar.max(),
        "n_calendar_days": int(len(calendar)),
        "abs_daily_return_gt_40pct_events": int(big.sum()),
        "abs_daily_return_gt_40pct_by_ticker_top10": big[big > 0]
        .sort_values(ascending=False)
        .head(10)
        .to_dict(),
    }
    return close, spy["close"].astype(float), hygiene


def load_sector_map(pinned_config: Path, tickers: list[str]) -> tuple[dict, list[str]]:
    cfg = json.loads(pinned_config.read_text())
    sm = dict(cfg.get("sector_map") or {})
    missing = [t for t in tickers if t not in sm]
    return {t: sm[t] for t in tickers if t in sm}, missing


# ---------------------------------------------------------------------------
# Regime reconstruction: the PRODUCTION task chain, replayed sequentially
# (mirrors renquant_backtesting.analysis.analyze_manifest_sanity_placebo::
#  build_regime_series, but sourced from the PINNED .subrepo_runtime pipeline
#  and the PINNED strategy config — see the memo for the fidelity statement).
# ---------------------------------------------------------------------------
def build_regime_series(
    dates,
    *,
    spy_frame: pd.DataFrame,
    pinned_config: Path,
    gmm_artifact: Path,
    pipeline_src: Path,
    common_src: Path,
) -> pd.DataFrame:
    for p in (str(pipeline_src), str(common_src)):
        if p not in sys.path:
            sys.path.insert(0, p)
    logging.getLogger("kernel.pipeline.regime").setLevel(logging.WARNING)
    logging.getLogger("kernel.regime").setLevel(logging.WARNING)
    from renquant_pipeline.kernel.regime import RegimeState  # noqa: PLC0415
    from renquant_pipeline.kernel.pipeline.task_regime import (  # noqa: PLC0415
        BEAROverrideTask,
        CUSUMTask,
        GMMTask,
        HurstTask,
        RegimeFinalizeTask,
    )

    config = json.loads(pinned_config.read_text())
    gmm = json.loads(gmm_artifact.read_text())
    tasks = [HurstTask(), CUSUMTask(), GMMTask(), BEAROverrideTask(), RegimeFinalizeTask()]
    ctx = SimpleNamespace(
        config=config,
        regime_state=RegimeState(),
        spy_returns=[],
        ohlcv={},
        gmm=gmm,
        regime_counts={},
        today=None,
        regime=None,
        confidence=None,
    )
    out = []
    for raw_d in sorted({pd.Timestamp(d).normalize() for d in dates}):
        hist = spy_frame.loc[spy_frame.index <= raw_d].copy()
        if len(hist) < 30:
            continue
        ctx.today = raw_d.date()
        ctx.ohlcv = {"SPY": hist}
        ctx.spy_returns = hist["close"].pct_change().dropna().values
        for task in tasks:
            task.run(ctx)
        evidence = dict(getattr(ctx, "_regime_evidence", {}) or {})
        out.append(
            {
                "date": raw_d,
                "regime": ctx.regime,
                "confidence": ctx.confidence,
                "source": evidence.get("source"),
                "hard_bear": evidence.get("hard_bear"),
                "in_transition": evidence.get("in_transition"),
            }
        )
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------
def mom_12_1(close: pd.DataFrame) -> pd.DataFrame:
    """ret(252d) excluding the last 21d: close[t-21]/close[t-252] - 1."""
    return close.shift(21) / close.shift(252) - 1.0


def rolling_beta(rets: pd.DataFrame, spy_rets: pd.Series, window: int) -> pd.DataFrame:
    """Rolling OLS slope of each name's daily return vs SPY (cov/var).

    Interpretation (stamped): min_periods = window // 2 — a name with less than
    half the window of paired history is EXCLUDED from that date's cross-section
    (no imputation), consistent with the spec's missingness stance.
    """
    minp = window // 2
    cov = rets.rolling(window, min_periods=minp).cov(spy_rets)
    var = spy_rets.rolling(window, min_periods=minp).var()
    return cov.div(var, axis=0)


def fwd_excess(close: pd.DataFrame, spy_close: pd.Series, horizon: int) -> pd.DataFrame:
    """fwd_h excess vs SPY, clipped to +/-0.5 (repo label convention)."""
    f_stock = close.shift(-horizon) / close - 1.0
    f_spy = spy_close.shift(-horizon) / spy_close - 1.0
    return f_stock.sub(f_spy, axis=0).clip(-LABEL_CLIP, LABEL_CLIP)


def residualize_scores(
    mom: pd.DataFrame, beta: pd.DataFrame, sector_map: dict
) -> pd.DataFrame:
    """Per-date: rank-z the momentum cross-section, then OLS-residualize on
    [const + sector dummies + market beta]. The residual is the C3 score.

    This is the stated resolution of the spec's section-1.3 residualization
    formula: per-date cross-sectional OLS where the sector factor is the
    per-date sector mean (dummies) and the market factor is the per-date premium
    on the trailing-window OLS beta.
    """
    sectors = pd.Series(sector_map)
    all_sec = sorted(sectors.unique())
    sec_codes = sectors.map({s: i for i, s in enumerate(all_sec)})
    out = pd.DataFrame(index=mom.index, columns=mom.columns, dtype=float)
    for dt in mom.index:
        m = mom.loc[dt]
        b = beta.loc[dt]
        valid = m.notna() & b.notna() & m.index.to_series().isin(sectors.index)
        names = m.index[valid]
        if len(names) < MIN_NAMES:
            continue
        y = m[names].rank().to_numpy(dtype=float)
        sd = y.std()
        if sd <= 0:
            continue
        y = (y - y.mean()) / sd  # rank-z
        codes = sec_codes[names].to_numpy()
        present = np.unique(codes)
        dummies = (codes[:, None] == present[None, 1:]).astype(float)  # drop first
        X = np.column_stack(
            [np.ones(len(names)), dummies, b[names].to_numpy(dtype=float)]
        )
        # np.errstate: on macOS Accelerate BLAS, matmul emits SPURIOUS
        # divide-by-zero/overflow/invalid RuntimeWarnings on perfectly
        # well-conditioned inputs (verified: cond(X)~22, all outputs finite,
        # |resid|<=3.1, resid orthogonal to beta at ~1e-15). The explicit
        # finiteness assertion below is the real guard.
        with np.errstate(all="ignore"):
            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ coef
        if not np.isfinite(resid).all():
            raise FloatingPointError(
                f"non-finite residual at {dt.date()} — refusing to score this date"
            )
        out.loc[dt, names] = resid
    return out


# ---------------------------------------------------------------------------
# Per-date cross-sectional Spearman IC + placebo
# ---------------------------------------------------------------------------
def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = math.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def per_date_ic(
    score: pd.DataFrame, label: pd.DataFrame, placebo: pd.DataFrame
) -> pd.DataFrame:
    """Per-date real IC, placebo IC (label shifted +horizon), and clean = real - placebo."""
    rows = []
    for dt in score.index:
        s = score.loc[dt].dropna()
        if len(s) < MIN_NAMES:
            continue
        rec = {"date": dt, "n_scored": int(len(s))}
        y = label.loc[dt, s.index].dropna()
        if len(y) >= MIN_NAMES:
            rec["real_ic"] = _spearman(s[y.index].to_numpy(), y.to_numpy())
            rec["n_real"] = int(len(y))
        yp = placebo.loc[dt, s.index].dropna()
        if len(yp) >= MIN_NAMES:
            rec["placebo_ic"] = _spearman(s[yp.index].to_numpy(), yp.to_numpy())
            rec["n_placebo"] = int(len(yp))
        if "real_ic" in rec and "placebo_ic" in rec:
            rec["clean_ic"] = rec["real_ic"] - rec["placebo_ic"]
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date")


# ---------------------------------------------------------------------------
# Moving-block bootstrap (mirrors scripts/research_panel_exit_predictiveness.py::
# _moving_block_bootstrap, extended to return the resample-mean distribution so
# both the two-sided 95% CI and the one-sided Bonferroni 98.33% bounds come from
# the SAME resamples).
# ---------------------------------------------------------------------------
def block_bootstrap_means(vals: np.ndarray, *, block: int, n_boot: int, seed: int):
    """NAIVE block bootstrap over a caller-pre-filtered array. NOT used by the
    main computation (round-2 review found this collapses calendar gaps when
    the caller pre-filters to an in-cell-only subseries before calling this —
    see block_bootstrap_conditional_mean for the fix). Kept only as the "old
    buggy behavior" comparator for tests/test_c3_residual_momentum.py; do not
    call this on a pre-filtered conditioned-cell array in new code."""
    a = np.asarray([v for v in vals if np.isfinite(v)], dtype=float)
    n = len(a)
    if n < 2 or block < 1 or n <= block:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    means = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[i] = a[idx].mean()
    return means


def block_bootstrap_diff(
    vals: np.ndarray, in_cell: np.ndarray, *, block: int, n_boot: int, seed: int
):
    """Paired difference bootstrap: resample date-blocks of the FULL series; per
    resample compute mean(in-cell dates) - mean(all dates). Preserves the
    pairing/overlap structure between the conditioned subset and the
    unconditional population (spec section 1.3 leg (b): 'computed via the paired
    daily difference series ... not two separate CIs compared by eye')."""
    mask_fin = np.isfinite(vals)
    a = vals[mask_fin]
    c = in_cell[mask_fin].astype(bool)
    n = len(a)
    if n < 2 or block < 1 or n <= block or c.sum() < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        av = a[idx]
        cv = c[idx]
        n_in = cv.sum()
        diffs[i] = (av[cv].mean() - av.mean()) if n_in >= 2 else np.nan
    diffs = diffs[np.isfinite(diffs)]
    return diffs if len(diffs) else None


def block_bootstrap_conditional_mean(
    vals: np.ndarray, in_cell: np.ndarray, *, block: int, n_boot: int, seed: int
):
    """Conditioned-cell mean bootstrap: resample date-BLOCKS OF THE FULL SERIES
    (never a pre-filtered in-cell-only array), then average only the in-cell
    values that fall within each drawn block. This is the SAME carried-mask
    pattern block_bootstrap_diff already uses correctly for the difference leg.

    Bug this replaces (round-2 review): the prior version filtered to
    `vals[in_cell]` BEFORE bootstrapping and drew 60-observation blocks from
    that filtered array. If two regime episodes are separated by a calendar
    gap (e.g. an intervening BEAR/CHOPPY stretch), the filtered array puts the
    last in-cell date of the first episode directly adjacent, in ARRAY
    POSITION, to the first in-cell date of the next episode — so a "60-day
    block" drawn near that seam actually splices together dates that may be
    months apart on the calendar, and no longer represents a genuine
    60-trading-day dependence block. Drawing blocks from the FULL dated
    series (as this function does) means a block can never span a regime-episode
    gap in a way that misrepresents contiguity — the block's underlying dates
    ARE contiguous trading days; it just may contain a mix of in-cell and
    off-cell dates, of which only the in-cell ones are averaged.
    """
    mask_fin = np.isfinite(vals)
    a = vals[mask_fin]
    c = in_cell[mask_fin].astype(bool)
    n = len(a)
    if n < 2 or block < 1 or n <= block or c.sum() < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block
    means = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        av = a[idx]
        cv = c[idx]
        n_in = cv.sum()
        means[i] = av[cv].mean() if n_in >= 2 else np.nan
    means = means[np.isfinite(means)]
    return means if len(means) else None


def effective_block_coverage(vals: np.ndarray, in_cell: np.ndarray, *, block: int) -> dict:
    """Diagnostic (not a bootstrap draw): partitions the FULL finite-value series
    into non-overlapping consecutive blocks of `block` trading days and reports
    how many of those blocks contain at least 2 in-cell observations (i.e. are
    usable for the conditioned-mean estimator) versus how many straddle a
    regime-episode gap so thinly that fewer than 2 in-cell dates fall inside
    them. Makes the true regime-episode structure the corrected bootstrap
    operates over legible, rather than only reporting a raw date count."""
    mask_fin = np.isfinite(vals)
    c = in_cell[mask_fin].astype(bool)
    n = len(c)
    if n < block:
        return {"n_full_blocks": 0, "n_blocks_with_ge2_in_cell": 0, "n_blocks_total": 0}
    n_full_blocks = n // block
    usable = 0
    for i in range(n_full_blocks):
        seg = c[i * block:(i + 1) * block]
        if seg.sum() >= 2:
            usable += 1
    return {
        "n_full_blocks": int(n_full_blocks),
        "n_blocks_with_ge2_in_cell": int(usable),
        "n_blocks_total": int(n_full_blocks),
    }


def summarize_boot(means: np.ndarray | None) -> dict | None:
    if means is None:
        return None
    lo95, hi95 = np.percentile(means, [2.5, 97.5])
    lb, ub = np.percentile(means, [100 * ALPHA_ONESIDED, 100 * (1 - ALPHA_ONESIDED)])
    return {
        "boot_se": float(means.std(ddof=1)),
        "ci95_two_sided": [float(lo95), float(hi95)],
        "lb_one_sided_9833": float(lb),
        "ub_one_sided_9833": float(ub),
        "n_boot_effective": int(len(means)),
    }


# ---------------------------------------------------------------------------
# Cell statistics + frozen-rule evaluation
# ---------------------------------------------------------------------------
def cell_stats(per_date: pd.DataFrame, regimes: pd.Series) -> dict:
    df = per_date.copy()
    df["regime"] = regimes.reindex(df.index)
    df["in_cell"] = df["regime"].isin(CONDITIONED_CELL)
    out = {}

    def _summ(g: pd.DataFrame) -> dict:
        clean = g["clean_ic"].dropna()
        return {
            "n_dates_clean": int(len(clean)),
            "n_dates_real": int(g["real_ic"].notna().sum()),
            "mean_real_ic": float(g["real_ic"].mean()) if g["real_ic"].notna().any() else None,
            "mean_placebo_ic": float(g["placebo_ic"].mean()) if g["placebo_ic"].notna().any() else None,
            "mean_clean_ic": float(clean.mean()) if len(clean) else None,
            "median_clean_ic": float(clean.median()) if len(clean) else None,
            "clean_hit_rate": float((clean > 0).mean()) if len(clean) else None,
        }

    out["unconditional"] = _summ(df)
    out["conditioned_BULL_CALM+BULL_VOLATILE"] = _summ(df[df["in_cell"]])
    for reg, g in df.groupby("regime", dropna=False):
        out[f"regime_{reg}"] = _summ(g)
    return out


def evaluate_verdict(cond_mean, uncond_mean, cond_boots, diff_boots, n_cond_dates) -> dict:
    """Both frozen readings, then the governing verdict.

    - spec reading (merged doc/design/2026-07-02-m-sig-signal-stack-spec.md
      sections 1.3+2a): GO iff conditioned 98.33% one-sided CI LB > 0.015 AND
      difference 98.33% one-sided CI LB > 0, on all seeds; KILL iff conditioned
      98.33% UB < 0.015 on all seeds; else INCONCLUSIVE.
    - dispatch reading (task-dispatch frozen thresholds): PASS iff conditioned
      placebo-clean mean >= 0.015 AND difference > 0 with CI excluding 0;
      KILL iff conditioned <= unconditioned (point estimate).
    Governing verdict: spec GO -> PASS; else any KILL trigger -> KILL;
    else MISS (recorded).
    """
    seeds_ok = bool(cond_boots) and all(b is not None for b in cond_boots.values())
    spec_go = spec_kill = False
    if seeds_ok and all(d is not None for d in diff_boots.values()):
        spec_go = all(
            b["lb_one_sided_9833"] > IC_THRESHOLD for b in cond_boots.values()
        ) and all(d["lb_one_sided_9833"] > 0 for d in diff_boots.values())
        spec_kill = all(
            b["ub_one_sided_9833"] < IC_THRESHOLD for b in cond_boots.values()
        )
    dispatch_kill = (
        cond_mean is not None and uncond_mean is not None and cond_mean <= uncond_mean
    )
    dispatch_pass = (
        cond_mean is not None
        and cond_mean >= IC_THRESHOLD
        and not dispatch_kill
        and all(d is not None and d["lb_one_sided_9833"] > 0 for d in diff_boots.values())
    )
    sample_floor_met = n_cond_dates >= MIN_DECISION_DATES
    if spec_go and dispatch_pass and sample_floor_met:
        verdict = "PASS"
    elif dispatch_kill or spec_kill:
        verdict = "KILL"
    else:
        verdict = "MISS"
    return {
        "spec_reading": {
            "go": bool(spec_go),
            "kill": bool(spec_kill),
            "rule": "98.33% one-sided CI LB(conditioned clean) > 0.015 AND CI LB(diff) > 0, all seeds",
        },
        "dispatch_reading": {
            "pass": bool(dispatch_pass),
            "kill_conditioned_le_unconditioned": bool(dispatch_kill),
            "rule": "mean(conditioned clean) >= 0.015 AND diff > 0 with CI excluding 0; KILL iff cond <= uncond",
        },
        "sample_floor_n600_met": bool(sample_floor_met),
        "n_conditioned_clean_dates": int(n_cond_dates),
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--umbrella", default=str(DEFAULT_UMBRELLA))
    ap.add_argument("--out", default="doc/research/evidence/2026-07-02-c3")
    ap.add_argument(
        "--pinned-config",
        default=None,
        help="pinned strategy_config.json (default: <umbrella>/.subrepo_runtime/"
        "repos/renquant-strategy-104/configs/strategy_config.json)",
    )
    ap.add_argument(
        "--gmm-artifact",
        default=None,
        help="production GMM regime artifact (default: <umbrella>/backtesting/"
        "renquant_104/artifacts/prod/spy-gmm-regime.json)",
    )
    args = ap.parse_args()

    umbrella = Path(args.umbrella)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pinned_config = (
        Path(args.pinned_config)
        if args.pinned_config
        else umbrella
        / ".subrepo_runtime"
        / "repos"
        / "renquant-strategy-104"
        / "configs"
        / "strategy_config.json"
    )
    gmm_artifact = (
        Path(args.gmm_artifact)
        if args.gmm_artifact
        else umbrella / "backtesting" / "renquant_104" / "artifacts" / "prod" / "spy-gmm-regime.json"
    )
    pipeline_src = umbrella / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src"
    common_src = umbrella / ".subrepo_runtime" / "repos" / "renquant-common" / "src"

    print("[1/7] loading universe + prices ...", flush=True)
    tickers = load_universe(umbrella)
    close, spy_close, hygiene = load_close_matrix(umbrella, tickers)
    sector_map, sector_missing = load_sector_map(pinned_config, tickers)
    if sector_missing:
        raise SystemExit(f"panel tickers missing from pinned sector_map: {sector_missing}")

    print("[2/7] signals: mom_12_1, rolling betas, labels ...", flush=True)
    rets = close.pct_change()
    spy_rets = spy_close.pct_change()
    mom = mom_12_1(close)
    beta_spec = rolling_beta(rets, spy_rets, BETA_WINDOW_SPEC)
    beta_dispatch = rolling_beta(rets, spy_rets, BETA_WINDOW_DISPATCH)
    labels = {h: fwd_excess(close, spy_close, h) for h in (HORIZON_VERDICT, HORIZON_SUPPORT)}
    placebos = {h: labels[h].shift(-h) for h in labels}  # label shifted +horizon

    print("[3/7] residualizing (spec beta=252 + dispatch beta=120) ...", flush=True)
    score_spec = residualize_scores(mom, beta_spec, sector_map)
    score_dispatch = residualize_scores(mom, beta_dispatch, sector_map)

    print("[4/7] per-date cross-sectional Spearman ICs ...", flush=True)
    ic60_spec = per_date_ic(score_spec, labels[60], placebos[60])
    ic20_spec = per_date_ic(score_spec, labels[20], placebos[20])
    ic60_dispatch = per_date_ic(score_dispatch, labels[60], placebos[60])

    print("[5/7] production regime chain replay (pinned pipeline+config) ...", flush=True)
    all_dates = ic60_spec.index.union(ic20_spec.index)
    spy_frame = pd.read_parquet(umbrella / "data" / "ohlcv" / "SPY" / "1d.parquet")
    if "date" in spy_frame.columns:
        spy_frame = spy_frame.set_index("date")
    spy_frame.index = pd.to_datetime(spy_frame.index)
    spy_frame = spy_frame.sort_index()
    regimes = build_regime_series(
        all_dates,
        spy_frame=spy_frame,
        pinned_config=pinned_config,
        gmm_artifact=gmm_artifact,
        pipeline_src=pipeline_src,
        common_src=common_src,
    )
    regime_by_date = regimes.set_index("date")["regime"]

    print("[6/7] cell stats + frozen-rule bootstraps ...", flush=True)

    def gating_block(per_date: pd.DataFrame, *, block: int, n_boot: int, seeds, stride: int = 1):
        df = per_date.dropna(subset=["clean_ic"]).sort_index()
        if stride > 1:
            df = df.iloc[::stride]
        reg = regime_by_date.reindex(df.index)
        in_cell = reg.isin(CONDITIONED_CELL).to_numpy()
        vals = df["clean_ic"].to_numpy(dtype=float)
        cond_vals = vals[in_cell]
        cond_boots, diff_boots = {}, {}
        for s in seeds:
            # Round-2 fix: block_bootstrap_conditional_mean draws blocks from the
            # FULL dated series with the regime mask carried through (never a
            # pre-filtered in-cell-only array) — a block can no longer splice
            # together two regime episodes separated by a calendar gap and
            # misrepresent them as one contiguous 60-trading-day window.
            cond_boots[str(s)] = summarize_boot(
                block_bootstrap_conditional_mean(vals, in_cell, block=block, n_boot=n_boot, seed=s)
            )
            diff_boots[str(s)] = summarize_boot(
                block_bootstrap_diff(vals, in_cell, block=block, n_boot=n_boot, seed=s)
            )
        return {
            "config": {
                "block": block,
                "n_boot": n_boot,
                "seeds": list(seeds),
                "stride_days": stride,
                "ci": "two-sided 95% + one-sided 98.33% (Bonferroni k=3, spec 2a)",
            },
            "n_dates_total": int(len(vals)),
            "n_dates_conditioned": int(in_cell.sum()),
            "effective_block_coverage": effective_block_coverage(vals, in_cell, block=block),
            "mean_clean_conditioned": float(cond_vals.mean()) if len(cond_vals) else None,
            "mean_clean_unconditional": float(vals.mean()) if len(vals) else None,
            "difference_conditioned_minus_unconditional": (
                float(cond_vals.mean() - vals.mean()) if len(cond_vals) else None
            ),
            "conditioned_bootstrap_by_seed": cond_boots,
            "difference_bootstrap_by_seed": diff_boots,
        }

    # --- GATING configuration (spec-frozen): beta252, daily cadence, block=60 ---
    gating = gating_block(
        ic60_spec, block=BLOCK_PRIMARY, n_boot=N_BOOT_PRIMARY, seeds=SEEDS_PRIMARY
    )
    gating["cells"] = cell_stats(ic60_spec, regime_by_date)
    gating["verdict"] = evaluate_verdict(
        gating["mean_clean_conditioned"],
        gating["mean_clean_unconditional"],
        gating["conditioned_bootstrap_by_seed"],
        gating["difference_bootstrap_by_seed"],
        gating["n_dates_conditioned"],
    )

    # --- Supporting horizon fwd_20d (block = its own horizon, 20) ---
    support = gating_block(ic20_spec, block=HORIZON_SUPPORT, n_boot=N_BOOT_PRIMARY, seeds=SEEDS_PRIMARY)
    support["cells"] = cell_stats(ic20_spec, regime_by_date)

    # --- Sensitivities (labeled; never gate) ---
    sens_dispatch_bundle = gating_block(
        ic60_dispatch,
        block=BLOCK_DISPATCH,
        n_boot=N_BOOT_DISPATCH,
        seeds=(SEED_DISPATCH,),
        stride=STRIDE_DISPATCH,
    )
    sens_block13_daily = gating_block(
        ic60_spec, block=BLOCK_DISPATCH, n_boot=N_BOOT_PRIMARY, seeds=(SEED_DISPATCH,)
    )
    sens_beta120_daily = gating_block(
        ic60_dispatch, block=BLOCK_PRIMARY, n_boot=N_BOOT_PRIMARY, seeds=SEEDS_PRIMARY
    )

    print("[7/7] writing evidence ...", flush=True)
    worktree_head = None
    try:
        repo_root = Path(__file__).resolve().parents[1]
        head = (repo_root / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = repo_root / ".git" / head[5:]
            worktree_head = ref.read_text().strip() if ref.exists() else head
        else:
            worktree_head = head
    except OSError:
        pass

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "worktree_head": worktree_head,
        "umbrella": str(umbrella),
        "inputs_sha256": {
            "pinned_strategy_config": sha256_file(pinned_config),
            "gmm_artifact": sha256_file(gmm_artifact),
            "task_regime_py": sha256_file(
                pipeline_src / "renquant_pipeline" / "kernel" / "pipeline" / "task_regime.py"
            ),
            "regime_py": sha256_file(pipeline_src / "renquant_pipeline" / "kernel" / "regime.py"),
            "universe_tickers": hashlib.sha256(",".join(tickers).encode()).hexdigest(),
        },
        "pinned_config_path": str(pinned_config),
        "gmm_artifact_path": str(gmm_artifact),
        "gmm_trained_date": json.loads(gmm_artifact.read_text()).get("trained_date"),
        "pipeline_src": str(pipeline_src),
        "common_src": str(common_src),
        "n_universe": len(tickers),
        "benchmark": "SPY",
    }

    interpretations = [
        "block=60 (NOT 13): the merged spec r2/r3 explicitly resolved the 'A1 convention "
        "block=13?' open question to block=60 = fwd_60d label horizon (spec section 1.3 and "
        "section 4 Q2); block=13 is reported as a labeled sensitivity only.",
        "beta window 252d (spec-frozen residualization fit window, section 1.3); the "
        "dispatch-stated 120d beta is a labeled sensitivity.",
        "decision-date cadence: DAILY (spec shared default, 'daily Spearman rank IC', with "
        "the n>=600 decision-date floor that stride-21 cannot meet); the dispatch-stated "
        "stride-21 grid is a labeled sensitivity.",
        "n_boot=2000 with seeds {42,43,44} all reported (spec shared default); the "
        "dispatch-stated 5000/single-seed is used for its sensitivity bundle.",
        "CI level: one-sided 98.33% (Bonferroni k=3, spec section 2a) for the frozen rule; "
        "two-sided 95% also reported for legibility.",
        "residualization: per-date cross-sectional OLS of rank-z mom_12_1 on [const + sector "
        "dummies + trailing-beta] — the stated resolution of the spec 1.3 formula (sector "
        "factor = per-date sector mean; market factor = per-date premium on trailing beta).",
        "labels: fwd_20d/fwd_60d PRICE-return excess vs SPY, clipped +/-0.5 (repo convention); "
        "verdict rendered on fwd_60d (strategy horizon), fwd_20d supporting only.",
        "placebo: label shifted +horizon within ticker (fwd_h at t+h); placebo-clean = "
        "real_ic - placebo_ic per date, defined only where both exist (the clean series ends "
        "~2*horizon before the last bar).",
        "conditioned cell: POOLED BULL_CALM+BULL_VOLATILE (spec 1.3 'Regime pooling'); "
        "per-regime cuts reported as diagnostics only.",
        "difference leg: paired — block-bootstrap resamples the FULL dated series and "
        "recomputes mean(in-cell) - mean(all) per resample (spec 1.3 leg (b)).",
        "conditioned-cell-only CI (round-2 fix): blocks are drawn over the FULL dated series "
        "with the regime mask carried through per date, then only the in-cell values within "
        "each drawn block are averaged — NOT drawn over a pre-filtered in-cell-only "
        "subseries, which would splice together regime episodes separated by a calendar gap "
        "as if they were contiguous trading days. effective_block_coverage reports how many "
        "of the full non-overlapping blocks actually contain >=2 in-cell observations.",
        f"min {MIN_NAMES} names per date for both the residualization (17 params) and each IC.",
        "regime labels: TODAY'S pinned production chain (pinned pipeline code + pinned "
        "strategy config incl. the 2026-06-11 false-BEAR fix + GMM artifact trained "
        "2026-05-22) replayed sequentially from a fresh RegimeState over the full SPY "
        "parquet — NOT the labels production actually emitted historically; the GMM is "
        "in-sample for dates before 2026-05-22.",
        "substrate: the S5/S8 pick-table/ledger (spec design rule 1) has no multi-year "
        "history; per the measurement dispatch this run uses the durable committed umbrella "
        "OHLCV parquets + the 142-name transformer panel universe instead — a stated "
        "deviation, with survivorship of the panel listed as a limitation.",
        "universe fixed at TODAY'S 142 panel tickers over the whole history (survivorship / "
        "selection bias: names are in the panel because they matter in 2026).",
        "prices split-adjusted, dividends NOT included (price returns both legs).",
    ]

    results = {
        "task": "C3 — regime-conditioned residual momentum (M-SIG frozen spec, first voting candidate)",
        "spec": "doc/design/2026-07-02-m-sig-signal-stack-spec.md (merged PR #243) section 1.3 + 2a",
        "adjudication_status": "UNADJUDICATED",
        "adjudication_note": (
            "gating_fwd60_spec_config.verdict.verdict is the MECHANICAL rule output computed "
            "on this run's substrate (production-chain-replayed regime labels + fixed-panel "
            "universe applied retrospectively over history) -- it does NOT stand as C3's "
            "formal GO/KILL/MISS vote, because that substrate is not point-in-time "
            "(see doc/research/2026-07-02-c3-residual-momentum.md sections 6-8 for the "
            "specific contamination mechanisms and the point-in-time-availability "
            "investigation). Treat this run as exploratory/sensitivity evidence only."
        ),
        "frozen_thresholds": {
            "ic_threshold_conditioned_clean": IC_THRESHOLD,
            "difference_must_exceed": 0.0,
            "ci_level_one_sided": 1 - ALPHA_ONESIDED,
            "min_decision_dates": MIN_DECISION_DATES,
            "conditioned_cell": list(CONDITIONED_CELL),
            "verdict_horizon": HORIZON_VERDICT,
        },
        "manifest": manifest,
        "interpretations": interpretations,
        "hygiene": hygiene,
        "regime_counts": regimes["regime"].value_counts(dropna=False).to_dict(),
        "gating_fwd60_spec_config": gating,
        "supporting_fwd20_spec_config": support,
        "sensitivities": {
            "dispatch_bundle_beta120_stride21_block13_boot5000_seed42": sens_dispatch_bundle,
            "block13_daily_spec_score_seed42": sens_block13_daily,
            "beta120_daily_block60": sens_beta120_daily,
        },
    }

    (out_dir / "c3_results.json").write_text(
        json.dumps(results, indent=2, default=_json_default) + "\n"
    )
    per_date_out = ic60_spec.copy()
    per_date_out["regime"] = regime_by_date.reindex(per_date_out.index)
    per_date_out.reset_index().to_json(
        out_dir / "c3_per_date_ic_fwd60.json", orient="records", date_format="iso", indent=1
    )
    regimes.to_json(out_dir / "c3_regime_series.json", orient="records", date_format="iso", indent=1)

    v = gating["verdict"]
    print(json.dumps({
        "VERDICT": v["verdict"],
        "conditioned_mean_clean": gating["mean_clean_conditioned"],
        "unconditional_mean_clean": gating["mean_clean_unconditional"],
        "difference": gating["difference_conditioned_minus_unconditional"],
        "n_conditioned_dates": gating["n_dates_conditioned"],
        "conditioned_ci_seed42": gating["conditioned_bootstrap_by_seed"]["42"],
        "difference_ci_seed42": gating["difference_bootstrap_by_seed"]["42"],
        "evidence_dir": str(out_dir),
    }, indent=2, default=_json_default), flush=True)


if __name__ == "__main__":
    main()
