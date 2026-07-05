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

## Round 2 (Codex review — N3 authoritative false-positive)

Codex blocked on `N3_fmp_coverage`: it unioned ticker coverage across every
`earnings_*.parquet` file under `data/fmp_harvest` with no freshness or
snapshot-selection rule, so old harvest residue could keep this AUTHORITATIVE
check READY even if the current harvest were broken or missing recent names —
"has there ever existed a broad-enough parquet set" rather than "is the
current harvest healthy."

Investigated the real `data/fmp_harvest` layout (`scripts/fmp_harvest.py` in
the umbrella tree): every endpoint already writes a parquet AND a sidecar
`<key>_<N>.manifest.json` atomically, and a broken/errored pull never
overwrites the existing good parquet/manifest (partial results are quarantined
to `.staging`). This is a real, already-established manifest contract — no
new infrastructure needed.

Fixed by binding N3 to that contract instead of an all-time union:
- a parquet file is only trusted if it has a matching manifest with
  `status == "ok"` and `output` matching the parquet's own filename
- among all trusted (ok-status) parquet+manifest pairs, only the one with the
  most recent `finished_at` is used as the "current" snapshot — no more
  unioning across time periods
- the current snapshot must be within 45 days (earnings harvests run
  periodically, not daily; wide enough for normal cadence, bounded enough
  that abandoned residue can't count as current)

N1 was left unchanged per Codex's own note that its softness is acceptable
(informational/non-authoritative).

5 new regression tests, including one that reproduces Codex's exact scenario:
an old, broad, ok-status harvest (100/100 coverage) sitting alongside a
current, narrow, ok-status harvest (5/100 coverage) — confirmed the pre-fix
union logic would report READY (100% coverage from the stale file), and the
fix correctly selects only the current snapshot and reports NOT_READY (5%).
All 4 new negative-case tests confirmed to fail against the pre-fix code.

2253/2255 relevant tests pass (2 pre-existing unrelated failures in
`test_bundle_consistency_ci_gate.py` reproduce identically on clean
`origin/main`).
