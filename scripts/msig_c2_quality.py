#!/usr/bin/env python
"""C2 — quality composite (FMP-full): the M-SIG frozen-spec measurement.

Measures the second-measured candidate of the merged M-SIG signal-stack spec
(doc/design/2026-07-02-m-sig-signal-stack-spec.md, PR #243 r4, thresholds FROZEN):

    C2 estimand: cross-sectional rank of a quality composite over
    {gross-profit/assets, total accruals, net share issuance},
    acceptedDate-lagged.  composite(i,t) = mean(zscore(GP/A),
    -zscore(accruals), -zscore(net_issuance)), equal-weight, frozen.

Frozen decision rule (spec sections 0/1.2/2a, Bonferroni k=3 one-sided 98.33% CI):
    GO   iff the UNCONDITIONAL daily placebo-clean fwd_60d IC series'
         moving-block-bootstrap 98.33% one-sided CI lower bound > 0.015 on ALL
         seeds {42,43,44} AND n >= 600 decision dates.
    KILL iff the 98.33% CI upper bound < 0.015 on all seeds.
    else INCONCLUSIVE.

Everything else (field-level leg derivations, PIT availability rule, staleness
cap, coverage-precondition metric, positive controls) was frozen BEFORE this
script ran — see doc/research/evidence/2026-07-03-c2/c2_frozen_addendum.json
(committed first, the M8 three-commit pattern).

Spec-governed PRECONDITION (section 1.2): C2's re-test is justified ONLY if the
FMP-full panel shows >=20% panel-coverage improvement over the free-tier
fundamentals_scan baseline.  This script MEASURES that precondition and stamps
its outcome; if unmet, the harness output is EXPLORATORY/NON-VOTING by the
spec's own rule (in addition to the substrate disqualifiers stamped below).

S-REL compliance (PR #265): positive controls are mandatory — PC-A (planted
decaying effect at 2x the bar; harness must return GO), PC-B (planted PERSISTENT
survivorship tilt; expected clean ~= 0, demonstrates the placebo's design
property), PC-C (within-date permuted composite; must not GO).  A NULL reading
of this harness is inadmissible unless PC-A passes.

READ-ONLY on all production data.  Writes ONLY into --out.
No git commands are executed against any primary checkout.

One-command reproduce (from the renquant-orchestrator repo root):

    /Users/renhao/git/github/RenQuant/.venv/bin/python \
        scripts/msig_c2_quality.py --out doc/research/evidence/2026-07-03-c2
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Shared M-SIG harness machinery: import the COMMITTED C3 implementation
# (single source — per-date Spearman IC, shifted-label placebo convention,
# gap-respecting moving-block bootstrap, production regime-chain replay).
# ---------------------------------------------------------------------------
_C3_PATH = Path(__file__).resolve().parent / "c3_residual_momentum.py"
_c3_spec = importlib.util.spec_from_file_location("c3_residual_momentum", _C3_PATH)
c3 = importlib.util.module_from_spec(_c3_spec)
_c3_spec.loader.exec_module(c3)

# ---------------------------------------------------------------------------
# Frozen constants (spec + committed addendum; do not tune)
# ---------------------------------------------------------------------------
IC_THRESHOLD = 0.015            # spec section 0/1.2: individual placebo-clean bar
BLOCK_VERDICT = 60              # spec shared default: block = fwd_60d horizon
BLOCK_SUPPORT = 20              # supporting horizon block = its own horizon
N_BOOT = 2000                   # spec shared default
SEEDS = (42, 43, 44)            # spec shared default, all reported
ALPHA_ONESIDED = 0.05 / 3       # spec section 2a: Bonferroni k=3 -> 98.33%
MIN_DECISION_DATES = 600        # spec shared default floor
MIN_NAMES = 30                  # house convention (C3)
HORIZON_VERDICT = 60
HORIZON_SUPPORT = 20
STALENESS_CAL_DAYS = 400        # frozen addendum: annual cadence + filing lag
COVERAGE_WINDOW = ("2017-07-01", "2026-07-01")  # frozen addendum, outcome-free
COVERAGE_BAR = 0.20             # spec section 1.2: >=20% improvement precondition
PC_KAPPA = 33.17                # frozen addendum: planted IC ~= 0.030 (2x bar)
PC_NOISE_SEED = 777
PC_PERM_SEED = 778
SHUFFLE_DIAG_SEED = 779
BLOCK_A1_SENS = 13              # labeled sensitivity only

DEFAULT_UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
DEFAULT_FUND = DEFAULT_UMBRELLA / "data" / "fmp_harvest_5y"
DEFAULT_OLD_FUND = DEFAULT_UMBRELLA / "data" / "fmp_harvest"


# ---------------------------------------------------------------------------
# Fundamentals loading + frozen field mapping
# ---------------------------------------------------------------------------
def _two_stage_join(left: pd.DataFrame, right: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """Join `cols` from right onto left per (symbol, date), falling back to
    (symbol, fiscalYear) for period-end labeling drift (frozen addendum;
    measured pre-freeze: ADI/MDT drift <= 6 days). Returns joined frame +
    join-provenance counts."""
    r1 = right[["symbol", "date"] + cols].drop_duplicates(["symbol", "date"], keep="last")
    m = left.merge(r1, on=["symbol", "date"], how="left", indicator=True)
    exact = int((m["_merge"] == "both").sum())
    m = m.drop(columns=["_merge"])
    need = m[cols[0]].isna()
    fallback = 0
    if need.any() and "fiscalYear" in left.columns and "fiscalYear" in right.columns:
        r2 = right[["symbol", "fiscalYear"] + cols].drop_duplicates(
            ["symbol", "fiscalYear"], keep="last"
        )
        fb = (
            m.loc[need, ["symbol", "fiscalYear"]]
            .merge(r2, on=["symbol", "fiscalYear"], how="left")
        )
        for c in cols:
            m.loc[need, c] = fb[c].to_numpy()
        fallback = int(m.loc[need, cols[0]].notna().sum())
    return m, {"joined_exact_symbol_date": exact, "joined_fallback_symbol_fiscalyear": fallback,
               "unjoined": int(m[cols[0]].isna().sum())}


def load_fund_new(fund_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Frozen field mapping (addendum): all three legs + PIT availability from
    the Starter-tier harvest.  Returns per-(symbol, period) observations."""
    inc = pd.read_parquet(fund_dir / "income_statement_annual.parquet")
    ra = pd.read_parquet(fund_dir / "ratios_annual.parquet")
    fg = pd.read_parquet(fund_dir / "financial_growth_annual.parquet")

    base = ra[["symbol", "date", "fiscalYear", "grossProfitMargin", "assetTurnover",
               "netProfitMargin", "operatingCashFlowSalesRatio"]].copy()
    base, join_ts = _two_stage_join(
        base, inc[["symbol", "date", "fiscalYear", "acceptedDate", "filingDate"]],
        ["acceptedDate", "filingDate"],
    )
    base, join_fg = _two_stage_join(
        base, fg[["symbol", "date", "fiscalYear", "weightedAverageSharesGrowth"]],
        ["weightedAverageSharesGrowth"],
    )

    at = base["assetTurnover"].where(base["assetTurnover"] > 0)
    obs = pd.DataFrame({
        "symbol": base["symbol"],
        "period_end": pd.to_datetime(base["date"]),
        "gp_a": base["grossProfitMargin"] * at,
        "accruals": (base["netProfitMargin"] - base["operatingCashFlowSalesRatio"]) * at,
        "net_issuance": base["weightedAverageSharesGrowth"],
        "acceptedDate": pd.to_datetime(base["acceptedDate"], errors="coerce"),
        "filingDate": pd.to_datetime(base["filingDate"], errors="coerce"),
    })
    stats = {"panel": "fmp_harvest_5y (Starter)", "rows": int(len(obs)),
             "join_timestamps": join_ts, "join_financial_growth": join_fg,
             "asset_turnover_nonpositive_rows": int((base["assetTurnover"] <= 0).sum())}
    return obs, stats


def load_fund_old(old_dir: Path, universe: list[str]) -> tuple[pd.DataFrame, dict]:
    """The free-tier fundamentals_scan baseline panel, SAME three legs
    (addendum-frozen derivation from its richer statement files)."""
    inc = pd.read_parquet(old_dir / "income_statement_291.parquet")
    bal = pd.read_parquet(old_dir / "balance_sheet_291.parquet")
    cf = pd.read_parquet(old_dir / "cash_flow_291.parquet")
    inc = inc[inc["symbol"].isin(universe)].copy()
    bal = bal[bal["symbol"].isin(universe)]
    cf = cf[cf["symbol"].isin(universe)]
    if "fiscalYear" not in inc.columns:
        inc["fiscalYear"] = pd.to_datetime(inc["date"]).dt.year
    for df in (bal, cf):
        if "fiscalYear" not in df.columns:
            df["fiscalYear"] = pd.to_datetime(df["date"]).dt.year

    base = inc[["symbol", "date", "fiscalYear", "grossProfit", "netIncome",
                "weightedAverageShsOut", "acceptedDate", "filingDate"]].copy()
    base, join_bal = _two_stage_join(base, bal, ["totalAssets"])
    base, join_cf = _two_stage_join(base, cf, ["operatingCashFlow"])

    base = base.sort_values(["symbol", "date"])
    prev_shs = base.groupby("symbol")["weightedAverageShsOut"].shift(1)
    ta = base["totalAssets"].where(base["totalAssets"] > 0)
    obs = pd.DataFrame({
        "symbol": base["symbol"],
        "period_end": pd.to_datetime(base["date"]),
        "gp_a": base["grossProfit"] / ta,
        "accruals": (base["netIncome"] - base["operatingCashFlow"]) / ta,
        "net_issuance": base["weightedAverageShsOut"] / prev_shs.where(prev_shs > 0) - 1.0,
        "acceptedDate": pd.to_datetime(base["acceptedDate"], errors="coerce"),
        "filingDate": pd.to_datetime(base["filingDate"], errors="coerce"),
    })
    stats = {"panel": "fmp_harvest (free tier, fundamentals_scan baseline)",
             "rows": int(len(obs)), "join_balance": join_bal, "join_cashflow": join_cf}
    return obs, stats


def resolve_availability(obs: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    """Frozen r4 admissible-mapping rule: acceptedDate -> filingDate -> (EDGAR
    join, unused here: both fields are fully populated) -> INADMISSIBLE.
    Availability = first trading day STRICTLY AFTER the timestamp's calendar
    date.  Anomaly guard: acceptedDate on/before period end -> INADMISSIBLE."""
    obs = obs.copy()
    ts = obs["acceptedDate"]
    field = pd.Series(np.where(ts.notna(), "acceptedDate", ""), index=obs.index)
    ts = ts.fillna(obs["filingDate"])
    field = field.mask((field == "") & obs["filingDate"].notna(), "filingDate")
    field = field.replace("", "INADMISSIBLE_no_timestamp")

    anom = ts.notna() & (ts.dt.normalize() <= obs["period_end"])
    field = field.mask(anom, "INADMISSIBLE_accepted_on_or_before_period_end")
    ts = ts.mask(anom)

    cal_vals = calendar.values
    avail = np.full(len(obs), np.datetime64("NaT"), dtype="datetime64[ns]")
    ok = ts.notna().to_numpy()
    idx = np.searchsorted(cal_vals, ts.dt.normalize().to_numpy()[ok], side="right")
    in_range = idx < len(cal_vals)
    take = np.where(in_range, idx, 0)
    vals = cal_vals[take]
    vals[~in_range] = np.datetime64("NaT")
    avail[ok] = vals
    obs["avail_day"] = pd.to_datetime(avail)
    obs["avail_field"] = field
    obs["timestamp_used"] = ts

    counts = field.value_counts().to_dict()
    lag = (ts.dt.normalize() - obs["period_end"]).dt.days.dropna()
    stats = {
        "avail_field_counts": {str(k): int(v) for k, v in counts.items()},
        "edgar_fallback_used": 0,
        "accept_lag_days_after_period_end": {
            "min": float(lag.min()), "p5": float(lag.quantile(0.05)),
            "median": float(lag.median()), "p95": float(lag.quantile(0.95)),
            "max": float(lag.max()),
        } if len(lag) else None,
        "n_anomalous_inadmissible": int(anom.sum()),
    }
    return obs, stats


def build_asof_panels(
    obs: pd.DataFrame, calendar: pd.DatetimeIndex, universe: list[str]
) -> dict[str, pd.DataFrame]:
    """Daily as-of panels for the three legs: latest admissible observation per
    name with avail_day <= t and (t - timestamp) <= STALENESS_CAL_DAYS; a name
    missing ANY leg at t is excluded (spec 1.2 missingness, applied later)."""
    legs = ("gp_a", "accruals", "net_issuance")
    panels = {leg: pd.DataFrame(index=calendar, columns=universe, dtype=float) for leg in legs}
    for sym, g in obs.groupby("symbol"):
        if sym not in universe:
            continue
        g = g[g["avail_day"].notna()].sort_values(["avail_day", "timestamp_used"])
        g = g.drop_duplicates("avail_day", keep="last")
        if g.empty:
            continue
        ts_used = g.set_index("avail_day")["timestamp_used"].reindex(calendar).ffill()
        stale = (pd.Series(calendar, index=calendar) - ts_used.dt.normalize()).dt.days > STALENESS_CAL_DAYS
        for leg in legs:
            s = g.set_index("avail_day")[leg].reindex(calendar).ffill()
            s[stale.to_numpy()] = np.nan
            panels[leg][sym] = s
    return panels


def composite_from_panels(panels: dict[str, pd.DataFrame], *, rank_z: bool = False) -> pd.DataFrame:
    """Spec 1.2 frozen composite: per-date cross-sectional plain z-scores,
    mean(z(GP/A), -z(accruals), -z(net_issuance)); all-three-legs names only;
    >= MIN_NAMES per date. rank_z=True is the labeled sensitivity variant."""
    gp, ac, ni = panels["gp_a"], panels["accruals"], panels["net_issuance"]
    valid = gp.notna() & ac.notna() & ni.notna()
    out = pd.DataFrame(index=gp.index, columns=gp.columns, dtype=float)
    for dt in gp.index:
        v = valid.loc[dt]
        names = v.index[v]
        if len(names) < MIN_NAMES:
            continue
        zs = []
        degenerate = False
        for frame, sign in ((gp, 1.0), (ac, -1.0), (ni, -1.0)):
            x = frame.loc[dt, names].astype(float)
            if rank_z:
                x = x.rank()
            sd = x.std(ddof=0)
            if not np.isfinite(sd) or sd <= 0:
                degenerate = True
                break
            zs.append(sign * (x - x.mean()) / sd)
        if degenerate:
            continue
        out.loc[dt, names] = (zs[0] + zs[1] + zs[2]) / 3.0
    return out


def coverage_series(panels: dict[str, pd.DataFrame], n_universe: int) -> pd.Series:
    valid = panels["gp_a"].notna() & panels["accruals"].notna() & panels["net_issuance"].notna()
    return valid.sum(axis=1) / float(n_universe)


# ---------------------------------------------------------------------------
# Gate evaluation on a per-date clean-IC series (unconditional — C2 is not
# regime-conditioned; per-regime cuts are mandatory diagnostics only)
# ---------------------------------------------------------------------------
def run_gate(per_date: pd.DataFrame, *, block: int, seeds=SEEDS, n_boot=N_BOOT) -> dict:
    df = per_date.dropna(subset=["clean_ic"]).sort_index()
    vals = df["clean_ic"].to_numpy(dtype=float)
    all_cell = np.ones(len(vals), dtype=bool)
    boots = {}
    for s in seeds:
        boots[str(s)] = c3.summarize_boot(
            c3.block_bootstrap_conditional_mean(vals, all_cell, block=block, n_boot=n_boot, seed=s)
        )
    seeds_ok = all(b is not None for b in boots.values())
    go = seeds_ok and all(b["lb_one_sided_9833"] > IC_THRESHOLD for b in boots.values())
    kill = seeds_ok and all(b["ub_one_sided_9833"] < IC_THRESHOLD for b in boots.values())
    floor = len(vals) >= MIN_DECISION_DATES
    verdict = "GO" if (go and floor) else ("KILL" if kill else "INCONCLUSIVE")
    return {
        "n_dates": int(len(vals)),
        "sample_floor_n600_met": bool(floor),
        "mean_real_ic": float(df["real_ic"].mean()) if len(df) else None,
        "mean_placebo_ic": float(df["placebo_ic"].mean()) if len(df) else None,
        "mean_clean_ic": float(vals.mean()) if len(vals) else None,
        "clean_hit_rate": float((vals > 0).mean()) if len(vals) else None,
        "bootstrap_by_seed": boots,
        "rule": "GO iff 98.33% one-sided LB > 0.015 all seeds AND n>=600; "
                "KILL iff 98.33% UB < 0.015 all seeds; else INCONCLUSIVE",
        "mechanical_rule_output": verdict,
    }


def regime_cells(per_date: pd.DataFrame, regime_by_date: pd.Series) -> dict:
    df = per_date.dropna(subset=["clean_ic"]).copy()
    df["regime"] = regime_by_date.reindex(df.index)
    out = {}
    for reg, g in df.groupby("regime", dropna=False):
        out[str(reg)] = {
            "n_dates": int(len(g)),
            "mean_real_ic": float(g["real_ic"].mean()),
            "mean_placebo_ic": float(g["placebo_ic"].mean()),
            "mean_clean_ic": float(g["clean_ic"].mean()),
            "clean_hit_rate": float((g["clean_ic"] > 0).mean()),
        }
    return out


# ---------------------------------------------------------------------------
# Positive controls (S-REL R2; designs frozen in the addendum)
# ---------------------------------------------------------------------------
def pc_scores(label60: pd.DataFrame, close: pd.DataFrame, spy_close: pd.Series,
              composite: pd.DataFrame) -> dict[str, pd.DataFrame]:
    mu = label60.mean(axis=1)
    sd = label60.std(axis=1).replace(0, np.nan)
    z_label = label60.sub(mu, axis=0).div(sd, axis=0)
    rng = np.random.default_rng(PC_NOISE_SEED)
    noise = rng.standard_normal(z_label.shape)
    pca = z_label + PC_KAPPA * noise
    pca = pca.where(label60.notna())

    rets = close.pct_change().sub(spy_close.pct_change(), axis=0)
    persistent = rets.mean(axis=0)  # full-sample mean excess return per name
    pcb = pd.DataFrame(
        np.tile(persistent.to_numpy(dtype=float), (len(close.index), 1)),
        index=close.index, columns=close.columns,
    ).where(close.notna())

    rng_p = np.random.default_rng(PC_PERM_SEED)
    pcc = composite.copy()
    for dt in pcc.index:
        row = pcc.loc[dt]
        mask = row.notna()
        if mask.sum() >= 2:
            vals = row[mask].to_numpy()
            pcc.loc[dt, mask.index[mask]] = rng_p.permutation(vals)
    return {"pc_a_planted_decaying": pca, "pc_b_planted_persistent": pcb,
            "pc_c_permuted_composite": pcc}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--umbrella", default=str(DEFAULT_UMBRELLA))
    ap.add_argument("--fund-dir", default=str(DEFAULT_FUND))
    ap.add_argument("--old-fund-dir", default=str(DEFAULT_OLD_FUND))
    ap.add_argument("--out", default="doc/research/evidence/2026-07-03-c2")
    ap.add_argument("--pinned-config", default=None)
    ap.add_argument("--gmm-artifact", default=None)
    args = ap.parse_args()

    umbrella = Path(args.umbrella)
    fund_dir = Path(args.fund_dir)
    old_fund_dir = Path(args.old_fund_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pinned_config = (
        Path(args.pinned_config) if args.pinned_config
        else umbrella / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
        / "configs" / "strategy_config.json"
    )
    gmm_artifact = (
        Path(args.gmm_artifact) if args.gmm_artifact
        else umbrella / "backtesting" / "renquant_104" / "artifacts" / "prod" / "spy-gmm-regime.json"
    )
    pipeline_src = umbrella / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src"
    common_src = umbrella / ".subrepo_runtime" / "repos" / "renquant-common" / "src"

    print("[1/9] fundamentals: frozen field mapping + PIT availability ...", flush=True)
    obs_new, stats_new = load_fund_new(fund_dir)
    universe = sorted(obs_new["symbol"].unique())

    print("[2/9] prices on the SPY calendar ...", flush=True)
    close, spy_close, hygiene = c3.load_close_matrix(umbrella, universe)
    calendar = close.index
    obs_new, avail_new = resolve_availability(obs_new, calendar)
    obs_old, stats_old = load_fund_old(old_fund_dir, universe)
    obs_old, avail_old = resolve_availability(obs_old, calendar)

    print("[3/9] as-of leg panels + composite ...", flush=True)
    panels_new = build_asof_panels(obs_new, calendar, universe)
    panels_old = build_asof_panels(obs_old, calendar, universe)
    composite = composite_from_panels(panels_new)
    composite_rankz = composite_from_panels(panels_new, rank_z=True)

    print("[4/9] coverage precondition (spec 1.2, >=20% bar) ...", flush=True)
    cov_new = coverage_series(panels_new, len(universe))
    cov_old = coverage_series(panels_old, len(universe))
    w0, w1 = pd.Timestamp(COVERAGE_WINDOW[0]), pd.Timestamp(COVERAGE_WINDOW[1])
    win = (calendar >= w0) & (calendar <= w1)
    mean_new, mean_old = float(cov_new[win].mean()), float(cov_old[win].mean())
    improvement = (mean_new - mean_old) / mean_old if mean_old > 0 else None
    precondition_met = improvement is not None and improvement >= COVERAGE_BAR
    coverage = {
        "metric": "mean over trading days %s..%s of (admissible all-3-leg names)/%d"
                  % (COVERAGE_WINDOW[0], COVERAGE_WINDOW[1], len(universe)),
        "starter_panel_mean_coverage": mean_new,
        "free_tier_baseline_mean_coverage": mean_old,
        "relative_improvement": improvement,
        "bar": COVERAGE_BAR,
        "precondition_met": bool(precondition_met),
        "monthly_means": {
            "starter": {str(k): float(v) for k, v in cov_new[win].resample("ME").mean().round(4).items()},
            "free_tier": {str(k): float(v) for k, v in cov_old[win].resample("ME").mean().round(4).items()},
        },
    }

    print("[5/9] labels + placebo + per-date Spearman ICs ...", flush=True)
    labels = {h: c3.fwd_excess(close, spy_close, h) for h in (HORIZON_VERDICT, HORIZON_SUPPORT)}
    placebos = {h: labels[h].shift(-h) for h in labels}
    ic60 = c3.per_date_ic(composite, labels[60], placebos[60])
    ic20 = c3.per_date_ic(composite, labels[20], placebos[20])

    print("[6/9] regime replay (production chain via committed C3 impl) ...", flush=True)
    spy_frame = pd.read_parquet(umbrella / "data" / "ohlcv" / "SPY" / "1d.parquet")
    if "date" in spy_frame.columns:
        spy_frame = spy_frame.set_index("date")
    spy_frame.index = pd.to_datetime(spy_frame.index)
    spy_frame = spy_frame.sort_index()
    regimes = c3.build_regime_series(
        ic60.index.union(ic20.index), spy_frame=spy_frame, pinned_config=pinned_config,
        gmm_artifact=gmm_artifact, pipeline_src=pipeline_src, common_src=common_src,
    )
    regime_by_date = regimes.set_index("date")["regime"]

    print("[7/9] frozen gate + per-regime cuts + sensitivities ...", flush=True)
    gate60 = run_gate(ic60, block=BLOCK_VERDICT)
    gate60["per_regime_cells_DIAGNOSTIC"] = regime_cells(ic60, regime_by_date)
    support20 = run_gate(ic20, block=BLOCK_SUPPORT)
    support20["per_regime_cells_DIAGNOSTIC"] = regime_cells(ic20, regime_by_date)

    # turnover / persistence diagnostic (spec 1.2: report, never gate)
    lag = 21
    autoc = []
    idx = composite.index
    for i in range(lag, len(idx)):
        a = composite.iloc[i]
        b = composite.iloc[i - lag]
        m = a.notna() & b.notna()
        if m.sum() >= MIN_NAMES:
            autoc.append(c3._spearman(a[m].to_numpy(), b[m].to_numpy()))
    turnover = {"mean_rank_autocorr_21d": float(np.nanmean(autoc)) if autoc else None,
                "n_pairs": len(autoc)}

    sens = {}
    ic60_rankz = c3.per_date_ic(composite_rankz, labels[60], placebos[60])
    sens["rank_z_composite_fwd60"] = run_gate(ic60_rankz, block=BLOCK_VERDICT, seeds=(42,))
    rng = np.random.default_rng(SHUFFLE_DIAG_SEED)
    shuffled = labels[60].copy()
    for dt in shuffled.index:
        row = shuffled.loc[dt]
        mask = row.notna()
        if mask.sum() >= 2:
            shuffled.loc[dt, mask.index[mask]] = rng.permutation(row[mask].to_numpy())
    ic60_shuffle = c3.per_date_ic(composite, labels[60], shuffled)
    sens["within_date_shuffle_placebo_fwd60_DIAGNOSTIC"] = {
        "mean_real_ic": float(ic60_shuffle["real_ic"].mean()),
        "mean_shuffle_placebo_ic": float(ic60_shuffle["placebo_ic"].mean()),
        "mean_clean_vs_shuffle": float(ic60_shuffle["clean_ic"].mean()),
        "note": "absolute-IC read; survivorship-inflated; never the gate",
    }
    for leg, sign in (("gp_a", 1.0), ("accruals", -1.0), ("net_issuance", -1.0)):
        leg_ic = c3.per_date_ic(sign * panels_new[leg], labels[60], placebos[60])
        sens[f"leg_{leg}_signed_fwd60"] = {
            "mean_real_ic": float(leg_ic["real_ic"].mean()),
            "mean_clean_ic": float(leg_ic["clean_ic"].mean()),
            "n_dates": int(leg_ic["clean_ic"].notna().sum()),
        }
    vals = ic60.dropna(subset=["clean_ic"])["clean_ic"].to_numpy(dtype=float)
    sens["block13_seed42_fwd60"] = c3.summarize_boot(
        c3.block_bootstrap_conditional_mean(
            vals, np.ones(len(vals), dtype=bool), block=BLOCK_A1_SENS, n_boot=N_BOOT, seed=42)
    )

    print("[8/9] positive controls (S-REL R2) ...", flush=True)
    pcs = pc_scores(labels[60], close, spy_close, composite)
    pc_out = {}
    for name, score in pcs.items():
        icp = c3.per_date_ic(score, labels[60], placebos[60])
        pc_out[name] = run_gate(icp, block=BLOCK_VERDICT)
    pc_a_pass = pc_out["pc_a_planted_decaying"]["mechanical_rule_output"] == "GO"
    pc_c_pass = pc_out["pc_c_permuted_composite"]["mechanical_rule_output"] != "GO"
    pc_b_clean = pc_out["pc_b_planted_persistent"]["mean_clean_ic"]
    pc_b_real = pc_out["pc_b_planted_persistent"]["mean_real_ic"]
    pc_summary = {
        "pc_a_harness_detects_planted_decaying_effect": bool(pc_a_pass),
        "pc_c_specificity_no_false_go": bool(pc_c_pass),
        "pc_b_persistent_tilt": {
            "real_ic": pc_b_real, "clean_ic": pc_b_clean,
            "demonstrates": "shifted-label placebo nets out persistent/survivorship "
                            "structure (real >> clean); harness is by design "
                            "insensitive to never-decaying tilts",
        },
        "null_admissibility_per_s_rel_r2": bool(pc_a_pass and pc_c_pass),
        "detail": pc_out,
    }

    print("[9/9] PIT spot-checks + evidence ...", flush=True)
    ra = pd.read_parquet(fund_dir / "ratios_annual.parquet")
    inc = pd.read_parquet(fund_dir / "income_statement_annual.parquet")
    spot = []
    for sym in ("AAPL", "NVDA", "MDT", "ADI", "JPM"):
        a = ra[ra.symbol == sym].merge(
            inc[inc.symbol == sym], on=["symbol", "fiscalYear"], suffixes=("_ra", "_inc"))
        if a.empty:
            continue
        gm_re = a["grossProfit"] / a["revenue"]
        npm_re = a["netIncome"] / a["revenue"]
        spot.append({
            "symbol": sym, "n_periods": int(len(a)),
            "max_abs_diff_grossProfitMargin_vs_income_recompute": float((a["grossProfitMargin"] - gm_re).abs().max()),
            "max_abs_diff_netProfitMargin_vs_income_recompute": float((a["netProfitMargin"] - npm_re).abs().max()),
            "max_period_end_label_drift_days": int(
                (pd.to_datetime(a["date_ra"]) - pd.to_datetime(a["date_inc"])).abs().dt.days.max()),
            "accepted_minus_period_end_days_median": float(
                (pd.to_datetime(a["acceptedDate"]) - pd.to_datetime(a["date_inc"])).dt.days.median()),
        })
    pit_spotcheck = {
        "same_filing_derivation_assumption": (
            "key_metrics/ratios/financial_growth rows for fiscal year y are FMP-derived "
            "from that year's filed statements; availability therefore equals the "
            "statement filing's acceptance. Spot-checked by recomputing derived ratios "
            "from the income statement per ticker below (agreement => same filing)."),
        "spot_checks": spot,
        "availability_stats_new": avail_new,
        "availability_stats_old_baseline": avail_old,
        "load_stats_new": stats_new,
        "load_stats_old_baseline": stats_old,
    }

    repo_root = Path(__file__).resolve().parents[1]
    head = c3.resolve_worktree_head(repo_root)
    try:
        porcelain = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, check=True).stdout
        tracked_dirty = [l for l in porcelain.splitlines() if not l.startswith("??")]
        dirty = {"tracked_modified": len(tracked_dirty), "untracked": len(porcelain.splitlines()) - len(tracked_dirty)}
    except Exception:
        dirty = None
    try:
        freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                capture_output=True, text=True, check=True).stdout
        env_lock_sha = hashlib.sha256("\n".join(sorted(freeze.splitlines())).encode()).hexdigest()
    except Exception:
        env_lock_sha = None

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "env_lock_sha256_pip_freeze": env_lock_sha,
        "code": {"worktree_head": head, "git_dirty": dirty,
                 "script": "scripts/msig_c2_quality.py",
                 "c3_machinery_sha256": c3.sha256_file(_C3_PATH)},
        "inputs_sha256": {
            **{f"fmp_harvest_5y/{n}": c3.sha256_file(fund_dir / n) for n in (
                "income_statement_annual.parquet", "ratios_annual.parquet",
                "financial_growth_annual.parquet", "key_metrics_annual.parquet",
                "harvest.manifest.json")},
            **{f"fmp_harvest/{n}": c3.sha256_file(old_fund_dir / n) for n in (
                "income_statement_291.parquet", "balance_sheet_291.parquet",
                "cash_flow_291.parquet")},
            "pinned_strategy_config": c3.sha256_file(pinned_config),
            "gmm_artifact": c3.sha256_file(gmm_artifact),
            "universe_tickers": hashlib.sha256(",".join(universe).encode()).hexdigest(),
            **c3.canonical_panel_sha256(close, spy_close),
        },
        "n_universe": len(universe),
        "benchmark": "SPY",
    }

    results = {
        "task": "C2 — quality composite (M-SIG frozen spec; second-measured channel)",
        "spec": "doc/design/2026-07-02-m-sig-signal-stack-spec.md (merged PR #243, r4) section 1.2 + 2a",
        "frozen_addendum": "doc/research/evidence/2026-07-03-c2/c2_frozen_addendum.json (committed before this run)",
        "adjudication_status": "EXPLORATORY_NON_VOTING",
        "adjudication_note": (
            "The mechanical rule output below does NOT stand as C2's formal "
            "GO/KILL/INCONCLUSIVE vote: (1) the spec's own coverage-delta "
            "precondition reads %s; (2) the harvest manifest classifies the data "
            "research_descriptive_only (restated current values, no revision identity) "
            "and states no confirmatory claim may rest on it; (3) survivorship-"
            "backfilled 134-name universe; (4) annual-only cadence vs the frozen "
            "quarterly estimand; (5) earliest-test date deviation (Q3 vs frozen Q4). "
            "C2 remains OPEN (the C3/#268 pattern)." % (
                "MET" if precondition_met else "NOT MET")),
        "frozen_thresholds": {
            "ic_threshold_placebo_clean": IC_THRESHOLD,
            "ci_level_one_sided": 1 - ALPHA_ONESIDED,
            "block": BLOCK_VERDICT, "n_boot": N_BOOT, "seeds": list(SEEDS),
            "min_decision_dates": MIN_DECISION_DATES,
            "coverage_improvement_bar": COVERAGE_BAR,
            "verdict_horizon": HORIZON_VERDICT,
        },
        "manifest": manifest,
        "hygiene": hygiene,
        "coverage_precondition": coverage,
        "gate_fwd60_unconditional": gate60,
        "supporting_fwd20": support20,
        "turnover_diagnostic": turnover,
        "positive_controls": pc_summary,
        "sensitivities_never_gate": sens,
        "regime_counts": regimes["regime"].value_counts(dropna=False).to_dict(),
    }

    (out_dir / "c2_results.json").write_text(
        json.dumps(results, indent=2, default=c3._json_default) + "\n")
    per_date_out = ic60.copy()
    per_date_out["regime"] = regime_by_date.reindex(per_date_out.index)
    per_date_out.reset_index().to_json(
        out_dir / "c2_per_date_ic_fwd60.json", orient="records", date_format="iso", indent=1)
    (out_dir / "c2_coverage.json").write_text(
        json.dumps(coverage, indent=2, default=c3._json_default) + "\n")
    (out_dir / "c2_pit_spotcheck.json").write_text(
        json.dumps(pit_spotcheck, indent=2, default=c3._json_default) + "\n")
    (out_dir / "c2_positive_control.json").write_text(
        json.dumps(pc_summary, indent=2, default=c3._json_default) + "\n")

    print(json.dumps({
        "ADJUDICATION_STATUS": results["adjudication_status"],
        "COVERAGE_PRECONDITION_MET": bool(precondition_met),
        "coverage_improvement": improvement,
        "MECHANICAL_RULE_OUTPUT": {
            "verdict": gate60["mechanical_rule_output"], "voting": False,
            "non_voting_reason": "see adjudication_note in c2_results.json"},
        "mean_real_ic_fwd60": gate60["mean_real_ic"],
        "mean_placebo_ic_fwd60": gate60["mean_placebo_ic"],
        "mean_clean_ic_fwd60": gate60["mean_clean_ic"],
        "n_dates": gate60["n_dates"],
        "gate_ci_seed42": gate60["bootstrap_by_seed"]["42"],
        "positive_controls": {
            "pc_a_detected": pc_summary["pc_a_harness_detects_planted_decaying_effect"],
            "pc_c_specific": pc_summary["pc_c_specificity_no_false_go"],
            "null_admissible": pc_summary["null_admissibility_per_s_rel_r2"]},
        "evidence_dir": str(out_dir),
    }, indent=2, default=c3._json_default), flush=True)


if __name__ == "__main__":
    main()
