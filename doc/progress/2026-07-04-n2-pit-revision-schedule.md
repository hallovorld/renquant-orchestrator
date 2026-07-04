# N2: PIT estimate-revision snapshot scheduling

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan task**: N2 — PIT revision accrual starts (time-irreversible)

## What

Orchestrator scheduling wrapper for the `renquant_base_data.fmp_estimate_revisions`
collector (base-data PR #27, merged 2026-06-30). Each daily invocation appends one
day's analyst estimate snapshot to the PIT revision lake; missed days are permanently
lost (the whole point of N2).

## Components

1. **`pit_revision_collector.py`** (~165 lines):
   - `collect_snapshot()`: invokes the base-data collector via subprocess with
     subrepo PYTHONPATH, records SHA-256 content fingerprint + provenance sidecar
   - `check_freshness()`: verifies the PIT lake has a recent snapshot within
     `max_gap_days` (default 2)
   - CLI with `--dry-run`, `--check-freshness`, `--universe` override

2. **Job dispatcher**: added `daily_pit_revision_snapshot` to `job_runner.py`

3. **Scheduled job inventory**: added entry to `scheduled_jobs.py` with
   `cadence=daily`, `kind=ops`, `production_safe=True`

## What this does NOT do

- Does not create launchd plists (landing action → operator ask-first)
- Does not write to canonical production data paths (writes to `data/pit/`)
- Does not import from `renquant-base-data` directly (subprocess isolation)

## Tests

12 tests covering: dry run, collector invocation, error handling, universe override,
freshness checks (missing/empty/recent/stale), CLI modes, inventory/dispatcher wiring.
All 1925 tests pass.
