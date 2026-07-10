#!/usr/bin/env python3
"""Deployment-policy research experiment — EXPLORATORY, TUNING SUBSET ONLY.

Runs 6 deployment-policy arms on the extended D6 stateful replay harness
(renquant-pipeline feat/replay-harness-d6-conventions, PR #180) against a
byte-copied sim_runs.db, restricted to the frozen TUNING subset
(d6_freeze_20260709.json: seed 20260709, tuning_frac 0.3, exclude-window
2026-06-23:2026-07-09).

READ-ONLY everywhere except the scratchpad. NOT decision evidence — this is
hypothesis generation on the tuning subset; nothing here touches the
evaluation subset.

Conventions (all arms identical): --stateful --tax --integer-shares
--enforce-caps, cost 5 bps/side, PV start $10,700, top-k = 8, per-name cap
12%, sector cap 35% (strategy sector map snapshot), fwd_1d horizon.

Sigma units: score_distribution.sigma is the model sigma on the fwd_60d
label horizon (median 0.123 ~= 25% annualized; a 12.3% *annualized*
single-name vol would be implausible). Annualization factor
sqrt(252/60) ~= 2.049 is applied for the vol-target arms and documented.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

SCRATCH = Path("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/"
               "2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad")
OUT_DIR = SCRATCH / "deploy_policy_results"
DB_COPY = SCRATCH / "sim_runs.db"
FREEZE = SCRATCH / "d6_freeze_20260709.json"
SECTOR_SNAP = OUT_DIR / "sector_map_snapshot.json"

sys.path.insert(0, str(SCRATCH / "wt-harness" / "src"))

from renquant_pipeline.kernel.portfolio_qp.allocator_replay import (  # noqa: E402
    ReplayConventions,
    paired_daily_returns,
    replay_all,
)
from renquant_pipeline.kernel.portfolio_qp.baseline_allocators import (  # noqa: E402
    AllocatorResult,
)
from renquant_pipeline.kernel.portfolio_qp.run_ab_replay import (  # noqa: E402
    constraint_fidelity_block,
    paired_comparison_metrics,
    regime_stratified_block,
    register_allocator,
    get_allocator,
    violation_report_block,
)
from renquant_pipeline.kernel.portfolio_qp.replay_significance import (  # noqa: E402
    compute_significance_verdicts,
    verdicts_to_dict,
)
from renquant_pipeline.kernel.portfolio_qp.wf_replay_loader import (  # noqa: E402
    load_replay_bars_from_sim_db,
)

# ── experiment constants (frozen by the task spec) ─────────────────────
TOP_K = 8
PER_NAME_CAP = 0.12
SECTOR_CAP = 0.35
COST_BPS_PER_SIDE = 5.0
PV_START = 10_700.0
GROSS_MAX = 0.95          # cash-reserve hard budget (loader cash_reserve=0.05)
KELLY_FRACTION = 0.30
RHO = 0.4                  # pairwise correlation approximation
SIGMA_ANNUALIZE = math.sqrt(252.0 / 60.0)  # fwd_60d-horizon sigma -> annual
HYSTERESIS_BAND = 0.05
VOL_TARGET_15 = 0.15
VOL_TARGET_12 = 0.12

# Side channels (per-arm per-bar diagnostics not carried by ReplayResult)
SIDE: dict[str, list] = {
    "kelly_raw_sum_uncapped": [],   # sum of 0.3*mu/sigma^2 over selected
    "kelly_raw_sum_capped": [],     # sum of min(., 0.12) — the "bridge" Sigma-w
    "govern_kelly_estar": [],
    "voltarget_ew_estar": [],
    "voltarget_kelly_estar": [],
    "voltarget_ew_12_estar": [],
    "voltarget_ew_sigma_pf": [],
}


def _top_k(mu: np.ndarray, k: int = TOP_K) -> list[int]:
    idx = [i for i in range(len(mu)) if np.isfinite(mu[i]) and mu[i] > 0.0]
    idx.sort(key=lambda i: -float(mu[i]))
    return idx[:k]


def _result(snap, target: np.ndarray, sel, status: str) -> AllocatorResult:
    return AllocatorResult(
        delta_w=target - snap.w_current,
        target_w=target,
        status=status,
        selected_indices=tuple(sel),
    )


def _budget_scale(target: np.ndarray) -> np.ndarray:
    """Hard cash-budget: scale DOWN so gross <= 0.95. Never scales up."""
    s = float(target.sum())
    if s > GROSS_MAX:
        target = target * (GROSS_MAX / s)
    return target


def _sigma_pf_ann(w_rel: np.ndarray, sigma_ann: np.ndarray) -> float:
    """sqrt(Sum w_i^2 s_i^2 + rho * Sum_{i!=j} w_i w_j s_i s_j), rho=0.4.

    Equivalent closed form: rho*(Sum w_i s_i)^2 + (1-rho)*Sum w_i^2 s_i^2.
    """
    ws = w_rel * sigma_ann
    var = RHO * float(ws.sum()) ** 2 + (1.0 - RHO) * float((ws ** 2).sum())
    return math.sqrt(max(var, 0.0))


# ── arm 1: ew_full ──────────────────────────────────────────────────────
def ew_full(snap, *, mu, sigma=None):
    sel = _top_k(np.asarray(mu, float))
    target = np.zeros(snap.n)
    if not sel:
        return _result(snap, target, (), "no_candidates")
    w = min(GROSS_MAX / len(sel), PER_NAME_CAP)
    for i in sel:
        target[i] = w
    return _result(snap, target, sel, "optimal")


# ── arm 2: kelly_raw ────────────────────────────────────────────────────
def kelly_raw_weights(snap, mu, sigma):
    """min(0.3*mu/sigma^2, 0.12) on top-k; also returns raw sums."""
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    sel = _top_k(mu)
    target = np.zeros(snap.n)
    sum_uncapped = 0.0
    for i in sel:
        s = max(float(sigma[i]), 1e-6)
        f = KELLY_FRACTION * float(mu[i]) / (s * s)
        sum_uncapped += max(f, 0.0)
        target[i] = min(max(f, 0.0), PER_NAME_CAP)
    return target, sel, sum_uncapped


def kelly_raw(snap, *, mu, sigma=None):
    target, sel, sum_uncapped = kelly_raw_weights(snap, mu, sigma)
    SIDE["kelly_raw_sum_uncapped"].append(sum_uncapped)
    SIDE["kelly_raw_sum_capped"].append(float(target.sum()))
    if not sel:
        return _result(snap, target, (), "no_candidates")
    # NO further scaling except the hard cash budget (Sigma-w <= 0.95).
    target = _budget_scale(target)
    return _result(snap, target, sel, "optimal")


# ── arm 3: govern_kelly (signal-driven governor, RFC draft design) ─────
class _GovernorState:
    def __init__(self):
        self.e_prev: float | None = None


def make_govern_kelly():
    st = _GovernorState()

    def govern_kelly(snap, *, mu, sigma=None):
        target, sel, _ = kelly_raw_weights(snap, mu, sigma)
        raw_sum = float(target.sum())
        if not sel or raw_sum <= 0.0:
            SIDE["govern_kelly_estar"].append(
                st.e_prev if st.e_prev is not None else 0.0)
            return _result(snap, np.zeros(snap.n), (), "no_candidates")
        e_target = min(raw_sum, GROSS_MAX)
        if st.e_prev is not None and abs(e_target - st.e_prev) <= HYSTERESIS_BAND:
            e_star = st.e_prev            # hold inside the hysteresis band
        else:
            e_star = e_target
        e_star = min(e_star, GROSS_MAX)
        st.e_prev = e_star
        SIDE["govern_kelly_estar"].append(e_star)
        target = target * (e_star / raw_sum)
        # re-cap per name (down-only) after a possible hysteresis scale-up
        target = np.minimum(target, PER_NAME_CAP)
        target = _budget_scale(target)
        return _result(snap, target, sel, "optimal")

    return govern_kelly


# ── arms 4/5/6: vol-target ──────────────────────────────────────────────
def make_voltarget(name: str, vol_target: float, kelly_relative: bool):
    def voltarget(snap, *, mu, sigma=None):
        mu_a = np.asarray(mu, float)
        sig_a = np.asarray(sigma, float)
        if kelly_relative:
            base, sel, _ = kelly_raw_weights(snap, mu_a, sig_a)
        else:
            sel = _top_k(mu_a)
            base = np.zeros(snap.n)
            for i in sel:
                base[i] = 1.0 / len(sel) if sel else 0.0
        tot = float(base.sum())
        if not sel or tot <= 0.0:
            SIDE[f"{name}_estar"].append(0.0)
            return _result(snap, np.zeros(snap.n), (), "no_candidates")
        w_rel = base / tot                       # relative weights, sum 1
        sigma_ann = sig_a * SIGMA_ANNUALIZE
        s_pf = _sigma_pf_ann(w_rel, sigma_ann)   # vol at full deployment
        if name == "voltarget_ew":
            SIDE["voltarget_ew_sigma_pf"].append(s_pf)
        e_star = min(vol_target / s_pf, GROSS_MAX) if s_pf > 1e-9 else GROSS_MAX
        SIDE[f"{name}_estar"].append(e_star)
        target = np.minimum(e_star * w_rel, PER_NAME_CAP)  # down-only cap
        target = _budget_scale(target)
        return _result(snap, target, sel, "optimal")

    return voltarget


# ── driver ──────────────────────────────────────────────────────────────
def main() -> int:
    t0 = time.time()
    freeze = json.loads(FREEZE.read_text())
    tuning_ids = set(freeze["horizons"]["fwd_1d"]["tuning"]["ids"])
    sector_snap = json.loads(SECTOR_SNAP.read_text())
    sector_map = sector_snap["sector_map"]
    max_per_sector = int(sector_snap["max_positions_per_sector"] or 0)

    bars = load_replay_bars_from_sim_db(
        DB_COPY, "2024-01-01", "2026-07-09",
        fwd_horizon_days=1,
        cost_per_trade_bps=COST_BPS_PER_SIDE,
        sector_map=sector_map,
        max_per_sector=max_per_sector,
    )
    bars = [b for b in bars if b.bar_date in tuning_ids]
    assert len(bars) == len(tuning_ids), (
        f"tuning bar mismatch: {len(bars)} bars vs {len(tuning_ids)} frozen ids")
    print(f"loaded {len(bars)} TUNING bars "
          f"({bars[0].bar_date}..{bars[-1].bar_date})")

    arms = {
        "ew_full": ew_full,
        "kelly_raw": kelly_raw,
        "govern_kelly": make_govern_kelly(),
        "voltarget_ew": make_voltarget("voltarget_ew", VOL_TARGET_15, False),
        "voltarget_kelly": make_voltarget("voltarget_kelly", VOL_TARGET_15, True),
        "voltarget_ew_12": make_voltarget("voltarget_ew_12", VOL_TARGET_12, False),
    }
    for nm, fn in arms.items():
        register_allocator(nm, fn)
    allocators = {nm: get_allocator(nm) for nm in arms}

    conv = ReplayConventions(
        stateful=True, tax=True, integer_shares=True, enforce_caps=True,
        per_name_cap=PER_NAME_CAP, sector_cap=SECTOR_CAP,
        sector_map=sector_map, initial_capital=PV_START,
    )

    results = replay_all(allocators, bars, conv)

    # cash-conservation sanity: prod(1+r) == PV_final / PV_start
    for nm, r in results.items():
        pv_final = r.final_state.portfolio_value
        lhs = float(np.prod(1.0 + np.asarray(r.daily_returns_net)))
        rhs = pv_final / PV_START
        assert abs(lhs - rhs) < 1e-9, f"{nm}: PV identity broken {lhs} vs {rhs}"

    # evidence blocks (mirrors run_replay, incumbent = ew_full)
    incumbent = "ew_full"
    per_allocator = {nm: r.to_dict() for nm, r in results.items()}
    arrays = paired_daily_returns(results)
    paired = {}
    for nm in arms:
        if nm == incumbent:
            continue
        paired[f"{incumbent}_vs_{nm}"] = paired_comparison_metrics(
            arrays[incumbent], arrays[nm], name_a=incumbent, name_b=nm)
    # direct HAC on (arm - ew_full), positive = arm beats the incumbent
    from renquant_common.metrics.hac_se import hac_t_stat
    hac_vs_incumbent = {}
    for nm in arms:
        if nm == incumbent:
            continue
        delta = arrays[nm] - arrays[incumbent]
        h = hac_t_stat(delta.tolist())
        hac_vs_incumbent[nm] = {
            "mean_delta_per_session": float(np.mean(delta)),
            "hac_t_stat": float(h["t_stat"]),
            "hac_p_value": float(h["p_value"]),
            "hac_lag": int(h["lag"]),
            "n": int(h["n"]),
        }

    significance = verdicts_to_dict(
        compute_significance_verdicts(results, pbo_n_slices=16))
    regime_block = regime_stratified_block(results, bars)
    violations = violation_report_block(results)
    fidelity = constraint_fidelity_block(bars)

    # own reduction ------------------------------------------------------
    def _med(x):
        return float(np.median(x)) if x else None

    summary = {}
    for nm, r in results.items():
        arr = np.asarray(r.daily_returns_net, float)
        summary[nm] = {
            "mean_deployed_fraction": float(np.mean(r.deployed_fraction)),
            "median_deployed_fraction": _med(r.deployed_fraction),
            "mean_E_executed": float(np.mean(r.executed_exposure)),
            "median_E_executed": _med(r.executed_exposure),
            "total_net_return": float(np.prod(1.0 + arr) - 1.0),
            "final_pv": float(r.final_state.portfolio_value),
            "sharpe_annual_net": r.sharpe_annual,
            "max_drawdown": r.max_drawdown,
            "total_tax_paid_usd": float(np.sum(r.tax_paid)),
            "total_cost_paid_usd": float(np.sum(r.cost_paid)),
            "mean_session_turnover": r.mean_turnover,
            "total_name_cap_breaches": int(np.sum(r.name_cap_breaches)),
            "total_sector_cap_breaches": int(np.sum(r.sector_cap_breaches)),
            "mean_integer_residual": float(np.mean(r.integer_residual)),
            "off_universe_liquidations": int(r.off_universe_liquidations),
            "no_candidates_sessions": int(r.fallback_to_no_candidates),
        }

    kr_capped = np.asarray(SIDE["kelly_raw_sum_capped"], float)
    kr_uncapped = np.asarray(SIDE["kelly_raw_sum_uncapped"], float)
    sigma_w_answer = {
        "note": ("kelly_raw bridge Sigma-w = Sum_i min(0.3*mu_i/sigma_i^2, 0.12) "
                 "over top-8 positive-mu names, BEFORE cash-budget scaling. "
                 "'uncapped' is Sum 0.3*mu/sigma^2 without the 12% name cap."),
        "n_sessions": int(kr_capped.size),
        "sigma_w_capped_mean": float(kr_capped.mean()),
        "sigma_w_capped_median": float(np.median(kr_capped)),
        "sigma_w_capped_pctl_5_25_75_95": [
            float(x) for x in np.percentile(kr_capped, [5, 25, 75, 95])],
        "sigma_w_uncapped_mean": float(kr_uncapped.mean()),
        "sigma_w_uncapped_median": float(np.median(kr_uncapped)),
        "share_sessions_name_cap_bound_ge_half":
            float(np.mean(kr_uncapped > 2.0 * kr_capped)),
        "share_sessions_gross_ge_0p90": float(np.mean(kr_capped >= 0.90)),
        "share_sessions_gross_le_0p60": float(np.mean(kr_capped <= 0.60)),
    }

    payload = {
        "label": "EXPLORATORY-HYPOTHESIS-GENERATION-TUNING-SUBSET-ONLY",
        "as_of_date": "2026-07-09",
        "protocol": "D6 conventions, tuning subset of d6_freeze_20260709.json",
        "freeze_record": str(FREEZE),
        "freeze_db_sha256": freeze["source_db"]["sha256"],
        "db_copy_path": str(DB_COPY),
        "n_bars": len(bars),
        "bar_dates_first_last": [bars[0].bar_date, bars[-1].bar_date],
        "fwd_horizon_days": 1,
        "conventions": conv.to_dict(),
        "arm_constants": {
            "top_k": TOP_K, "per_name_cap": PER_NAME_CAP,
            "sector_cap": SECTOR_CAP, "cost_bps_per_side": COST_BPS_PER_SIDE,
            "pv_start_usd": PV_START, "gross_max_cash_budget": GROSS_MAX,
            "kelly_fraction": KELLY_FRACTION, "rho_approx": RHO,
            "sigma_annualize_factor_sqrt_252_over_60": SIGMA_ANNUALIZE,
            "hysteresis_band": HYSTERESIS_BAND,
            "vol_target_annual": {"voltarget_ew": VOL_TARGET_15,
                                  "voltarget_kelly": VOL_TARGET_15,
                                  "voltarget_ew_12": VOL_TARGET_12},
        },
        "incumbent": incumbent,
        "summary_metrics": summary,
        "kelly_raw_sigma_w_distribution": sigma_w_answer,
        "per_allocator": per_allocator,
        "paired_comparisons_vs_ew_full": paired,
        "hac_arm_minus_ew_full": hac_vs_incumbent,
        "significance": significance,
        "regime_stratified": regime_block,
        "violation_report": violations,
        "constraint_fidelity": fidelity,
        "side_channels": {k: [float(x) for x in v] for k, v in SIDE.items()},
        "runtime_seconds": round(time.time() - t0, 2),
    }
    out = OUT_DIR / "evidence_tuning_fwd1d.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"evidence written: {out} ({time.time()-t0:.1f}s)")

    # compact console table
    cols = ["mean_deployed_fraction", "total_net_return", "sharpe_annual_net",
            "max_drawdown", "total_tax_paid_usd", "total_cost_paid_usd",
            "mean_session_turnover"]
    print("\narm            " + "  ".join(f"{c[:14]:>14}" for c in cols))
    for nm in arms:
        s = summary[nm]
        print(f"{nm:<14} " + "  ".join(
            f"{(s[c] if s[c] is not None else float('nan')):>14.4f}" for c in cols))
    print("\nHAC paired (arm - ew_full), positive = arm beats ew_full:")
    for nm, v in hac_vs_incumbent.items():
        print(f"  {nm:<16} mean_delta={v['mean_delta_per_session']:+.6f} "
              f"t={v['hac_t_stat']:+.2f} p={v['hac_p_value']:.3f} "
              f"(win_rate_arm={1-paired[f'{incumbent}_vs_{nm}']['win_rate_a_beats_b']:.3f})")
    print("\nkelly_raw Sigma-w (bridge, pre-budget): "
          f"mean={sigma_w_answer['sigma_w_capped_mean']:.3f} "
          f"median={sigma_w_answer['sigma_w_capped_median']:.3f} "
          f"pctl5/25/75/95={sigma_w_answer['sigma_w_capped_pctl_5_25_75_95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
