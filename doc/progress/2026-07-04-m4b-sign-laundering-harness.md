# M4-b: Sign-Laundering Measurement Harness

**Date:** 2026-07-04
**Sprint:** 2026-07-03 ~ 07-06 (105/106/107 engineering)
**Branch:** feat/m4b-sign-laundering-harness

## What

Measurement harness for sign laundering: names whose raw scores lie between
the calibrator's neutral point (~-0.29) and 0 receive calibrated mu of the
OPPOSITE sign. On 2026-07-01, 44/90 names (49%) were sign-laundered.

## Deliverables

- `sign_laundering_harness.py` — `measure_sign_laundering()` (single artifact)
  and `audit_laundering_history()` (DB time-series), CLI with `measure` and
  `history` subcommands, exit code 1 if laundering rate > 10%
- 25 tests covering calibrator neutral detection, score estimation, laundering
  measurement, DB history audit, and CLI
- CLI wiring: `renquant-orchestrator sign-laundering measure|history`

## Key decisions

- Read-only: never modifies scorer, calibrator, or DB artifacts
- Neutral-raw auto-detection from calibrator breakpoints, intercept/slope, or
  cross-ticker score interpolation (3-level fallback)
- DB pattern matches `transfer_coefficient.py` (read-only URI connection)
- Exit code 1 threshold at 10% laundering rate (current rate ~49%)

## References

- Master plan: M4 (sign-laundering measurement) in sprint plan
- Root cause: calibrator neutral at ~-0.29, not 0; scores in (-0.29, 0) get
  sign-flipped mu through piecewise-linear calibration

## Round 2 (Codex review — two substantive measurement-validity bugs)

Codex blocked on `audit_laundering_history()` (the DB time-series path;
`measure_sign_laundering()`, the single-artifact path, was not implicated):

1. **Wrong input field.** The SQL query read `candidate_scores.rank_score`.
   Confirmed directly against the live DB schema
   (`sqlite3 runs.alpaca.db ".schema candidate_scores"`) that this table has
   BOTH `raw_score` and `rank_score` as distinct columns — `raw_score` is
   the actual calibrator input axis (`doc/research/2026-06-27-...md` ties
   `raw_score` directly to "PatchTST is intrinsically negative ~-0.198");
   `rank_score` is a different, rank-transformed field that never goes
   through the calibration curve. Fixed: query now reads `cs.raw_score`.
2. **Sample-dependent neutral-raw baseline.** The history path re-derived a
   "neutral point" from each day's own candidate cross-section via
   `_estimate_neutral_raw_from_scores()` — a threshold that drifts with
   whatever happens to be in that day's sample, which can hide or reshape
   the very laundering being measured. Fixed: added `calibrator_path` /
   `neutral_raw_override` params so the neutral reference can be bound to
   ONE stable, external source (the real calibrator's ER=0 crossing, or an
   explicit override) shared across every day in the series. Falls back to
   per-run estimation only when neither is given, and now explicitly tags
   each record's `neutral_raw_source` ("calibrator" / "override" /
   "per_run_estimate") plus a rendered-text warning, so an unstable
   measurement is never silently indistinguishable from a stable one.

**Also fixed as a prerequisite**: `_find_neutral_raw_from_calibrator()`
itself was reading a fabricated schema (`breakpoints` /
`calibration_breakpoints` / `intercept`+`slope`) that does not match any
real calibrator artifact. Verified the actual schema directly against a
live artifact (`panel-rank-calibration.alpha158_linear.json`):
`expected_return: {"x": [...], "y": [...]}`. Rewrote the reader to match
this real schema, using the same ER=0 zero-crossing rule as
`scripts/m4b_floor_replay.py::Calibrator.neutral_raw` (scan from the
low-raw end; exact-zero knot returns that knot; strict sign change
interpolates; never-crossing returns `None`) — that rule is itself
V5-verified (#272) against the pipeline's calibration logic. Without this
fix, calibrator-path binding for either function would have silently
returned `None` on every real artifact and fallen straight through to the
unstable per-run estimate anyway.

**Impact, demonstrated against the real live DB** (read-only,
`runs.alpaca.db`, last 10 `run_type='live'` runs): with the pre-fix
per-run-estimate baseline, reported laundering rates for 2026-06-29
through 2026-07-02 ranged 7.0%-23.3% and the "neutral point" itself moved
from -0.10 to -0.30 run to run. Re-running the identical window bound to
`panel-rank-calibration.alpha158_linear.json`'s stable calibrator anchor
(neutral_raw = -0.0328, constant across all 10 runs) instead reports
2.3%-3.6% — roughly a 5-10x difference, in the direction codex's review
warned about (the sample-dependent threshold was inflating the apparent
laundering rate). Note this specific calibrator artifact is used here only
to demonstrate the fix mechanism and is not necessarily the exact
calibrator that produced this doc's original "44/90 (49%)" headline figure
— that number came from `measure_sign_laundering()` (the single-artifact
path, unaffected by this round's bugs), not from `audit_laundering_history()`.

23 existing tests plus 2 new regression tests (raw_score-vs-rank_score
divergence, calibrator-bound stability across differing cross-sections) —
both confirmed to fail against the pre-fix code and pass after. 27/27 tests
pass.
