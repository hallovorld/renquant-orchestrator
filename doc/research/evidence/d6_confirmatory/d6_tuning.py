#!/usr/bin/env python3
"""D6 confirmatory run — TUNING PHASE (tuning subset ONLY, 249 sessions).

Nested selection per protocol §1 (doc/design/2026-07-09-governor-prereg-
replay-protocol.md @ orchestrator main 1de64df9) and the declared grids in
TUNING-PLAN.md (committed + pushed BEFORE this script ran — freeze commit
d5c570e52060af62c7518a03009a658167406794).

Selects: regime E_ceil profile, hysteresis band, top-k (stage i, rider arm);
shrinkage s, Kelly fraction lambda (stage ii, governor_kelly arm);
sigma_target (stage iii, voltarget arm). Selection criterion (declared):
max net annualized Sharpe on the tuning subset subject to |MDD| <= 0.30 and
turnover-tax ratio <= 0.50; ties -> higher total net return, then lower
turnover. If no config passes the sanity gates the best-Sharpe config is
chosen and FLAGGED (gates recorded either way).

READ-ONLY outside the scratchpad + this orchestrator worktree. The
EVALUATION subset is never loaded here.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

# ── paths (scratchpad layout; worktree of pipeline origin/main 3e68737) ──
SCRATCH = Path("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/"
               "2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad")
HARNESS_SRC = SCRATCH / "wt-harness-d6main" / "src"
DB_COPY = SCRATCH / "d6run" / "sim_runs.db"
HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze_20260710.json"
PINNED_CFG = SCRATCH / "d6run" / "pinned_strategy_config.json"
OUT = HERE / "tuning_results.json"

sys.dont_write_bytecode = True
for p in (str(HARNESS_SRC),
          "/Users/renhao/git/github/renquant-common/src",
          "/Users/renhao/git/github/renquant-artifacts/src",
          "/Users/renhao/git/github/renquant-base-data/src",
          "/Users/renhao/git/github/renquant-execution/src"):
    sys.path.insert(0, p)

from renquant_pipeline.kernel.portfolio_qp.allocator_replay import (  # noqa: E402
    ReplayConventions,
    replay_all,
    sector_map_coverage_gap,
)
from renquant_pipeline.kernel.portfolio_qp.baseline_allocators import (  # noqa: E402
    AllocatorResult,
)
from renquant_pipeline.kernel.portfolio_qp.wf_replay_loader import (  # noqa: E402
    load_replay_bars_from_sim_db,
)

# ── frozen constants (TUNING-PLAN.md §1/§2) ─────────────────────────────
WORKING_DB_SHA = "72b25fdbd3f246fa5fbefb679349d7e7bd6206d511090bef37602e1b8498827d"
PV_START = 10_700.0
GROSS_MAX = 0.95
PER_NAME_CAP = 0.12
SECTOR_CAP = 0.35
COST_BPS = 5.0
MAX_STEP = 0.15                    # D5 declared, FIXED (not in §1 nested list)
SIGMA_ANNUALIZE = math.sqrt(252.0 / 60.0)
RHO = 0.4
KNOWN_REGIMES = ("BULL_CALM", "BULL_VOLATILE", "CHOPPY", "BEAR")

E_CEIL_PROFILES = {
    "P_flat95": {"BULL_CALM": 0.95, "BULL_VOLATILE": 0.95, "CHOPPY": 0.95, "BEAR": 0.95},
    "P_D5":     {"BULL_CALM": 0.95, "BULL_VOLATILE": 0.70, "CHOPPY": 0.60, "BEAR": 0.35},
    "P_mid":    {"BULL_CALM": 0.95, "BULL_VOLATILE": 0.80, "CHOPPY": 0.60, "BEAR": 0.30},
    "P_derisk": {"BULL_CALM": 0.90, "BULL_VOLATILE": 0.70, "CHOPPY": 0.45, "BEAR": 0.20},
    "P_cons":   {"BULL_CALM": 0.80, "BULL_VOLATILE": 0.60, "CHOPPY": 0.40, "BEAR": 0.10},
}
BANDS = (0.02, 0.05, 0.10)
KS = (4, 6, 8)
SHRINKS = (0.0, 0.1, 0.2)
LAMBDAS = (0.3, 0.5)
SIGMA_TARGETS = (0.12, 0.15, 0.18)


# ── governor arm machinery (RFC #443 §2.1/§2.2, capped-Kelly L2) ────────
def conviction_weights(mu, sigma, *, k, s, lam, cap):
    """raw_i = lam*max(mu - s*sigma, 0)/sigma^2; top-k by conviction raw_i;
    L2 step-1 w_i = min(raw_i, cap). Returns (target, sel, e_raw)."""
    mu = np.asarray(mu, float)
    sigma = np.asarray(sigma, float)
    n = len(mu)
    raw = np.zeros(n)
    for i in range(n):
        sg = max(float(sigma[i]), 1e-6)
        m = float(mu[i])
        if not np.isfinite(m):
            continue
        raw[i] = lam * max(m - s * sg, 0.0) / (sg * sg)
    sel = [i for i in range(n) if raw[i] > 0.0]
    sel.sort(key=lambda i: -raw[i])
    sel = sel[:k]
    target = np.zeros(n)
    for i in sel:
        target[i] = min(raw[i], cap)
    return target, sel, float(target.sum())


class _Gov:
    """E* state machine: hysteresis band + max-step, fail-closed on
    missing/unknown regime (carry current book, no reallocation).

    Regime threading: the stateful engine REBUILDS the session snapshot
    (carried w_current) before calling the allocator, so bar attributes
    do not survive. The engine calls each arm exactly once per bar in
    order (single loop in _replay_one_allocator_stateful), so the regime
    sequence is threaded positionally via a per-arm call counter; the
    counter/bar-count match is asserted after each replay."""

    def __init__(self, mode, *, e_ceil, band, k, s, lam, cap,
                 regimes, sigma_target=None):
        self.mode = mode
        self.e_ceil = e_ceil
        self.band = band
        self.k = k
        self.s = s
        self.lam = lam
        self.cap = cap
        self.sigma_target = sigma_target
        self.regimes = list(regimes)
        self._t = 0
        self.e_prev = None
        self.fail_closed_sessions = 0
        self.estar_series = []

    def _e_target(self, snap, mu, sigma, regime):
        ceil = self.e_ceil[regime]
        if self.mode == "ceil":
            return ceil
        target, sel, e_raw = conviction_weights(
            mu, sigma, k=self.k, s=self.s, lam=self.lam, cap=self.cap)
        if self.mode == "kelly":
            return min(e_raw, ceil)
        # voltarget: sigma_pf on relative capped-Kelly weights, rho=0.4
        tot = float(target.sum())
        if tot <= 0.0:
            return 0.0
        w_rel = target / tot
        sig_ann = np.asarray(sigma, float) * SIGMA_ANNUALIZE
        ws = w_rel * sig_ann
        var = RHO * float(ws.sum()) ** 2 + (1.0 - RHO) * float((ws ** 2).sum())
        s_pf = math.sqrt(max(var, 0.0))
        e_vol = (self.sigma_target / s_pf) if s_pf > 1e-9 else GROSS_MAX
        return min(e_vol, ceil)

    def __call__(self, snap, *, mu, sigma=None):
        regime = self.regimes[self._t] if self._t < len(self.regimes) else None
        self._t += 1
        if regime not in KNOWN_REGIMES:
            self.fail_closed_sessions += 1
            self.estar_series.append(None)
            return AllocatorResult(
                delta_w=np.zeros(snap.n), target_w=np.asarray(snap.w_current, float),
                status="fail_closed_no_regime", selected_indices=())
        e_target = min(self._e_target(snap, mu, sigma, regime), GROSS_MAX)
        if self.e_prev is None:
            e_star = e_target
        elif abs(e_target - self.e_prev) <= self.band:
            e_star = self.e_prev
        else:
            step = max(-MAX_STEP, min(MAX_STEP, e_target - self.e_prev))
            e_star = self.e_prev + step
        e_star = max(0.0, min(e_star, GROSS_MAX))
        self.e_prev = e_star
        self.estar_series.append(e_star)

        target, sel, _ = conviction_weights(
            mu, sigma, k=self.k, s=self.s, lam=self.lam, cap=self.cap)
        tot = float(target.sum())
        if not sel or tot <= 0.0:
            return AllocatorResult(
                delta_w=-np.asarray(snap.w_current, float),
                target_w=np.zeros(snap.n),
                status="no_candidates", selected_indices=())
        if tot > e_star:                       # down-only scale to E*
            target = target * (e_star / tot)
        target = np.minimum(target, self.cap)  # re-assert cap (paranoia)
        tot2 = float(target.sum())
        if tot2 > GROSS_MAX:                   # hard cash budget
            target = target * (GROSS_MAX / tot2)
        return AllocatorResult(
            delta_w=target - np.asarray(snap.w_current, float),
            target_w=target, status="optimal", selected_indices=tuple(sel))


def run_metrics(name, result, bars):
    arr = np.asarray(result.daily_returns_net, float)
    pv_final = result.final_state.portfolio_value
    tax = float(np.sum(result.tax_paid))
    cost = float(np.sum(result.cost_paid))
    gross_usd = (pv_final - PV_START) + tax + cost
    ratio = (tax + cost) / gross_usd if gross_usd > 1e-9 else float("inf")
    return {
        "sharpe_annual_net": result.sharpe_annual,
        "total_net_return": float(np.prod(1.0 + arr) - 1.0),
        "max_drawdown": result.max_drawdown,
        "mean_deployed_fraction": float(np.mean(result.deployed_fraction)),
        "mean_E_executed": float(np.mean(result.executed_exposure)),
        "total_tax_usd": tax,
        "total_cost_usd": cost,
        "turnover_tax_ratio": ratio,
        "gross_usd": gross_usd,
        "mean_session_turnover": result.mean_turnover,
        "off_universe_liquidations": int(result.off_universe_liquidations),
        "no_candidates_sessions": int(result.fallback_to_no_candidates),
    }


def passes_sanity(m):
    return abs(m["max_drawdown"]) <= 0.30 and (
        math.isfinite(m["turnover_tax_ratio"]) and m["turnover_tax_ratio"] <= 0.50)


def pick_best(rows):
    """Declared criterion: Sharpe desc among sanity-passers (fallback: all),
    ties -> total net return desc, then turnover asc."""
    eligible = [r for r in rows if r["sanity_pass"]]
    flagged = not eligible
    pool = eligible or rows
    def key(r):
        m = r["metrics"]
        sh = m["sharpe_annual_net"] if m["sharpe_annual_net"] is not None else -1e9
        return (-sh, -m["total_net_return"], m["mean_session_turnover"])
    pool = sorted(pool, key=key)
    return pool[0], flagged


def main() -> int:
    t0 = time.time()
    freeze = json.loads(FREEZE.read_text())
    assert freeze["source_db"]["sha256"] == WORKING_DB_SHA, "DB sha drift — void"
    import hashlib
    h = hashlib.sha256(DB_COPY.read_bytes()).hexdigest()
    assert h == WORKING_DB_SHA, f"working DB drifted: {h}"

    tuning_ids = list(freeze["horizons"]["fwd_1d"]["tuning"]["ids"])
    tuning_set = set(tuning_ids)

    cfg = json.loads(PINNED_CFG.read_text())
    sector_map = cfg["sector_map"]
    max_per_sector = int(cfg.get("max_positions_per_sector") or 0)

    bars = load_replay_bars_from_sim_db(
        DB_COPY, tuning_ids[0], tuning_ids[-1],
        fwd_horizon_days=1, cost_per_trade_bps=COST_BPS,
        sector_map=sector_map, max_per_sector=max_per_sector)
    bars = [b for b in bars if b.bar_date in tuning_set]
    assert len(bars) == len(tuning_ids), (
        f"tuning bar mismatch: {len(bars)} vs {len(tuning_ids)}")
    regime_seq = [b.regime for b in bars]
    regimes = {}
    for b in bars:
        regimes[str(b.regime)] = regimes.get(str(b.regime), 0) + 1
    print(f"TUNING bars: {len(bars)} ({bars[0].bar_date}..{bars[-1].bar_date}) "
          f"regimes={regimes}")

    conv = ReplayConventions(
        stateful=True, tax=True, integer_shares=True, enforce_caps=True,
        per_name_cap=PER_NAME_CAP, sector_cap=SECTOR_CAP,
        sector_map=sector_map, initial_capital=PV_START)
    gap = sector_map_coverage_gap(bars, conv)
    assert not gap, f"sector map gap (fail-closed): {gap}"

    results_log = {"stage_i_rider": [], "stage_ii_kelly": [], "stage_iii_voltarget": []}

    # ── stage i: rider (E_ceil x band x k), s=0, lam=0.3 ────────────────
    for pname, prof in E_CEIL_PROFILES.items():
        for band in BANDS:
            for k in KS:
                gov = _Gov("ceil", e_ceil=prof, band=band, k=k,
                           s=0.0, lam=0.3, cap=PER_NAME_CAP,
                           regimes=regime_seq)
                res = replay_all({"arm": gov}, bars, conv)["arm"]
                assert gov._t == len(bars), "call-count desync (ceil)"
                m = run_metrics("arm", res, bars)
                row = {"profile": pname, "band": band, "k": k,
                       "fail_closed_sessions": gov.fail_closed_sessions,
                       "metrics": m, "sanity_pass": passes_sanity(m)}
                results_log["stage_i_rider"].append(row)
    best_i, flag_i = pick_best(results_log["stage_i_rider"])
    print(f"stage i chosen: {best_i['profile']} band={best_i['band']} "
          f"k={best_i['k']} (gate-flagged={flag_i}) "
          f"sharpe={best_i['metrics']['sharpe_annual_net']}")

    prof = E_CEIL_PROFILES[best_i["profile"]]
    band, k = best_i["band"], best_i["k"]

    # ── stage ii: governor_kelly (s x lambda) at chosen rider params ────
    for s in SHRINKS:
        for lam in LAMBDAS:
            gov = _Gov("kelly", e_ceil=prof, band=band, k=k,
                       s=s, lam=lam, cap=PER_NAME_CAP, regimes=regime_seq)
            res = replay_all({"arm": gov}, bars, conv)["arm"]
            assert gov._t == len(bars), "call-count desync (kelly)"
            m = run_metrics("arm", res, bars)
            results_log["stage_ii_kelly"].append(
                {"s": s, "lam": lam,
                 "fail_closed_sessions": gov.fail_closed_sessions,
                 "metrics": m, "sanity_pass": passes_sanity(m)})
    best_ii, flag_ii = pick_best(results_log["stage_ii_kelly"])
    print(f"stage ii chosen: s={best_ii['s']} lam={best_ii['lam']} "
          f"(gate-flagged={flag_ii}) sharpe={best_ii['metrics']['sharpe_annual_net']}")

    # ── stage iii: voltarget sigma_target at chosen params ──────────────
    for st in SIGMA_TARGETS:
        gov = _Gov("voltarget", e_ceil=prof, band=band, k=k,
                   s=best_ii["s"], lam=best_ii["lam"], cap=PER_NAME_CAP,
                   regimes=regime_seq, sigma_target=st)
        res = replay_all({"arm": gov}, bars, conv)["arm"]
        assert gov._t == len(bars), "call-count desync (voltarget)"
        m = run_metrics("arm", res, bars)
        results_log["stage_iii_voltarget"].append(
            {"sigma_target": st,
             "fail_closed_sessions": gov.fail_closed_sessions,
             "metrics": m, "sanity_pass": passes_sanity(m)})
    best_iii, flag_iii = pick_best(results_log["stage_iii_voltarget"])
    print(f"stage iii chosen: sigma_target={best_iii['sigma_target']} "
          f"(gate-flagged={flag_iii}) sharpe={best_iii['metrics']['sharpe_annual_net']}")

    chosen = {
        "e_ceil_profile": best_i["profile"],
        "e_ceil_by_regime": prof,
        "hysteresis_band": band,
        "top_k": k,
        "mu_shrinkage_s": best_ii["s"],
        "kelly_fraction_lambda": best_ii["lam"],
        "sigma_target_annual": best_iii["sigma_target"],
        "max_step_per_session_FIXED": MAX_STEP,
        "gate_flags": {"stage_i": flag_i, "stage_ii": flag_ii, "stage_iii": flag_iii},
    }
    payload = {
        "label": "D6 CONFIRMATORY — TUNING PHASE (nested selection, tuning subset only)",
        "protocol": "doc/design/2026-07-09-governor-prereg-replay-protocol.md @ 1de64df9",
        "freeze_record": "freeze_20260710.json",
        "freeze_commit": "d5c570e52060af62c7518a03009a658167406794",
        "db_sha256": WORKING_DB_SHA,
        "n_tuning_bars": len(bars),
        "bar_dates_first_last": [bars[0].bar_date, bars[-1].bar_date],
        "regime_counts": regimes,
        "conventions": conv.to_dict(),
        "declared_grids": {
            "e_ceil_profiles": E_CEIL_PROFILES, "bands": BANDS, "ks": KS,
            "shrinks": SHRINKS, "lambdas": LAMBDAS, "sigma_targets": SIGMA_TARGETS,
            "max_step_fixed": MAX_STEP,
        },
        "selection_criterion": (
            "max net annualized Sharpe on tuning subset s.t. |MDD|<=0.30 and "
            "turnover-tax ratio<=0.50; ties: total net return desc, turnover asc; "
            "if no config passes, best Sharpe chosen and flagged"),
        "chosen": chosen,
        "results": results_log,
        "runtime_seconds": round(time.time() - t0, 2),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=list) + "\n")
    print(f"tuning results written: {OUT} ({time.time()-t0:.1f}s)")
    print("CHOSEN:", json.dumps(chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
