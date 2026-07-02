# Scorecard: unique-session admissible ledger coverage (S5 companion)

Date: 2026-07-02. Companion to renquant-backtesting#60 (S5 forward-returns
as-of backfill), review requirement: "The scorecard should report both raw
row coverage and unique-session admissible coverage."

## Why

The S5 as-of backfill makes weekend/holiday-dated live decision rows join a
forward outcome resolved from the preceding NYSE session. Those rows share
that session's market realization: raw row coverage counts a Fri+Sat
duplicate cohort twice, so coverage gains from weekend rows are storage
coverage, not additional independent evidence. Measured on the live DB copy
(aged <= 2026-05-28): 5,199 raw rows / 792 unique (ticker, session)
realizations; 103 clusters span more than one run_date.

## What changed

`scripts/kpi_scorecard.py` `metric_ledger_coverage`:

- `value` unchanged (raw row coverage; backward compatible).
- New detail fields: `admissible_coverage_pct` (share of unique
  (ticker, NYSE-session) clusters with a covered row), and
  `n_unique_ticker_sessions`, `n_non_session_rows`, `session_calendar`.
- Session key = last NYSE session at or before run_date — the same
  pure-date rule as backtesting `analysis/session_resolution.py`
  (`pandas_market_calendars` NYSE; weekday fallback rolls Sat/Sun to Friday
  and is flagged `weekday_fallback` because weekday holidays are then
  undetectable).
- Markdown renderer prints both coverages.

Measured on the post-backfill live DB copy: raw 97.2%, admissible 98.0% —
both clear the >=95% S5 AC.

## Cross-repo ledger

- renquant-backtesting#60: writer + in-repo consumers (weighted inference).
- renquant-pipeline#158: QP replay / Gate-B exposure (865 weekend
  score_distribution mu-rows), filed with fix path; schema-owner side.

Tests: 2 new in `tests/test_kpi_scorecard.py` (weekend cohort raw vs
admissible; session-key weekend rolling). Full suite 1250 passed / 3
skipped.
