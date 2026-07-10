#!/usr/bin/env python3
"""Cap-grid replay experiment — EXPLORATORY / TUNING SUBSET ONLY.

[EXPLORATORY / TUNING SUBSET — does not select anything, does not clear
any gate.]

Breadth x cap grid at regime-ceiling deployment on the D6 stateful replay
harness (renquant-pipeline feat/replay-harness-d6-conventions, commit
6ac718f, worktree scratchpad/wt-harness — harness code untouched), against
the byte-copied sim_runs.db, restricted to the frozen TUNING subset of
d6_freeze_20260709.json (149 sessions; the 348-session evaluation subset is
RETIRED and never touched).

ARMS (6): per-name cap in {12%, 20%, 25%} x weights in {equal_weight,
capped_kelly}. Deployment target = the regime CEILING, gross 0.95 always.
Regime labels DO exist on most bars (BULL_CALM dominates the tuning window)
but the grid intentionally fixes the ceiling at 0.95 for every session:
(a) the task spec pins it ("regime labels may not be on bars"), and
(b) a fixed ceiling isolates the cap x breadth effect from regime-scaling.

Weight rules (per arm cap C):
  equal_weight : sel = top-8 positive-mu; w_i = min(0.95/n_sel, C).
                 Gross = min(0.95, n_sel*C) — the ceiling by construction.
  capped_kelly : w_i = min(max(0.3*mu_i/sigma_i^2, 0), C) on the same
                 top-8; down-only cash-budget scale to 0.95. LITERAL task
                 formula, matching the prior experiment's kelly_raw arm
                 (cap12_ck == prior kelly_raw; cap12_ew == prior ew_full —
                 reproduction cross-check). NO scale-up to the ceiling:
                 raw 30%-Kelly on these mu/sigma wants ~2.4x leverage, so
                 min(f, C) saturates at C almost everywhere and gross is
                 ~min(0.95, n_sel*C) anyway; the realized shortfall vs the
                 ceiling is measured and reported per arm.

Conventions (identical across arms except per_name_cap): --stateful --tax
--integer-shares --enforce-caps, sector cap 35% (snapshot), 5 bps/side,
PV $10,700, top-k 8, fwd_1d horizon. Each cap group runs with its own
ReplayConventions(per_name_cap=C); bars are identical across arms so
paired contrasts stay valid.

Realized per-name executed weights are captured via a driver-side wrap of
allocator_replay._record_family_violations (called once per bar in the
stateful engine with the post-projection, post-integer executed_w) — no
harness code modified.
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
OUT_DIR = SCRATCH / "cap_grid_results"
DB_COPY = SCRATCH / "sim_runs.db"
FREEZE = SCRATCH / "deploy_policy_results" / "d6_freeze_20260709.json"
SECTOR_SNAP = SCRATCH / "deploy_policy_results" / "sector_map_snapshot.json"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRATCH / "wt-harness" / "src"))
sys.path.insert(0, "/Users/renhao/git/github/renquant-common/src")  # read-only

from renquant_pipeline.kernel.portfolio_qp import allocator_replay  # noqa: E402
from renquant_pipeline.kernel.portfolio_qp.allocator_replay import (  # noqa: E402
    ReplayConventions,
    paired_daily_returns,
    replay_all,
)
from renquant_pipeline.kernel.portfolio_qp.baseline_allocators import (  # noqa: E402
    AllocatorResult,
)
from renquant_pipeline.kernel.portfolio_qp.wf_replay_loader import (  # noqa: E402
    load_replay_bars_from_sim_db,
)
from renquant_common.metrics.hac_se import hac_t_stat  # noqa: E402

# ── experiment constants ────────────────────────────────────────────────
TOP_K = 8
CAPS = (0.12, 0.20, 0.25)
SECTOR_CAP = 0.35
COST_BPS_PER_SIDE = 5.0
PV_START = 10_700.0
GROSS_MAX = 0.95            # regime CEILING, fixed for every session
KELLY_FRACTION = 0.30
INCUMBENT = "cap12_ew"

# Side channels: per-arm per-bar diagnostics
BREADTH: dict[str, list[int]] = {}          # n_sel per session
TARGET_GROSS: dict[str, list[float]] = {}   # allocator target gross pre-exec
EXEC_W: dict[str, list[np.ndarray]] = {}    # realized executed weights


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


def make_ew(name: str, cap: float):
    def ew(snap, *, mu, sigma=None):
        sel = _top_k(np.asarray(mu, float))
        BREADTH[name].append(len(sel))
        target = np.zeros(snap.n)
        if not sel:
            TARGET_GROSS[name].append(0.0)
            return _result(snap, target, (), "no_candidates")
        w = min(GROSS_MAX / len(sel), cap)
        for i in sel:
            target[i] = w
        TARGET_GROSS[name].append(float(target.sum()))
        return _result(snap, target, sel, "optimal")
    return ew


def make_ck(name: str, cap: float):
    def ck(snap, *, mu, sigma=None):
        mu_a = np.asarray(mu, float)
        sig_a = np.asarray(sigma, float)
        sel = _top_k(mu_a)
        BREADTH[name].append(len(sel))
        target = np.zeros(snap.n)
        if not sel:
            TARGET_GROSS[name].append(0.0)
            return _result(snap, target, (), "no_candidates")
        for i in sel:
            s = max(float(sig_a[i]), 1e-6)
            f = KELLY_FRACTION * float(mu_a[i]) / (s * s)
            target[i] = min(max(f, 0.0), cap)
        tot = float(target.sum())
        if tot > GROSS_MAX:                      # down-only cash budget
            target = target * (GROSS_MAX / tot)
        TARGET_GROSS[name].append(float(target.sum()))
        return _result(snap, target, sel, "optimal")
    return ck


# ── executed-weight capture (driver-side wrap; harness untouched) ──────
_ORIG_RECORD = allocator_replay._record_family_violations


def _capturing_record(res, snap, target_w, delta_w):
    EXEC_W[res.name].append(np.asarray(target_w, float).copy())
    return _ORIG_RECORD(res, snap, target_w, delta_w)


def main() -> int:
    t0 = time.time()
    freeze = json.loads(FREEZE.read_text())
    assert freeze["source_db"]["sha256"] == (
        "82084a6d026a1a8db39c92d19ee119f7f79c96e82a4dade91404d93848772a88")
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
        f"tuning bar mismatch: {len(bars)} vs {len(tuning_ids)}")
    regime_counts: dict[str, int] = {}
    for b in bars:
        regime_counts[str(b.regime)] = regime_counts.get(str(b.regime), 0) + 1
    print(f"loaded {len(bars)} TUNING bars "
          f"({bars[0].bar_date}..{bars[-1].bar_date}); regimes={regime_counts}")

    # arm construction: 3 cap groups x {ew, ck}
    arm_defs: dict[str, tuple[float, str]] = {}
    for cap in CAPS:
        tag = f"cap{int(round(cap * 100))}"
        arm_defs[f"{tag}_ew"] = (cap, "ew")
        arm_defs[f"{tag}_ck"] = (cap, "ck")
    for nm in arm_defs:
        BREADTH[nm] = []
        TARGET_GROSS[nm] = []
        EXEC_W[nm] = []

    allocator_replay._record_family_violations = _capturing_record
    try:
        results = {}
        for cap in CAPS:
            tag = f"cap{int(round(cap * 100))}"
            allocators = {
                f"{tag}_ew": make_ew(f"{tag}_ew", cap),
                f"{tag}_ck": make_ck(f"{tag}_ck", cap),
            }
            conv = ReplayConventions(
                stateful=True, tax=True, integer_shares=True,
                enforce_caps=True, per_name_cap=cap, sector_cap=SECTOR_CAP,
                sector_map=sector_map, initial_capital=PV_START,
            )
            results.update(replay_all(allocators, bars, conv))
    finally:
        allocator_replay._record_family_violations = _ORIG_RECORD

    # sanity: PV identity + capture counts
    for nm, r in results.items():
        pv_final = r.final_state.portfolio_value
        lhs = float(np.prod(1.0 + np.asarray(r.daily_returns_net)))
        assert abs(lhs - pv_final / PV_START) < 1e-9, f"{nm}: PV identity broken"
        assert len(EXEC_W[nm]) == len(bars), f"{nm}: exec_w capture mismatch"
        assert len(BREADTH[nm]) == len(bars), f"{nm}: breadth capture mismatch"

    arrays = paired_daily_returns(results)

    # ── per-arm reductions ──────────────────────────────────────────────
    summary: dict[str, dict] = {}
    ceiling_block: dict[str, dict] = {}
    concentration: dict[str, dict] = {}
    for nm, r in results.items():
        cap = arm_defs[nm][0]
        arr = np.asarray(r.daily_returns_net, float)
        e_exec = np.asarray(r.executed_exposure, float)
        breadth = np.asarray(BREADTH[nm], int)

        # concentration proxy: per session, min over HELD names of w_i*r_i
        worst = np.zeros(len(bars))
        max_w = 0.0
        for t, (b, w) in enumerate(zip(bars, EXEC_W[nm])):
            held = w > 1e-9
            if held.any():
                contrib = w[held] * np.asarray(b.fwd_return, float)[held]
                worst[t] = float(contrib.min())
                max_w = max(max_w, float(w.max()))
        concentration[nm] = {
            "worst_name_contrib_p1": float(np.percentile(worst, 1)),
            "worst_name_contrib_p5": float(np.percentile(worst, 5)),
            "worst_name_contrib_median": float(np.median(worst)),
            "worst_name_contrib_min": float(worst.min()),
            "max_realized_single_name_weight": max_w,
            "worst_name_contrib_series": [float(x) for x in worst],
        }

        # deployment ceiling actually hit
        theo_ceiling = np.minimum(GROSS_MAX, breadth * cap)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(theo_ceiling > 0, e_exec / theo_ceiling, 0.0)
        ceiling_block[nm] = {
            "theoretical_ceiling_mean": float(theo_ceiling.mean()),
            "exec_over_ceiling_ratio_mean": float(ratio.mean()),
            "exec_over_ceiling_ratio_median": float(np.median(ratio)),
            "share_sessions_E_exec_ge_0p80": float(np.mean(e_exec >= 0.80)),
            "share_sessions_E_exec_ge_0p90": float(np.mean(e_exec >= 0.90)),
            "share_sessions_ceiling_binds_breadth": float(
                np.mean(breadth * cap < GROSS_MAX)),
            "breadth_needed_for_0p90": int(math.ceil(0.90 / cap)),
            "share_sessions_breadth_ge_needed": float(
                np.mean(breadth >= math.ceil(0.90 / cap))),
            "target_gross_mean": float(np.mean(TARGET_GROSS[nm])),
            "target_gross_shortfall_vs_ceiling_mean": float(
                np.mean(theo_ceiling - np.asarray(TARGET_GROSS[nm]))),
        }

        summary[nm] = {
            "cap": cap,
            "scheme": arm_defs[nm][1],
            "mean_E_executed": float(e_exec.mean()),
            "median_E_executed": float(np.median(e_exec)),
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

    # ── HAC paired vs cap12_ew ─────────────────────────────────────────
    hac_vs_incumbent: dict[str, dict] = {}
    for nm in results:
        if nm == INCUMBENT:
            continue
        delta = arrays[nm] - arrays[INCUMBENT]
        h = hac_t_stat(delta.tolist())
        hac_vs_incumbent[nm] = {
            "mean_delta_per_session": float(np.mean(delta)),
            "hac_t_stat": float(h["t_stat"]),
            "hac_p_value": float(h["p_value"]),
            "hac_lag": int(h["lag"]),
            "n": int(h["n"]),
            "win_rate_arm_beats_incumbent": float(np.mean(delta > 0)),
        }

    # breadth distribution (identical across arms by construction; assert)
    b0 = BREADTH[INCUMBENT]
    for nm in results:
        assert BREADTH[nm] == b0, f"{nm}: breadth differs from incumbent"
    breadth_arr = np.asarray(b0, int)
    breadth_block = {
        "median": float(np.median(breadth_arr)),
        "mean": float(breadth_arr.mean()),
        "min": int(breadth_arr.min()),
        "max": int(breadth_arr.max()),
        "share_ge_4": float(np.mean(breadth_arr >= 4)),
        "share_ge_5": float(np.mean(breadth_arr >= 5)),
        "share_ge_8": float(np.mean(breadth_arr >= 8)),
        "histogram": {str(k): int(np.sum(breadth_arr == k))
                      for k in sorted(set(b0))},
    }

    payload = {
        "label": ("EXPLORATORY / TUNING SUBSET — does not select anything, "
                  "does not clear any gate"),
        "as_of_date": "2026-07-10",
        "protocol": "D6 conventions, cap-grid at fixed 0.95 gross ceiling, "
                    "tuning subset of d6_freeze_20260709.json",
        "freeze_record": str(FREEZE),
        "freeze_db_sha256": freeze["source_db"]["sha256"],
        "db_copy_path": str(DB_COPY),
        "harness": "renquant-pipeline feat/replay-harness-d6-conventions "
                   "commit 6ac718f (scratchpad/wt-harness, untouched)",
        "n_bars": len(bars),
        "bar_dates_first_last": [bars[0].bar_date, bars[-1].bar_date],
        "fwd_horizon_days": 1,
        "regime_counts_on_bars": regime_counts,
        "gross_ceiling_note": (
            "target gross fixed at 0.95 for ALL sessions (regime ceiling); "
            "regime labels are present on bars but intentionally unused for "
            "scaling per the task spec"),
        "arm_constants": {
            "top_k": TOP_K, "caps": list(CAPS), "sector_cap": SECTOR_CAP,
            "cost_bps_per_side": COST_BPS_PER_SIDE, "pv_start_usd": PV_START,
            "gross_ceiling": GROSS_MAX, "kelly_fraction": KELLY_FRACTION,
            "capped_kelly_rule": "min(max(0.3*mu/sigma^2,0), cap), down-only "
                                 "budget scale to 0.95; NO scale-up (literal "
                                 "spec formula; saturation makes it ~ceiling)",
        },
        "incumbent": INCUMBENT,
        "summary_metrics": summary,
        "deployment_ceiling": ceiling_block,
        "concentration_tail": concentration,
        "hac_arm_minus_cap12_ew": hac_vs_incumbent,
        "breadth_distribution": breadth_block,
        "per_allocator": {nm: r.to_dict() for nm, r in results.items()},
        "side_channels": {
            "breadth_per_session": b0,
            "target_gross": {k: [float(x) for x in v]
                             for k, v in TARGET_GROSS.items()},
        },
        "runtime_seconds": round(time.time() - t0, 2),
    }
    out = OUT_DIR / "evidence_cap_grid_tuning_fwd1d.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"evidence written: {out} ({time.time()-t0:.1f}s)")

    # compact console table
    cols = ["mean_E_executed", "median_E_executed", "total_net_return",
            "sharpe_annual_net", "max_drawdown", "total_tax_paid_usd",
            "total_cost_paid_usd", "mean_session_turnover"]
    print("\narm        " + "  ".join(f"{c[:13]:>13}" for c in cols)
          + "  max_w   p1_worst   p5_worst")
    for nm in summary:
        s = summary[nm]
        c = concentration[nm]
        print(f"{nm:<10} " + "  ".join(
            f"{(s[k] if s[k] is not None else float('nan')):>13.4f}"
            for k in cols)
            + f"  {c['max_realized_single_name_weight']:.4f}"
            + f"  {c['worst_name_contrib_p1']:+.5f}"
            + f"  {c['worst_name_contrib_p5']:+.5f}")
    print("\nHAC paired (arm - cap12_ew), positive = arm beats cap12_ew:")
    for nm, v in hac_vs_incumbent.items():
        print(f"  {nm:<10} mean_delta={v['mean_delta_per_session']:+.6f} "
              f"t={v['hac_t_stat']:+.2f} p={v['hac_p_value']:.3f} "
              f"win={v['win_rate_arm_beats_incumbent']:.3f}")
    print("\nDeployment ceiling:")
    for nm, v in ceiling_block.items():
        print(f"  {nm:<10} theo_ceiling_mean={v['theoretical_ceiling_mean']:.3f} "
              f"exec/ceiling={v['exec_over_ceiling_ratio_mean']:.3f} "
              f"P(E>=0.80)={v['share_sessions_E_exec_ge_0p80']:.3f} "
              f"P(E>=0.90)={v['share_sessions_E_exec_ge_0p90']:.3f} "
              f"n_needed_90={v['breadth_needed_for_0p90']} "
              f"P(breadth>=needed)={v['share_sessions_breadth_ge_needed']:.3f}")
    print(f"\nbreadth: median={breadth_block['median']} "
          f"P(>=4)={breadth_block['share_ge_4']:.3f} "
          f"P(>=5)={breadth_block['share_ge_5']:.3f} "
          f"P(>=8)={breadth_block['share_ge_8']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
