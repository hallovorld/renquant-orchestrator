# Wire all remaining entry-point modules into CLI

**Date:** 2026-07-05
**Status:** Ready for review
**Supersedes:** #375, #376, #377, #378, #379, #380, #381, #382

## Summary

Consolidates 8 separate wiring PRs into one to avoid serial merge conflicts
on `cli.py` and `strategy_snapshot.json`. All modules with `main()` entry
points that were unreachable from the CLI are now wired.

## New CLI subcommands (9 total)

| Subcommand | Module | Sprint area |
|---|---|---|
| `parking-sleeve` | `parking_sleeve` | S7 cash-drag |
| `transfer-coefficient` | `transfer_coefficient` | S-TC evidence |
| `readiness-monitor` | `readiness_monitor` | ops/105 |
| `edgar-harvest` | `sec_edgar_harvester` | N3 data |
| `entry-timing` | `entry_timing_policy` | 105 entry |
| `train-gbdt` | `train_gbdt` | training |
| `patchtst-cutoff` | `patchtst_weekly_cutoff` | training |
| `replay-audit` | `intraday_replay_audit` | 105 audit |
| `risk-budget-report` | `risk_budget.report` | 107 risk |

## New scheduled jobs (2)

- `parking_sleeve_shadow` — daily parking-sleeve shadow allocation
- `readiness_monitor` — daily data-accumulation readiness check

## Test results

2889 passed, 2 skipped, 0 failures.
