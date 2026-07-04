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
  `canonical_runs`, `admitted_set`, `per_date_expectancy`, `point_delta`,
  `mean_admission_count`, `solve_arm_param`, `evaluate_arm`,
  `run_control_tests`, `replay_experiment`.
- `expkit/__init__.py`: updated imports + `__all__`.
- `tests/test_expkit_replay.py`: fixture-based tests covering DB
  read-only enforcement, canonical-run dedup (latest `created_at` per date,
  `min_candidates` threshold, `run_type='live'` filter), eligibility masking,
  per-date aggregation, point-delta computation, admission counting,
  parameter solving, arm evaluation, control tests (null rate + power
  monotonicity), and end-to-end replay orchestration.

## Round 2 (codex re-review)

Codex re-blocked this PR: the module docstring and this doc's own "Item 1"
claimed the extraction covered "canonical-run dedup discipline," but the
shipped surface at the time only had `open_readonly` (a bare read-only
connection opener) -- the actual dedup query (`canonical_runs()`: one live
run per date, latest `created_at`, `min_candidates` threshold on
`score_distribution.raw_panel`) was still living exclusively in
`scripts/m4b_floor_replay.py`. The documented claim was ahead of the code.

Fixed by choosing option (a) from the review -- actually extracting the
dedup logic, not just narrowing the docs -- since `canonical_runs()` has no
burst-script-specific coupling (it's a pure SQL query against `con` plus a
caller-supplied `min_candidates`):

- Moved the SQL query verbatim into `expkit/replay.py::canonical_runs()`.
  `min_candidates` is a required (non-defaulted) parameter there -- the
  "how many candidates make a run usable" threshold is experiment-specific
  tuning, not a property of the dedup rule itself.
- `scripts/m4b_floor_replay.py::canonical_runs()` is now a thin forwarding
  wrapper: it keeps its own local `MIN_FULL_RUN_CANDIDATES = 40` default
  (M4b-specific) and calls `expkit.replay.canonical_runs` for the actual
  query. No behavior change for existing callers.
- Added `test_canonical_runs_dedup_latest_full` and
  `test_canonical_runs_min_candidates_threshold` to
  `tests/test_expkit_replay.py` against a synthetic fixture DB (same-date
  dedup-to-latest, threshold filtering, `run_type` filtering). The
  pre-existing `test_canonical_runs_dedup_latest_full` in
  `tests/test_m4b_floor_replay.py` still passes unchanged, now exercising
  the forwarding wrapper.
- Full suite: 1930 passed, 3 skipped, zero regressions.

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
