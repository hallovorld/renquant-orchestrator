"""Replay-experiment orchestration: the reusable arm-vs-arm evaluation pattern.

Extracted from ``scripts/m4b_floor_replay.py`` -- the load -> match -> evaluate
-> control -> stamp pipeline that every arm-vs-arm experiment follows.
Experiment-specific logic (floor formulas, criteria, calibrator interpolation)
stays in the experiment script; this module provides the orchestration skeleton
and the reusable primitives.

The three pieces that were duplicated across burst scripts and are now
consolidated:

1. **Score replay loading** -- read-only DB access with the canonical-run dedup
   discipline (latest created_at among a date's full runs).
2. **Per-arm evaluation** -- admitted-set expectancy, pooled delta, per-date
   aggregation, and removed-set statistics.
3. **Control tests** -- iid-noise true null, within-date permutation null, and
   positive-control planted-effect detection power.

Items already in expkit that this module composes:
- ``evaluation.solve_matched_admission`` -- the bisection solver
- ``stats.bootstrap_or_exact`` -- the automatic small-n branch
- ``evidence.build_manifest`` / ``write_evidence`` -- stamping
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from renquant_orchestrator.expkit.evaluation import (
    MatchedAdmission,
    solve_matched_admission,
)

__all__ = [
    "ReplayArm",
    "ReplayBar",
    "admitted_set",
    "canonical_runs",
    "evaluate_arm",
    "mean_admission_count",
    "open_readonly",
    "per_date_expectancy",
    "point_delta",
    "replay_experiment",
    "run_control_tests",
    "solve_arm_param",
]

# Gate function signature: (scores, bar_context) -> boolean mask.
# bar_context carries {"date", "run_id", "eligible", "meta"} so the gate
# can inspect regime/era/etc without coupling to the Bar's full surface.
GateFn = Callable[[np.ndarray, dict[str, Any]], np.ndarray]


# ---------------------------------------------------------------------- types


@dataclass
class ReplayArm:
    """Configuration for one arm of a replay experiment.

    ``gate_fn(scores, ctx) -> bool_mask`` defines which names the arm admits
    on a given bar.  ``param`` is the single free parameter solved by the
    matched-admission protocol; ``param_bounds`` and ``param_increasing``
    configure the bisection solver.
    """

    name: str
    label: str
    gate_fn: GateFn
    param: float | None = None
    is_baseline: bool = False
    param_bounds: tuple[float, float] | None = None
    param_increasing: bool = True


@dataclass
class ReplayBar:
    """One scored bar (date) in a replay experiment."""

    date: str
    run_id: str
    tickers: list[str]
    scores: np.ndarray
    outcomes: np.ndarray | None = None
    eligible: np.ndarray | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------- DB helpers


def open_readonly(db_path: str) -> sqlite3.Connection:
    """Open a sqlite DB in strict read-only mode.

    The file: URI with ``?mode=ro`` is the mechanical enforcement -- the
    harness must never mutate the trade DB (CLAUDE.md hard boundary).
    """
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def canonical_runs(con: sqlite3.Connection, min_candidates: int) -> list[dict]:
    """One canonical live run per date: latest ``created_at`` among that
    date's runs with >= ``min_candidates`` scored candidate rows carrying
    ``raw_panel`` (the M3/#234 dedup discipline -- ported verbatim from
    ``scripts/m4b_floor_replay.py`` so every arm-vs-arm replay experiment
    shares one dedup implementation instead of hand-copying it per script).

    ``min_candidates`` is caller-owned (experiment-specific threshold
    tuning), not defaulted here -- the "how many candidates make a run
    usable" number is a property of the experiment, not of the dedup rule.
    """
    rows = con.execute(
        """
        SELECT p.run_id, p.run_date, COALESCE(p.regime,'UNKNOWN'), p.created_at,
               COALESCE(p.counters_json, '')
        FROM pipeline_runs p
        WHERE p.run_type='live'
          AND (SELECT COUNT(*) FROM score_distribution s
               WHERE s.run_id=p.run_id AND s.is_holding=0
                 AND s.raw_panel IS NOT NULL) >= ?
        ORDER BY p.run_date, p.created_at
        """,
        (min_candidates,),
    ).fetchall()
    by_date: dict[str, tuple] = {}
    for run_id, run_date, regime, created_at, counters in rows:
        by_date[run_date] = (run_id, regime, created_at, counters)
    out = []
    for d, (run_id, regime, _c, counters) in sorted(by_date.items()):
        try:
            counters_d = json.loads(counters) if counters else {}
        except (ValueError, TypeError):
            counters_d = {}
        out.append({"run_date": d, "run_id": run_id, "regime": regime,
                    "counters": counters_d})
    return out


# -------------------------------------------------------------- core primitives


def admitted_set(arm: ReplayArm, bar: ReplayBar) -> np.ndarray:
    """Boolean admission mask for an arm on one bar.

    Composes the arm's gate function with the bar's upstream-eligibility mask
    (upstream vetoes are excluded from every arm identically -- the #147
    lesson).
    """
    ctx: dict[str, Any] = {
        "date": bar.date,
        "run_id": bar.run_id,
        "eligible": bar.eligible,
        "meta": bar.meta,
    }
    mask = arm.gate_fn(bar.scores, ctx)
    if bar.eligible is not None:
        mask = mask & bar.eligible
    return mask


def per_date_expectancy(
    bars: Sequence[ReplayBar],
    baseline_arm: ReplayArm,
    candidate_arm: ReplayArm,
) -> tuple[list[str], np.ndarray]:
    """Per-date ``[sum_base, n_base, sum_cand, n_cand]`` for resolved outcomes.

    Returns ``(sorted_dates, agg_array)`` where ``agg_array`` has shape
    ``(n_dates, 4)``.  Dates with no resolved outcome for either arm are
    excluded.
    """
    agg: dict[str, list[float]] = {}
    for bar in bars:
        if bar.outcomes is None:
            continue
        ok = np.isfinite(bar.outcomes)
        mb = admitted_set(baseline_arm, bar) & ok
        mc = admitted_set(candidate_arm, bar) & ok
        if not (mb.any() or mc.any()):
            continue
        a = agg.setdefault(bar.date, [0.0, 0.0, 0.0, 0.0])
        a[0] += float(bar.outcomes[mb].sum())
        a[1] += float(mb.sum())
        a[2] += float(bar.outcomes[mc].sum())
        a[3] += float(mc.sum())
    dates = sorted(agg)
    arr = np.asarray([agg[d] for d in dates], dtype=float) if dates else np.empty((0, 4))
    return dates, arr


def point_delta(agg: np.ndarray) -> float | None:
    """Pooled expectancy difference: candidate mean - baseline mean."""
    if agg.size == 0:
        return None
    totals = agg.sum(axis=0)
    sum_b, n_b, sum_c, n_c = totals
    if n_b == 0 or n_c == 0:
        return None
    return float(sum_c / n_c - sum_b / n_b)


def _pool_stats(pool: np.ndarray) -> dict[str, Any]:
    fin = pool[np.isfinite(pool)] if len(pool) > 0 else np.array([])
    n = int(len(fin))
    return {"n": n, "mean": float(fin.mean()) if n > 0 else None}


# -------------------------------------------------------------- evaluation


def mean_admission_count(
    bars: Sequence[ReplayBar],
    arm: ReplayArm,
) -> float:
    """Mean per-bar admission count for an arm."""
    counts = [float(admitted_set(arm, bar).sum()) for bar in bars]
    return float(np.mean(counts)) if counts else 0.0


def solve_arm_param(
    bars: Sequence[ReplayBar],
    arm: ReplayArm,
    target_breadth: float,
    *,
    tol: float = 0.5,
    max_iter: int = 200,
) -> MatchedAdmission:
    """Solve arm's single parameter to match baseline admission breadth.

    Delegates to ``expkit.evaluation.solve_matched_admission`` (bisection on
    the integer-step admission-count function).  The solved parameter is
    written back to ``arm.param``.
    """
    if arm.param_bounds is None:
        raise ValueError(f"arm {arm.name!r} has no param_bounds set")
    lo, hi = arm.param_bounds

    def admission_fn(param: float) -> float:
        arm.param = param
        return mean_admission_count(bars, arm)

    result = solve_matched_admission(
        admission_fn,
        target_breadth,
        lo,
        hi,
        increasing=arm.param_increasing,
        tol=tol,
        max_iter=max_iter,
    )
    arm.param = result.param
    return result


def evaluate_arm(
    bars: Sequence[ReplayBar],
    baseline_arm: ReplayArm,
    candidate_arm: ReplayArm,
) -> dict[str, Any]:
    """Evaluate one candidate arm against the baseline.

    Returns pooled expectancy stats for both arms, the removed set
    (baseline-admitted but not candidate-admitted), the point delta, and the
    raw per-date aggregation array (for downstream bootstrap/exact tests).
    """
    base_pools: list[np.ndarray] = []
    cand_pools: list[np.ndarray] = []
    removed_pools: list[np.ndarray] = []
    for bar in bars:
        if bar.outcomes is None:
            continue
        ok = np.isfinite(bar.outcomes)
        bm = admitted_set(baseline_arm, bar) & ok
        cm = admitted_set(candidate_arm, bar) & ok
        base_pools.append(bar.outcomes[bm])
        cand_pools.append(bar.outcomes[cm])
        removed_pools.append(bar.outcomes[bm & ~cm])

    base_pool = np.concatenate(base_pools) if base_pools else np.array([])
    cand_pool = np.concatenate(cand_pools) if cand_pools else np.array([])
    removed_pool = np.concatenate(removed_pools) if removed_pools else np.array([])

    dates, agg = per_date_expectancy(bars, baseline_arm, candidate_arm)
    delta = point_delta(agg)

    return {
        "arm": candidate_arm.name,
        "param": candidate_arm.param,
        "baseline": _pool_stats(base_pool),
        "candidate": _pool_stats(cand_pool),
        "removed": _pool_stats(removed_pool),
        "expectancy_delta": delta,
        "n_resolved_dates": len(dates),
        "dates": dates,
        "per_date_agg": agg,
    }


# -------------------------------------------------------------- controls


def run_control_tests(
    bars: Sequence[ReplayBar],
    baseline_arm: ReplayArm,
    candidate_arm: ReplayArm,
    *,
    criterion_fn: Callable[[list[str], np.ndarray], bool],
    n_reps: int = 200,
    noise_sigma: float | None = None,
    planted_gaps: Sequence[float] = (0.02, 0.04, 0.08),
    seed: int = 42,
) -> dict[str, Any]:
    """Positive-control (planted effect) + true-null control tests.

    ``criterion_fn(dates, per_date_agg) -> bool`` is the verdict criterion
    under test -- typically wrapping a significance check (exact tail mass or
    bootstrap CI).

    Two true-null variants:
      * **iid noise**: outcomes are pure N(0, sigma), independent of admission.
      * **Within-date permutation**: the bar's REAL excess values are permuted
        across its names, breaking the admission->outcome link while preserving
        each date's marginal distribution.

    Positive control: a symmetric +/- gap/2 effect is planted on names
    exclusively in the candidate / baseline admitted sets.
    """
    if noise_sigma is None:
        pool: list[np.ndarray] = []
        for bar in bars:
            if bar.outcomes is not None:
                pool.append(bar.outcomes[np.isfinite(bar.outcomes)])
        pooled = np.concatenate(pool) if pool else np.array([])
        noise_sigma = float(pooled.std()) if len(pooled) >= 30 else 0.06

    base_masks = {bar.date: admitted_set(baseline_arm, bar) for bar in bars}
    cand_masks = {bar.date: admitted_set(candidate_arm, bar) for bar in bars}

    def _eval_synthetic(excess_by_date: dict[str, np.ndarray]) -> bool:
        agg_dict: dict[str, list[float]] = {}
        for bar in bars:
            ex = excess_by_date.get(bar.date)
            if ex is None:
                continue
            ok = np.isfinite(ex)
            mb = base_masks[bar.date] & ok
            mc = cand_masks[bar.date] & ok
            if not (mb.any() or mc.any()):
                continue
            a = agg_dict.setdefault(bar.date, [0.0, 0.0, 0.0, 0.0])
            a[0] += float(ex[mb].sum())
            a[1] += float(mb.sum())
            a[2] += float(ex[mc].sum())
            a[3] += float(mc.sum())
        dates = sorted(agg_dict)
        if not dates:
            return False
        agg = np.asarray([agg_dict[d] for d in dates], dtype=float)
        return criterion_fn(dates, agg)

    # True-null: iid noise
    rng = np.random.default_rng(seed)
    null_fires = sum(
        _eval_synthetic(
            {bar.date: rng.normal(0.0, noise_sigma, size=len(bar.tickers)) for bar in bars}
        )
        for _ in range(n_reps)
    )

    # True-null: within-date permutation of real outcomes
    rng_perm = np.random.default_rng(seed + 500)
    perm_fires, perm_valid = 0, 0
    for _ in range(n_reps):
        exs: dict[str, np.ndarray] = {}
        any_real = False
        for bar in bars:
            if bar.outcomes is None or not np.isfinite(bar.outcomes).any():
                continue
            any_real = True
            ex = np.array(bar.outcomes, dtype=float)
            idx = np.flatnonzero(np.isfinite(ex))
            ex[idx] = ex[idx][rng_perm.permutation(len(idx))]
            exs[bar.date] = ex
        if any_real:
            perm_valid += 1
            perm_fires += _eval_synthetic(exs)

    # Positive control: planted symmetric effect
    power: dict[str, float] = {}
    for gi, gap in enumerate(planted_gaps):
        rng_pos = np.random.default_rng(seed + 1000 + gi)
        detections = 0
        for _ in range(n_reps):
            exs_planted: dict[str, np.ndarray] = {}
            for bar in bars:
                ex = rng_pos.normal(0.0, noise_sigma, size=len(bar.tickers))
                only_cand = cand_masks[bar.date] & ~base_masks[bar.date]
                only_base = base_masks[bar.date] & ~cand_masks[bar.date]
                ex = ex + gap / 2.0 * only_cand - gap / 2.0 * only_base
                exs_planted[bar.date] = ex
            detections += _eval_synthetic(exs_planted)
        power[f"gap_{gap:g}"] = detections / n_reps

    return {
        "noise_sigma": noise_sigma,
        "n_reps": n_reps,
        "true_null_false_fire_rate_iid": null_fires / n_reps,
        "true_null_false_fire_rate_perm": (perm_fires / perm_valid if perm_valid > 0 else None),
        "positive_control_power": power,
    }


# ------------------------------------------------------------- orchestrator


def replay_experiment(
    bars: Sequence[ReplayBar],
    baseline_arm: ReplayArm,
    candidate_arms: Sequence[ReplayArm],
    *,
    criterion_fn: Callable[[list[str], np.ndarray], bool] | None = None,
    breadth_tol: float = 0.5,
    control_reps: int = 0,
    control_seed: int = 42,
    control_gaps: Sequence[float] = (0.02, 0.04, 0.08),
) -> dict[str, Any]:
    """Full replay-experiment orchestrator: match -> evaluate -> control.

    Steps:
      1. Measure baseline admission breadth.
      2. Solve each candidate's parameter to match baseline breadth
         (only for arms with ``param_bounds`` set).
      3. Evaluate each candidate vs baseline.
      4. Run controls (if ``criterion_fn`` provided and ``control_reps > 0``).

    Returns a dict with ``target_breadth``, ``solves``, ``evaluations``, and
    ``controls`` keyed by arm name.
    """
    target_b = mean_admission_count(bars, baseline_arm)

    solves: dict[str, dict[str, Any]] = {}
    evaluations: dict[str, dict[str, Any]] = {}
    controls: dict[str, dict[str, Any]] = {}

    for arm in candidate_arms:
        if arm.param_bounds is not None:
            result = solve_arm_param(bars, arm, target_b, tol=breadth_tol)
            solves[arm.name] = {
                "param": result.param,
                "achieved": result.achieved,
                "target": result.target,
                "converged": result.converged,
                "iterations": result.iterations,
            }

        evaluations[arm.name] = evaluate_arm(bars, baseline_arm, arm)

        if criterion_fn is not None and control_reps > 0:
            controls[arm.name] = run_control_tests(
                bars,
                baseline_arm,
                arm,
                criterion_fn=criterion_fn,
                n_reps=control_reps,
                planted_gaps=control_gaps,
                seed=control_seed,
            )

    return {
        "target_breadth": target_b,
        "n_bars": len(bars),
        "solves": solves,
        "evaluations": evaluations,
        "controls": controls if controls else None,
    }
