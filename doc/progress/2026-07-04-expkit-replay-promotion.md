# 2026-07-04 expkit replay-experiment promotion

## What

Extracted reusable replay-experiment orchestration primitives from
`scripts/m4b_floor_replay.py` (1537 lines) into
`src/renquant_orchestrator/expkit/replay.py` (~290 lines).

## Why

The sprint goal "settle burst scripts into reusable library" identified three
patterns duplicated in the m4b floor replay that had no expkit home:

1. **Score replay loading** -- read-only DB access + canonical-run dedup.
2. **Per-arm evaluation** -- admitted-set expectancy delta, pooled stats,
   per-date aggregation, removed-set analysis.
3. **Control tests** -- iid-noise true null, within-date permutation null,
   positive-control planted-effect detection power.

Items 1-3 existed only in the 1537-line script. The matched-admission solver,
block bootstrap, and evidence stamping were already in expkit (evaluation.py,
stats.py, evidence.py).

## Shipped surface

- `expkit/replay.py`: `ReplayArm`, `ReplayBar`, `open_readonly`,
  `admitted_set`, `per_date_expectancy`, `point_delta`,
  `mean_admission_count`, `solve_arm_param`, `evaluate_arm`,
  `run_control_tests`, `replay_experiment`.
- `expkit/__init__.py`: updated imports + `__all__`.
- `tests/test_expkit_replay.py`: 16 fixture-based tests covering DB
  read-only enforcement, eligibility masking, per-date aggregation,
  point-delta computation, admission counting, parameter solving, arm
  evaluation, control tests (null rate + power monotonicity), and end-to-end
  replay orchestration.

## Design notes

- The module exposes `GateFn = Callable[[scores, ctx], mask]` so experiment
  scripts define their own floor/gate formulas without changing expkit.
- `ReplayBar.eligible` carries upstream-veto masks applied identically across
  all arms (the #147 lesson).
- `run_control_tests` follows the V3 method-note discipline: the same
  criterion function used for the verdict is exercised by both null variants
  and the positive control.
- `open_readonly` enforces `?mode=ro` mechanically.

## Not shipped

The experiment-specific pieces remain in `scripts/m4b_floor_replay.py`:
calibrator interpolation, criterion C1-C5 evaluation, baseline-report mode,
gate-check mode, horizon-scaling, and the full CLI. These are M4-b-specific
and not yet duplicated elsewhere.
