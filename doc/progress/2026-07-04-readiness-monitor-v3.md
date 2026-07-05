# Readiness monitor v3 — freshness-gated N3 + 3 new checks

DATE: 2026-07-04
PR: supersedes #336
MODULES: `readiness_monitor.py`

## What changed

Added 4 new readiness checks (8 → 12 total), with the N3 freshness fix
requested by Codex review on #336:

| Check | Gate | Authoritative | Key change from #336 |
|-------|------|---------------|---------------------|
| N1_collector_liveness | 105 collector outputs | No (informational) | Staleness note only, no READY regression |
| N3_fmp_coverage | FMP harvest ≥95% watchlist | Yes (when watchlist available) | **Evaluates ONLY the latest file + staleness gate (14d)** — not an all-time union |
| S_TC_baseline | TC measurements ≥10 sessions | Yes | No change from #336 |
| S8_oos_pick_table | Track A OOS table exists | Yes | No change from #336 |

### N3 freshness fix (Codex #336 review finding)

The original N3 check unioned ticker coverage across ALL `earnings_*.parquet`
files in `data/fmp_harvest/`, meaning stale historical residue could satisfy
the readiness gate indefinitely. Fixed to:

1. Evaluate only the LATEST file (by filename sort)
2. Require that file to be ≤14 days old (staleness gate)
3. STALE files produce NOT_READY regardless of coverage

Added explicit `test_only_latest_file_evaluated` and `test_stale_harvest_fails`
tests to prevent regression.

## Tests

- 22 new tests across 4 test classes
- All 2255 tests passing
