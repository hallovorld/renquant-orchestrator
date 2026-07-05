# M4-b matched-breadth conviction-floor replay harness

DATE: 2026-07-05
STATUS: implementation complete, tests passing

## What

Package-level replay harness module (`src/renquant_orchestrator/m4b_conviction_replay.py`)
for evaluating candidate conviction-floor re-derivations against the current absolute floor
at matched admission rates, per the design at
`doc/design/2026-07-03-m4b-relative-conviction-floor.md` (design section 4).

## Components

- `ReplayConfig` dataclass: candidate floor formula params (quantile_k, mad_k,
  baseline_floor, evaluation window, min_breadth, bootstrap params)
- `load_candidate_scores(db_path, start_date, end_date)`: read-only DB loader with
  canonical-run dedup and forward-returns join
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
  --baseline-floor, --n-boot, --output, --json flags

## Tests

32 tests in `tests/test_m4b_conviction_replay.py`:
- TestApplyFloorQuantile: quantile fraction, mu>0 side-condition, subset, rank, empty
- TestApplyFloorMAD: separation, zero-dispersion, mu>0 side-condition
- TestApplyFloorBaseline: admits above, rejects below
- TestMatchedBreadthCompare: structure, fields, breadth matching, empty, delta consistency
- TestBlockBootstrapCI: sufficient data CI, inadmissible small-n, single value, diff CI,
  length mismatch, CI contains mean
- TestCLI: DB run, JSON output, file output, missing DB, MAD formula, date range
- TestLoadCandidateScores: all dates, filtering, canonical dedup, forward returns, empty DB

## Design compliance

- Read-only DB access (file: URI with mode=ro)
- Matched admission rates protocol (design section 4)
- BL-4 side-condition (mu > 0) on all relative-floor candidates (design section 2)
- Uses expkit.stats block bootstrap primitives (C2/C3 bit-identical)
- V3 small-n admissibility check before bootstrap
- Block-5 primary (design section 4; M3: block-13 degenerate)
