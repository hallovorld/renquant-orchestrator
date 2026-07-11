#!/usr/bin/env python3
"""D6 confirmatory run — EVALUATION PHASE (frozen evaluation subset, ONE pass).

Runs the LOCKED Phase-1 + Phase-2 family (protocol §2, as restated in
TUNING-PLAN.md §3 — committed and pushed in the freeze commit
d5c570e52060af62c7518a03009a658167406794 BEFORE any arm ran) over the frozen
188-session evaluation range (2025-05-08..2026-03-27, fwd_1d), simulated as
ONE continuous book per arm (protocol §2 evaluation scheme). Hyperparameters
come from the tuning phase ONLY (tuning_results.json; nested selection §1).

Analysis per §1.2 / §3 / §4 / §5:
- unit (i): daily paired net returns, NW lag = min(floor(4*(T/100)^(2/9)), 10),
  95% CI; promotion bar mean >= +1bp/day AND CI excl 0 AND DSR >= 0.95 AND
  PBO <= 0.10 (family CSCV, seed 0, 16 slices; n_trials = family size).
- unit (ii): 20d non-overlapping outcome blocks (geometric compounding of
  daily net log-returns), NW(lag1)-on-blocks t CI (df N-1) AND stationary
  bootstrap (E[len]=2, 10k resamples, seed 0), one-sided alpha=0.05
  conjunction; ESS = N*(1-rho1)/(1+rho1), rho1 clipped at 0; minima
  N_blocks >= 8 AND ESS >= 6. 60d blocks (3): DESCRIPTIVE-ONLY, no test.
- decomposed estimands (a)/(b)/(c) per §3; marginal capital via unit (ii).
- §4 gates: recorded; a breach fails promotion but the series completes
  (historical-replay stop rule, §5).

READ-ONLY outside scratchpad + this orchestrator worktree.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

SCRATCH = Path("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/"
               "2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad")
HARNESS_SRC = SCRATCH / "wt-harness-d6main" / "src"
DB_COPY = SCRATCH / "d6run" / "sim_runs.db"
HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze_20260710.json"
TUNING = HERE / "tuning_results.json"
PINNED_CFG = SCRATCH / "d6run" / "pinned_strategy_config.json"
OUT_EVIDENCE = HERE / "evidence_eval_fwd1d.json"
OUT_ANALYSIS = HERE / "analysis_results.json"

sys.dont_write_bytecode = True
for p in (str(HARNESS_SRC),
          "/Users/renhao/git/github/renquant-common/src",
          "/Users/renhao/git/github/renquant-artifacts/src",
          "/Users/renhao/git/github/renquant-base-data/src",
          "/Users/renhao/git/github/renquant-execution/src"):
    sys.path.insert(0, p)

from renquant_pipeline.kernel.portfolio_qp import allocator_replay  # noqa: E402
from renquant_pipeline.kernel.portfolio_qp.allocator_replay import (  # noqa: E402
    ReplayConventions,
    replay_all,
    sector_map_coverage_gap,
)
from renquant_pipeline.kernel.portfolio_qp.baseline_allocators import (  # noqa: E402
    AllocatorResult,
)
from renquant_pipeline.kernel.portfolio_qp.run_ab_replay import (  # noqa: E402
    get_allocator,
)
from renquant_pipeline.kernel.portfolio_qp.replay_significance import (  # noqa: E402
    compute_significance_verdicts,
    verdicts_to_dict,
)
from renquant_pipeline.kernel.portfolio_qp.wf_replay_loader import (  # noqa: E402
    load_replay_bars_from_sim_db,
)
from renquant_common.metrics.hac_se import hac_t_stat  # noqa: E402

# ── frozen constants ────────────────────────────────────────────────────
WORKING_DB_SHA = "72b25fdbd3f246fa5fbefb679349d7e7bd6206d511090bef37602e1b8498827d"
FREEZE_COMMIT = "d5c570e52060af62c7518a03009a658167406794"
PV_START = 10_700.0
GROSS_MAX = 0.95
CAP12, CAP20 = 0.12, 0.20
SECTOR_CAP = 0.35
COST_BPS = 5.0
MAX_STEP = 0.15
SIGMA_ANNUALIZE = math.sqrt(252.0 / 60.0)
RHO = 0.4
KNOWN_REGIMES = ("BULL_CALM", "BULL_VOLATILE", "CHOPPY", "BEAR")
BLOCK_H20, BLOCK_H60 = 20, 60
NI_MARGIN_20D = -0.0050            # -50 bps per 20d block (one-sided margin)
ALPHA = 0.05
T_CRIT_DF8_95 = 1.8595             # t_{0.95, df=8}
BOOT_N, BOOT_SEED, BOOT_EXP_LEN = 10_000, 0, 2.0
TBILL_ANNUAL_DESCRIPTIVE = 0.04    # descriptive overlay only (cost_no_carry
                                   # is the project's frozen sleeve convention)

BASELINES = ["current_qp", "equal_weight_top_k", "inverse_vol_top_k",
             "fractional_kelly_top_k", "hybrid_option_f_allocator",
             "hard_only_qp_allocator", "stage_a_a2_long_only"]

# ── side channels ───────────────────────────────────────────────────────
EXEC_W: dict[str, list] = {}
_ORIG_RECORD = allocator_replay._record_family_violations


def _capturing_record(res, snap, target_w, delta_w):
    EXEC_W.setdefault(res.name, []).append(np.asarray(target_w, float).copy())
    return _ORIG_RECORD(res, snap, target_w, delta_w)


# ── governor machinery (identical to d6_tuning.py; kept in-file so the
#    evaluation artifact is self-contained) ──────────────────────────────
def conviction_weights(mu, sigma, *, k, s, lam, cap):
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


class Gov:
    """L1 governor arm (positional regime threading; see d6_tuning.py)."""

    def __init__(self, mode, *, e_ceil, band, k, s, lam, cap,
                 regimes, sigma_target=None, hysteresis=True):
        self.mode, self.e_ceil, self.band, self.k = mode, e_ceil, band, k
        self.s, self.lam, self.cap = s, lam, cap
        self.sigma_target = sigma_target
        self.hysteresis = hysteresis
        self.regimes = list(regimes)
        self._t = 0
        self.e_prev = None
        self.fail_closed_sessions = 0
        self.estar_series: list = []

    def _e_target(self, mu, sigma, regime):
        ceil = self.e_ceil[regime]
        if self.mode == "ceil":
            return ceil
        target, sel, e_raw = conviction_weights(
            mu, sigma, k=self.k, s=self.s, lam=self.lam, cap=self.cap)
        if self.mode == "kelly":
            return min(e_raw, ceil)
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
                delta_w=np.zeros(snap.n),
                target_w=np.asarray(snap.w_current, float),
                status="fail_closed_no_regime", selected_indices=())
        e_target = min(self._e_target(mu, sigma, regime), GROSS_MAX)
        if not self.hysteresis or self.e_prev is None:
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
        if tot > e_star:
            target = target * (e_star / tot)
        target = np.minimum(target, self.cap)
        tot2 = float(target.sum())
        if tot2 > GROSS_MAX:
            target = target * (GROSS_MAX / tot2)
        return AllocatorResult(
            delta_w=target - np.asarray(snap.w_current, float),
            target_w=target, status="optimal", selected_indices=tuple(sel))


class GridArm:
    """Breadth-x-cap grid arm: deployment = pure regime ceiling (no
    hysteresis), weights ew | capped-kelly (s=0, lam=0.3, the stage-i /
    exploratory-grid weight convention)."""

    def __init__(self, scheme, cap, *, e_ceil, k, regimes):
        self.scheme, self.cap, self.e_ceil, self.k = scheme, cap, e_ceil, k
        self.regimes = list(regimes)
        self._t = 0
        self.fail_closed_sessions = 0

    def __call__(self, snap, *, mu, sigma=None):
        regime = self.regimes[self._t] if self._t < len(self.regimes) else None
        self._t += 1
        if regime not in KNOWN_REGIMES:
            self.fail_closed_sessions += 1
            return AllocatorResult(
                delta_w=np.zeros(snap.n),
                target_w=np.asarray(snap.w_current, float),
                status="fail_closed_no_regime", selected_indices=())
        e_t = min(self.e_ceil[regime], GROSS_MAX)
        target, sel, _ = conviction_weights(
            mu, sigma, k=self.k, s=0.0, lam=0.3, cap=self.cap)
        if not sel:
            return AllocatorResult(
                delta_w=-np.asarray(snap.w_current, float),
                target_w=np.zeros(snap.n),
                status="no_candidates", selected_indices=())
        if self.scheme == "ew":
            w = min(e_t / len(sel), self.cap)
            target = np.zeros(snap.n)
            for i in sel:
                target[i] = w
        else:  # capped-kelly, down-only scale to the ceiling
            tot = float(target.sum())
            if tot > e_t:
                target = target * (e_t / tot)
        tot2 = float(target.sum())
        if tot2 > GROSS_MAX:
            target = target * (GROSS_MAX / tot2)
        return AllocatorResult(
            delta_w=target - np.asarray(snap.w_current, float),
            target_w=target, status="optimal", selected_indices=tuple(sel))


class EwAtEstar:
    """Equal-weight at an EXTERNAL per-session E* series (estimand (a):
    E*_governor vs E*_incumbent, equal_weight preregistered comparator)."""

    def __init__(self, estar_series, *, k, cap, regimes):
        self.estar = list(estar_series)
        self.k, self.cap = k, cap
        self.regimes = list(regimes)
        self._t = 0

    def __call__(self, snap, *, mu, sigma=None):
        t = self._t
        self._t += 1
        e_t = self.estar[t]
        if e_t is None:
            return AllocatorResult(
                delta_w=np.zeros(snap.n),
                target_w=np.asarray(snap.w_current, float),
                status="fail_closed_no_estar", selected_indices=())
        _, sel, _ = conviction_weights(
            mu, sigma, k=self.k, s=0.0, lam=0.3, cap=self.cap)
        target = np.zeros(snap.n)
        if not sel:
            return AllocatorResult(
                delta_w=-np.asarray(snap.w_current, float), target_w=target,
                status="no_candidates", selected_indices=())
        w = min(max(float(e_t), 0.0) / len(sel), self.cap)
        for i in sel:
            target[i] = w
        tot = float(target.sum())
        if tot > GROSS_MAX:
            target = target * (GROSS_MAX / tot)
        return AllocatorResult(
            delta_w=target - np.asarray(snap.w_current, float),
            target_w=target, status="optimal", selected_indices=tuple(sel))


def cash_park(snap, *, mu, sigma=None):
    """Control: zero equity (idle capital; cost_no_carry convention)."""
    return AllocatorResult(
        delta_w=-np.asarray(snap.w_current, float),
        target_w=np.zeros(snap.n), status="optimal", selected_indices=())


# ── §1.2 statistics ─────────────────────────────────────────────────────
def nw_lag_unit_i(T: int) -> int:
    return min(int(math.floor(4.0 * (T / 100.0) ** (2.0 / 9.0))), 10)


def unit_i_paired(delta: np.ndarray) -> dict:
    """Daily paired series: NW capped-lag mean test + 95% CI (two-sided)."""
    T = len(delta)
    lag = nw_lag_unit_i(T)
    h = hac_t_stat(delta.tolist(), lag=lag)
    mean, se = h["mean"], h["se_nw"]
    ci = (mean - 1.96 * se, mean + 1.96 * se)
    return {"n": T, "lag": lag, "mean_daily": mean, "se_nw": se,
            "t_stat": h["t_stat"], "p_value": h["p_value"],
            "ci95": list(ci), "ci_excludes_zero": bool(ci[0] > 0 or ci[1] < 0),
            "mean_ge_1bp": bool(mean >= 1e-4)}


def block_returns(daily: np.ndarray, h: int) -> np.ndarray:
    """Non-overlapping h-day blocks from the start; geometric compounding."""
    n_blocks = len(daily) // h
    out = []
    for i in range(n_blocks):
        seg = daily[i * h:(i + 1) * h]
        out.append(float(np.exp(np.sum(np.log1p(seg))) - 1.0))
    return np.asarray(out)


def nw_lag1_block_se(d: np.ndarray) -> float:
    """Newey-West lag-1 SE of the mean, computed ON the block series."""
    n = len(d)
    dc = d - d.mean()
    g0 = float(np.mean(dc * dc))
    g1 = float(np.mean(dc[1:] * dc[:-1])) * (n - 1) / n
    var_lr = g0 + 2.0 * 0.5 * g1          # Bartlett weight at lag 1 = 1/2
    var_lr = max(var_lr, 0.0)
    return math.sqrt(var_lr / n)


def stationary_bootstrap_means(d: np.ndarray, n_boot: int, exp_len: float,
                               seed: int) -> np.ndarray:
    """Politis-Romano stationary bootstrap of the mean of d."""
    rng = np.random.default_rng(seed)
    n = len(d)
    p = 1.0 / exp_len
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.empty(n, dtype=int)
        i = rng.integers(0, n)
        for t in range(n):
            if t > 0 and rng.random() >= p:
                i = (i + 1) % n
            else:
                if t > 0:
                    i = rng.integers(0, n)
            idx[t] = i
        means[b] = d[idx].mean()
    return means


def unit_ii_test(d: np.ndarray, margin: float) -> dict:
    """§1.2 unit (ii): NW(lag1)-on-blocks t CI AND stationary bootstrap,
    one-sided alpha=0.05 conjunction vs H0: mean <= margin."""
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"n_blocks": n, "mean": mean, "insufficient": True}
    se = nw_lag1_block_se(d)
    tcrit = T_CRIT_DF8_95 if n == 9 else _t_crit(n - 1)
    lcb_nw = mean - tcrit * se           # one-sided 95% lower confidence bound
    nw_rejects = bool(lcb_nw > margin)
    boots = stationary_bootstrap_means(d, BOOT_N, BOOT_EXP_LEN, BOOT_SEED)
    lcb_boot = float(np.percentile(boots, 100 * ALPHA))
    boot_rejects = bool(lcb_boot > margin)
    dc = d - mean
    denom = float(np.sum(dc * dc))
    rho1 = float(np.sum(dc[1:] * dc[:-1]) / denom) if denom > 0 else 0.0
    rho1_clipped = max(rho1, 0.0)
    ess = n * (1.0 - rho1_clipped) / (1.0 + rho1_clipped)
    return {
        "n_blocks": n, "mean": mean, "se_nw_lag1": se,
        "t_crit_one_sided_95": tcrit,
        "lcb95_nw": lcb_nw, "nw_rejects_H0_mean_le_margin": nw_rejects,
        "lcb95_bootstrap": lcb_boot,
        "bootstrap_rejects_H0_mean_le_margin": boot_rejects,
        "conjunction_rejects": bool(nw_rejects and boot_rejects),
        "disagreement": bool(nw_rejects != boot_rejects),
        "margin": margin, "rho1": rho1, "rho1_clipped": rho1_clipped,
        "ess": ess, "meets_minima_n8_ess6": bool(n >= 8 and ess >= 6.0),
        "bootstrap": {"n_resamples": BOOT_N, "expected_block_len": BOOT_EXP_LEN,
                      "seed": BOOT_SEED},
    }


def _t_crit(df: int) -> float:
    from scipy.stats import t as tdist
    return float(tdist.ppf(0.95, df))


# ── metrics + gates ─────────────────────────────────────────────────────
def run_metrics(result) -> dict:
    arr = np.asarray(result.daily_returns_net, float)
    pv_final = result.final_state.portfolio_value
    tax = float(np.sum(result.tax_paid))
    cost = float(np.sum(result.cost_paid))
    gross_usd = (pv_final - PV_START) + tax + cost
    ratio = (tax + cost) / gross_usd if gross_usd > 1e-9 else float("inf")
    return {
        "sharpe_annual_net": result.sharpe_annual,
        "total_net_return": float(np.prod(1.0 + arr) - 1.0),
        "final_pv": float(pv_final),
        "max_drawdown": result.max_drawdown,
        "mean_deployed_fraction": float(np.mean(result.deployed_fraction)),
        "median_deployed_fraction": float(np.median(result.deployed_fraction)),
        "mean_E_executed": float(np.mean(result.executed_exposure)),
        "total_tax_usd": tax, "total_cost_usd": cost,
        "turnover_tax_ratio": ratio, "gross_usd": gross_usd,
        "mean_session_turnover": result.mean_turnover,
        "total_name_cap_breaches": int(np.sum(result.name_cap_breaches)),
        "total_sector_cap_breaches": int(np.sum(result.sector_cap_breaches)),
        "off_universe_liquidations": int(result.off_universe_liquidations),
        "no_candidates_sessions": int(result.fallback_to_no_candidates),
        "mean_integer_residual": float(np.mean(result.integer_residual)),
    }


def gates_for_arm(name, m, res, bars, arm_cap, ew_mean_turnover) -> dict:
    """§4 non-degradation gates (recorded; replay series always completes)."""
    ws = EXEC_W.get(name, [])
    worst = []
    max_w = 0.0
    max_sector_w = 0.0
    cfg = json.loads(PINNED_CFG.read_text())
    sector_map = cfg["sector_map"]
    for b, w in zip(bars, ws):
        held = w > 1e-9
        if held.any():
            contrib = w[held] * np.asarray(b.fwd_return, float)[held]
            worst.append(float(contrib.min()))
            max_w = max(max_w, float(w.max()))
            sec_tot: dict = {}
            for i, tk in enumerate(b.snap.tickers):
                if w[i] > 1e-9:
                    sec = sector_map.get(tk)
                    sec_tot[sec] = sec_tot.get(sec, 0.0) + float(w[i])
            if sec_tot:
                max_sector_w = max(max_sector_w, max(sec_tot.values()))
        else:
            worst.append(0.0)
    p5 = float(np.percentile(worst, 5)) if worst else 0.0
    conc_tol = -(arm_cap * 0.20)
    gates = {
        "single_name_construction_invariant": {
            "max_realized_weight": max_w, "tolerance": arm_cap,
            "pass": bool(max_w <= arm_cap + 1e-9)},
        "operator_policy_ceiling_12pct": {
            "arm_cap": arm_cap, "within_12pct_policy": bool(arm_cap <= 0.12 + 1e-9),
            "note": "cap>12% arms need recorded operator sign-off to ENABLE"},
        "sector_weight": {
            "max_realized_sector_weight": max_sector_w, "tolerance": SECTOR_CAP,
            "pass": bool(max_sector_w <= SECTOR_CAP + 1e-9),
            "enforced_in_arm_breach_count": m["total_sector_cap_breaches"]},
        "session_turnover_vs_2x_ew": {
            "mean_turnover": m["mean_session_turnover"],
            "tolerance_2x_ew": 2.0 * ew_mean_turnover,
            "pass": bool(m["mean_session_turnover"] <= 2.0 * ew_mean_turnover + 1e-12)},
        "max_drawdown": {
            "mdd": m["max_drawdown"], "tolerance": -0.30,
            "pass": bool(m["max_drawdown"] >= -0.30)},
        "concentration_event_p5": {
            "p5_worst_name_contrib": p5, "tolerance": conc_tol,
            "pass": bool(p5 >= conc_tol)},
        "turnover_tax_ratio": {
            "ratio": m["turnover_tax_ratio"], "tolerance": 0.50,
            "pass": bool(math.isfinite(m["turnover_tax_ratio"])
                         and m["turnover_tax_ratio"] <= 0.50)},
    }
    gates["all_pass"] = all(
        g.get("pass", True) for g in gates.values() if isinstance(g, dict))
    return gates


def fail_closed_injection_test() -> dict:
    """§4 fail-closed gate: injected missing/unknown-regime cases must emit
    NO target (carry current book) in 100% of cases."""
    class _Snap:
        n = 3
        w_current = np.array([0.1, 0.0, 0.05])
        tickers = ("A", "B", "C")
    cases = [None, "UNKNOWN_REGIME", "HIGH_SPIKED"]
    passed = 0
    for reg in cases:
        gov = Gov("ceil", e_ceil={r: 0.95 for r in KNOWN_REGIMES}, band=0.05,
                  k=4, s=0.0, lam=0.3, cap=0.12, regimes=[reg])
        out = gov(_Snap(), mu=np.array([0.1, 0.2, 0.3]),
                  sigma=np.array([0.1, 0.1, 0.1]))
        if (out.status == "fail_closed_no_regime"
                and np.allclose(out.target_w, _Snap.w_current)
                and np.allclose(out.delta_w, 0.0)):
            passed += 1
    return {"n_injected": len(cases), "n_fail_closed": passed,
            "pass": passed == len(cases)}


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    t0 = time.time()
    freeze = json.loads(FREEZE.read_text())
    assert freeze["source_db"]["sha256"] == WORKING_DB_SHA
    assert hashlib.sha256(DB_COPY.read_bytes()).hexdigest() == WORKING_DB_SHA, \
        "working DB drifted — freeze void"
    tuning = json.loads(TUNING.read_text())
    chosen = tuning["chosen"]
    E_CEIL = chosen["e_ceil_by_regime"]
    BAND = chosen["hysteresis_band"]
    K = chosen["top_k"]
    S = chosen["mu_shrinkage_s"]
    LAM = chosen["kelly_fraction_lambda"]
    SIGMA_T = chosen["sigma_target_annual"]

    eval_ids = list(freeze["horizons"]["fwd_1d"]["evaluation"]["ids"])
    eval_set = set(eval_ids)
    cfg = json.loads(PINNED_CFG.read_text())
    sector_map = cfg["sector_map"]
    max_per_sector = int(cfg.get("max_positions_per_sector") or 0)

    bars = load_replay_bars_from_sim_db(
        DB_COPY, eval_ids[0], eval_ids[-1], fwd_horizon_days=1,
        cost_per_trade_bps=COST_BPS, sector_map=sector_map,
        max_per_sector=max_per_sector)
    bars = [b for b in bars if b.bar_date in eval_set]
    assert len(bars) == len(eval_ids), (
        f"eval bar mismatch: {len(bars)} vs {len(eval_ids)}")
    regime_seq = [b.regime for b in bars]
    regime_counts: dict = {}
    for r in regime_seq:
        regime_counts[str(r)] = regime_counts.get(str(r), 0) + 1
    print(f"EVAL bars: {len(bars)} ({bars[0].bar_date}..{bars[-1].bar_date}) "
          f"regimes={regime_counts}")

    # incumbent realized E* + PV from the sim run bundles (pipeline_runs)
    conn = sqlite3.connect(f"file:{DB_COPY}?mode=ro", uri=True)
    rows = conn.execute(
        """SELECT run_date, portfolio_value, cash FROM pipeline_runs
           WHERE rowid IN (SELECT MAX(rowid) FROM pipeline_runs
                           WHERE portfolio_value > 0 AND cash IS NOT NULL
                           GROUP BY run_date)""").fetchall()
    conn.close()
    inc = {d: (pv, cash) for d, pv, cash in rows}
    missing = [d for d in eval_ids if d not in inc]
    assert not missing, f"incumbent run-bundle coverage gap: {missing[:5]}"
    inc_estar = [min(max(1.0 - inc[d][1] / inc[d][0], 0.0), GROSS_MAX)
                 for d in eval_ids]
    inc_pv = np.asarray([inc[d][0] for d in eval_ids], float)
    inc_daily = inc_pv[1:] / inc_pv[:-1] - 1.0   # descriptive only

    # precompute PRIMARY governor E* series (deterministic in regime_seq)
    pre = Gov("ceil", e_ceil=E_CEIL, band=BAND, k=K, s=0.0, lam=0.3,
              cap=CAP12, regimes=regime_seq)
    for reg in regime_seq:
        # replicate the E* state walk without portfolio interaction
        pre(_DummySnap(), mu=np.array([1e-3]), sigma=np.array([0.1]))
    gov_estar_series = list(pre.estar_series)
    assert len(gov_estar_series) == len(bars)

    conv12 = ReplayConventions(
        stateful=True, tax=True, integer_shares=True, enforce_caps=True,
        per_name_cap=CAP12, sector_cap=SECTOR_CAP, sector_map=sector_map,
        initial_capital=PV_START)
    conv20 = ReplayConventions(
        stateful=True, tax=True, integer_shares=True, enforce_caps=True,
        per_name_cap=CAP20, sector_cap=SECTOR_CAP, sector_map=sector_map,
        initial_capital=PV_START)
    gap = sector_map_coverage_gap(bars, conv12)
    assert not gap, f"sector map gap (fail-closed): {gap}"

    gov_ceiling = Gov("ceil", e_ceil=E_CEIL, band=BAND, k=K, s=0.0, lam=0.3,
                      cap=CAP12, regimes=regime_seq)
    gov_kelly = Gov("kelly", e_ceil=E_CEIL, band=BAND, k=K, s=S, lam=LAM,
                    cap=CAP12, regimes=regime_seq)
    gov_voltgt = Gov("voltarget", e_ceil=E_CEIL, band=BAND, k=K, s=S, lam=LAM,
                     cap=CAP12, regimes=regime_seq, sigma_target=SIGMA_T)

    arms12 = {n: get_allocator(n) for n in BASELINES}
    arms12.update({
        "gov_ceiling_ck": gov_ceiling,
        "gov_kelly_ck": gov_kelly,
        "gov_voltarget_ck": gov_voltgt,
        "cap12_ew_ceil": GridArm("ew", CAP12, e_ceil=E_CEIL, k=K,
                                 regimes=regime_seq),
        "cap12_ck_ceil": GridArm("ck", CAP12, e_ceil=E_CEIL, k=K,
                                 regimes=regime_seq),
        "ew_at_gov_estar": EwAtEstar(gov_estar_series, k=K, cap=CAP12,
                                     regimes=regime_seq),
        "ew_at_incumbent_estar": EwAtEstar(inc_estar, k=K, cap=CAP12,
                                           regimes=regime_seq),
        "cash_park": cash_park,
    })
    arms20 = {
        "cap20_ew_ceil": GridArm("ew", CAP20, e_ceil=E_CEIL, k=K,
                                 regimes=regime_seq),
        "cap20_ck_ceil": GridArm("ck", CAP20, e_ceil=E_CEIL, k=K,
                                 regimes=regime_seq),
    }
    arm_caps = {n: CAP12 for n in arms12}
    arm_caps.update({n: CAP20 for n in arms20})

    allocator_replay._record_family_violations = _capturing_record
    try:
        results = replay_all(arms12, bars, conv12)
        results.update(replay_all(arms20, bars, conv20))
    finally:
        allocator_replay._record_family_violations = _ORIG_RECORD

    # PV identity + capture sanity
    for nm, r in results.items():
        lhs = float(np.prod(1.0 + np.asarray(r.daily_returns_net)))
        assert abs(lhs - r.final_state.portfolio_value / PV_START) < 1e-9, nm
        assert len(EXEC_W.get(nm, [])) == len(bars), f"{nm} capture mismatch"

    metrics = {nm: run_metrics(r) for nm, r in results.items()}
    daily = {nm: np.asarray(r.daily_returns_net, float)
             for nm, r in results.items()}
    ew_turn = metrics["equal_weight_top_k"]["mean_session_turnover"]
    gates = {nm: gates_for_arm(nm, metrics[nm], results[nm], bars,
                               arm_caps[nm], ew_turn) for nm in results}
    injection = fail_closed_injection_test()

    # significance family (unit (i) DSR/PBO): all named candidates except
    # the constant-return cash control
    family = {nm: r for nm, r in results.items() if nm != "cash_park"}
    significance = verdicts_to_dict(
        compute_significance_verdicts(family, pbo_n_slices=16))
    n_trials_family = len(family)

    # ── paired comparisons ──────────────────────────────────────────────
    def paired(a, b):
        out = unit_i_paired(daily[a] - daily[b])
        out["promotion_bar_unit_i"] = bool(
            out["mean_ge_1bp"] and out["ci_excludes_zero"]
            and (significance.get(a, {}).get("dsr") or 0) >= 0.95
            and (significance.get(a, {}).get("pbo") is not None
                 and significance[a]["pbo"] <= 0.10))
        return out

    unit_i = {}
    for cand in ("gov_ceiling_ck", "gov_kelly_ck", "gov_voltarget_ck",
                 "cap12_ew_ceil", "cap12_ck_ceil", "cap20_ew_ceil",
                 "cap20_ck_ceil"):
        unit_i[f"{cand}_minus_equal_weight_top_k"] = paired(cand, "equal_weight_top_k")
        unit_i[f"{cand}_minus_inverse_vol_top_k"] = paired(cand, "inverse_vol_top_k")
    unit_i["gov_ceiling_ck_minus_current_qp"] = paired("gov_ceiling_ck", "current_qp")
    unit_i["ew_at_gov_estar_minus_ew_at_incumbent_estar"] = paired(
        "ew_at_gov_estar", "ew_at_incumbent_estar")
    unit_i["cap12_ew_ceil_minus_cap12_ck_ceil"] = paired("cap12_ew_ceil", "cap12_ck_ceil")
    unit_i["cap20_ew_ceil_minus_cap20_ck_ceil"] = paired("cap20_ew_ceil", "cap20_ck_ceil")

    # ── unit (ii): 20d blocks (enable-grade length) + 60d descriptive ──
    unit_ii = {}
    descriptive_60d = {}
    key_pairs = {
        "marginal_capital_a_ewgov_minus_ewinc":
            ("ew_at_gov_estar", "ew_at_incumbent_estar"),
        "gov_ceiling_minus_equal_weight": ("gov_ceiling_ck", "equal_weight_top_k"),
        "gov_ceiling_minus_inverse_vol": ("gov_ceiling_ck", "inverse_vol_top_k"),
        "gov_ceiling_minus_current_qp": ("gov_ceiling_ck", "current_qp"),
    }
    for label, (a, b) in key_pairs.items():
        d20 = block_returns(daily[a], BLOCK_H20) - block_returns(daily[b], BLOCK_H20)
        res_m = unit_ii_test(d20, NI_MARGIN_20D)
        res_0 = unit_ii_test(d20, 0.0)
        unit_ii[label] = {
            "block_diffs_20d": [float(x) for x in d20],
            "point_estimate_ge_0": bool(d20.mean() >= 0.0),
            "vs_margin_minus50bps": res_m,
            "vs_zero_margin": res_0,
        }
        d60 = block_returns(daily[a], BLOCK_H60) - block_returns(daily[b], BLOCK_H60)
        descriptive_60d[label] = {
            "n_blocks": len(d60), "block_diffs": [float(x) for x in d60],
            "mean": float(d60.mean()),
            "NOTE": "DESCRIPTIVE-ONLY per §1.2 — no significance test computed",
        }

    # ── §5 verdict assembly (honest) ────────────────────────────────────
    def bar(name):
        s = significance.get(name, {})
        return {
            "beats_ew_unit_i": unit_i[f"{name}_minus_equal_weight_top_k"],
            "beats_iv_unit_i": unit_i[f"{name}_minus_inverse_vol_top_k"],
            "dsr": s.get("dsr"), "pbo": s.get("pbo"),
            "dsr_ge_095": bool((s.get("dsr") or 0) >= 0.95),
            "pbo_le_010": bool(s.get("pbo") is not None and s["pbo"] <= 0.10),
            "gates_all_pass": gates[name]["all_pass"],
        }

    marginal = unit_ii["marginal_capital_a_ewgov_minus_ewinc"]
    verdict = {
        "primary_arm": "gov_ceiling_ck",
        "primary_bar": bar("gov_ceiling_ck"),
        "comparison_arms": {n: bar(n) for n in ("gov_kelly_ck", "gov_voltarget_ck")},
        "marginal_capital_ge_0": marginal["point_estimate_ge_0"],
        "fail_closed_injection": injection,
        "s1_live_shadow_requirement": (
            "UNMET BY CONSTRUCTION — §5 requires the live shadow arm-level "
            "endpoint; historical replay is directional/low-power support only"),
        "enable_possible_from_this_run": False,
    }

    payload = {
        "label": "D6 CONFIRMATORY REPLAY — EVALUATION (first protocol-valid run)",
        "as_of_date": "2026-07-11",
        "protocol": "doc/design/2026-07-09-governor-prereg-replay-protocol.md @ 1de64df9",
        "freeze_record": "freeze_20260710.json",
        "freeze_commit": FREEZE_COMMIT,
        "db_sha256": WORKING_DB_SHA,
        "harness": "renquant-pipeline origin/main 3e68737 (worktree, untouched)",
        "n_bars": len(bars),
        "bar_dates_first_last": [bars[0].bar_date, bars[-1].bar_date],
        "regime_counts": regime_counts,
        "fwd_horizon_days": 1,
        "conventions_cap12": conv12.to_dict(),
        "conventions_cap20": conv20.to_dict(),
        "tuned_hyperparameters": chosen,
        "n_trials_significance_family": n_trials_family,
        "arms": sorted(results.keys()),
        "incumbent_estar_source": (
            "pipeline_runs (sim run bundles): last run per session date, "
            "deployed = 1 - cash/portfolio_value, clipped [0, 0.95]"),
        "incumbent_estar_series": [float(x) for x in inc_estar],
        "gov_estar_series": [float(x) if x is not None else None
                             for x in gov_estar_series],
        "gov_fail_closed_sessions": {
            "gov_ceiling_ck": gov_ceiling.fail_closed_sessions,
            "gov_kelly_ck": gov_kelly.fail_closed_sessions,
            "gov_voltarget_ck": gov_voltgt.fail_closed_sessions,
        },
        "summary_metrics": metrics,
        "significance": significance,
        "gates": gates,
        "unit_i_paired": unit_i,
        "unit_ii_blocks_20d": unit_ii,
        "descriptive_60d": descriptive_60d,
        "incumbent_realized_sim_daily_descriptive": {
            "n": int(len(inc_daily)),
            "total_return": float(np.prod(1.0 + inc_daily) - 1.0),
            "NOTE": ("realized PV path of the incumbent sim system on the same "
                     "sessions (run bundles) — descriptive context for (c)"),
        },
        "cash_park_descriptive_tbill_overlay": {
            "convention": "cost_no_carry (project sleeve convention); overlay "
                          "reported descriptively only",
            "tbill_annual": TBILL_ANNUAL_DESCRIPTIVE,
            "eval_window_overlay_return": float(
                (1.0 + TBILL_ANNUAL_DESCRIPTIVE) ** (len(bars) / 252.0) - 1.0),
        },
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t0, 2),
    }
    OUT_EVIDENCE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"evidence written: {OUT_EVIDENCE}")

    # console summary
    cols = ["mean_deployed_fraction", "total_net_return", "sharpe_annual_net",
            "max_drawdown", "turnover_tax_ratio", "mean_session_turnover"]
    print("\narm                      " + "  ".join(f"{c[:14]:>14}" for c in cols)
          + "  gates")
    for nm in sorted(results):
        m = metrics[nm]
        print(f"{nm:<24} " + "  ".join(
            f"{(m[c] if m[c] is not None else float('nan')):>14.4f}" for c in cols)
            + f"  {'PASS' if gates[nm]['all_pass'] else 'FAIL'}")
    print(f"\nfail-closed injection: {injection}")
    print(f"runtime: {time.time()-t0:.1f}s")
    return 0


class _DummySnap:
    n = 1
    w_current = np.zeros(1)
    tickers = ("X",)


if __name__ == "__main__":
    raise SystemExit(main())
