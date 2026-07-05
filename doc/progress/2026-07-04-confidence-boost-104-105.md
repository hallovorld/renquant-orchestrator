# Confidence boost: 104/105 data pipeline wiring

**Date:** 2026-07-04
**PR:** feat/confidence-boost-104-105

## What

Two new modules that close data-pipeline wiring gaps blocking the S5 and S6
readiness checks:

1. **outcome_backfiller** — populates `decision_outcomes` from
   `candidate_scores` + `ticker_forward_returns` (bridges runs.alpaca.db →
   decision_ledger.db). This unblocks:
   - S5 readiness check (fwd-outcome join coverage)
   - `decision_outcome_validator` running on real data
   - `gate_value_report` and `gate_information_value` queries

2. **config_experiment_store** — DDL + writer/reader for
   `config_experiments` table. This is the storage layer the S6 lambda
   sweep writes to and the readiness monitor checks (0/45 → functional
   once the sweep runs).

## Modules

| Module | Tests | Purpose |
|--------|-------|---------|
| `outcome_backfiller.py` | 19 | Backfill decision_outcomes from runs DB |
| `config_experiment_store.py` | 11 | S6 experiment storage DDL + CRUD |

CLI: `rq outcome-backfill` subcommand added.

## Confidence impact

- 104: data pipeline now has a path from gate verdicts → forward outcomes →
  gate accuracy measurement (S5 unblocked by code, data-bound on accumulation)
- S6: config_experiments schema ready for the lambda sweep to write to
- 30 new tests, 2191 total passing
