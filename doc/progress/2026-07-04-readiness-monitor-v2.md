# Readiness monitor v2 — 4 new accumulation gates

DATE: 2026-07-04
PR: #336 (feat/readiness-monitor-v2)

## What

Expanded the readiness monitor (#332) with 4 new checks covering master plan
items that previously had no programmatic gate:

| Check | Item | Gate logic | Authoritative? |
|-------|------|-----------|---------------|
| `N1_collector_liveness` | 105 collectors live | ≥3 session dates in collector output files | No (informational) |
| `N3_fmp_coverage` | FMP harvest coverage | ≥95% of watchlist tickers in earnings parquet | Yes (when watchlist available) |
| `S_TC_baseline` | Transfer coefficient baseline | ≥10 sessions in transfer_coefficient table | Yes |
| `S8_oos_pick_table` | Track A OOS table durable | data/exp/oos_pick_table*.parquet non-empty | Yes |

Total readiness checks: 8 → 12 (covering N1, N2, N3, S5, S6, S8, S10, S-TC,
D1, M1, baseline).

## Key design choices

- N1 is informational (not authoritative) — collector liveness depends on
  machine landing, not code readiness
- N3 FMP returns UNKNOWN (non-authoritative) when no watchlist config exists
  to compute coverage against
- S-TC checks for `transfer_coefficient` table in runs.alpaca.db
- S8 verifies parquet exists, is non-empty, and has date+ticker columns

## Tests

16 new tests across 4 test classes. 2131 total passed.
