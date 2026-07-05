# M4-b matched-breadth conviction-floor replay harness

DATE: 2026-07-05 (round 2: same day, Codex calibration-gap fix + CLI guard addendum)
STATUS: implementation complete, tests passing

## What

Package-level replay harness module (`src/renquant_orchestrator/m4b_conviction_replay.py`)
for evaluating candidate conviction-floor re-derivations against the current absolute floor
at matched admission rates, per the design at
`doc/design/2026-07-03-m4b-relative-conviction-floor.md` (design section 4).

## Round 2 (2026-07-05): Codex review — calibration gap

**Codex's finding (CONFIRMED on read of round-1 code):** `ReplayConfig` accepted
`quantile_k`/`mad_k` as fixed external inputs, `apply_floor` used them directly with no
search step, and `matched_breadth_compare` only truncated each day's candidate-admitted set
to that day's baseline count (`cand_names.head(n_base)`) — a per-day post-hoc truncation,
not a parameter calibration. The design doc's own frozen protocol (section 4) is explicit:
*"Each candidate's single parameter is set ONCE, on the replay window, such that its mean
floor-clearing count equals B (±0.5). Per-bar counts may differ ...; means may not. **No
per-bar re-tuning.**"* Round 1 implemented neither half of that: no global parameter search,
and the per-day truncation is itself the literal "per-bar re-tuning" the design prohibits.
Any return delta from round 1 was confounded with whatever admission rate an
arbitrarily-chosen k happened to produce that day — exactly Codex's concern.

**Fix implemented (Option 1: genuine calibration, not claim-narrowing).** Both candidate
formulas' k-to-breadth relationship is monotonic and searchable from data already loaded by
the harness (quantile: larger k → lower threshold quantile → monotonically MORE admitted;
MAD: larger k → higher threshold → monotonically FEWER admitted), so a bisection search is
tractable:
- `calibrate_parameter(scores_df, config, tol=BREADTH_TOL, max_iter=100)`: binary search
  (bounds 0.01–0.99 for quantile_k, 0.01–5.0 for mad_k) for the parameter value whose mean
  per-day admitted count matches the baseline's mean admitted count within `tol`. Raises
  `ValueError` if it fails to converge within `max_iter` — a hard failure rather than a
  silent best-effort, consistent with this repo's "no silent skip" posture.
- CLI `--calibrate`: when combined with `--quantile-k` or `--mad-k` (used only to pick
  which formula to calibrate; the value itself is replaced by the search), runs the
  calibrated matched-breadth protocol end to end and reports `"calibrated": true` in the
  JSON output. Without `--calibrate`, the harness runs in exploratory mode at the fixed
  parameter (unchanged round-1 behavior, now honestly the *non-default* path).
- 4 new tests (`TestCalibrateParameter`): quantile/MAD calibration hits target breadth
  within tolerance, calibration raises on empty data, calibrated k stays positive.

**Race condition note:** a concurrent session (different `Claude-Session` ID, commit
`6a16a78f`) implemented and pushed this exact fix to `feat/m4b-conviction-replay` while this
session was independently implementing an equivalent bisection-based calibration
(`calibrate_k`/`mean_baseline_breadth`/`--formula`). Both approaches were verified correct
(same monotonicity argument, same direction-of-search logic, same convergence behavior on
synthetic data). Rather than force-push a redundant, functionally-duplicate implementation
over an already-pushed working fix, this session deferred to the upstream commit, verified
it independently (full test suite green, `calibrate_parameter` confirmed absent in the
pre-fix commit via direct `git show`), and added one small addendum on top (see below)
rather than reimplementing.

**Addendum found during independent verification:** `--calibrate` passed *without* either
`--quantile-k` or `--mad-k` silently fell through to `apply_floor`'s "no candidate formula
specified" branch, which sets `admitted_candidate = admitted_baseline` — i.e. a baseline
compared against itself, with `"calibrated": false` in the output but no error. Reproduced
directly against the fix as pushed: `--calibrate --json` alone returns `rc=0` with
`mean_candidate_breadth == mean_baseline_breadth` exactly. Added a guard in `main()`: if
`--calibrate` is given with neither `--quantile-k` nor `--mad-k` set, the CLI now exits 1
with an explicit error naming the fix, instead of silently emitting a placebo comparison.
One regression test (`test_cli_calibrate_without_formula_errors`) added, confirmed to fail
(rc=0, no error) against the code prior to this guard.

**Verification:**
- Full `tests/test_m4b_conviction_replay.py`: 37 passed (36 from the upstream fix + 1 new
  guard test).
- Full repo test suite: 2925+ passed, 3 skipped, 2 pre-existing failures in
  `test_bundle_consistency_ci_gate.py` unrelated to this module (reproduce on `main`).
- `calibrate_parameter` confirmed absent from the pre-fix commit (`27806323`) via
  `git show <sha>:path | grep -c calibrate_parameter` → 0.

## Components

- `ReplayConfig` dataclass: candidate floor formula params (quantile_k, mad_k,
  baseline_floor, evaluation window, min_breadth, bootstrap params)
- `load_candidate_scores(db_path, start_date, end_date)`: read-only DB loader with
  canonical-run dedup and forward-returns join
- `calibrate_parameter(scores_df, config, tol, max_iter)`: bisection search for the
  quantile_k/mad_k matching baseline mean breadth within tolerance (round 2)
- `apply_floor(scores_df, config)`: applies candidate (a) quantile / (b) MAD /
  baseline absolute floor formulas to daily cross-sections, enforcing BL-4 mu>0
  side-condition on all relative candidates
- `matched_breadth_compare(admitted_df)`: matches candidate admitted set to baseline
  breadth per day (top-N by mu where N = baseline count), computes per-day mean forward
  returns for both arms
- `block_bootstrap_ci(daily_returns)`: block bootstrap CI via expkit.stats primitives
  (gap-respecting block bootstrap, V3 small-n admissibility check)
- `block_bootstrap_diff_ci(base, cand)`: paired-difference bootstrap CI
- `main(argv)` CLI: argparse with --db, --start-date, --end-date, --quantile-k, --mad-k,
  --calibrate (round 2 — runs the matched-breadth protocol; requires --quantile-k or
  --mad-k to select the formula, guarded against silent no-op, round 2 addendum),
  --baseline-floor, --n-boot, --output, --json flags

## Tests

37 tests in `tests/test_m4b_conviction_replay.py`:
- TestApplyFloorQuantile: quantile fraction, mu>0 side-condition, subset, rank, empty
- TestApplyFloorMAD: separation, zero-dispersion, mu>0 side-condition
- TestApplyFloorBaseline: admits above, rejects below
- TestMatchedBreadthCompare: structure, fields, breadth matching, empty, delta consistency
- TestBlockBootstrapCI: sufficient data CI, inadmissible small-n, single value, diff CI,
  length mismatch, CI contains mean
- TestCLI: DB run, JSON output, file output, missing DB, MAD formula, date range,
  --calibrate without a formula errors instead of silently no-op'ing (round 2 addendum)
- TestLoadCandidateScores: all dates, filtering, canonical dedup, forward returns, empty DB
- TestCalibrateParameter (round 2): quantile calibration hits target breadth, MAD
  calibration hits target breadth, raises on empty data, calibrated k stays positive

## Design compliance

- Read-only DB access (file: URI with mode=ro)
- Matched admission rates protocol (design section 4): parameter calibrated ONCE via
  bisection to match baseline mean breadth within ±0.5 (round 2 — was previously unmet)
- BL-4 side-condition (mu > 0) on all relative-floor candidates (design section 2)
- Uses expkit.stats block bootstrap primitives (C2/C3 bit-identical)
- V3 small-n admissibility check before bootstrap
- Block-5 primary (design section 4; M3: block-13 degenerate)
