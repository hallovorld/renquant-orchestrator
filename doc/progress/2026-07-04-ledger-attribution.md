# Decision-ledger attribution engine (107 skeleton, S5)

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S5 (fwd-outcome join >=95%), 107 skeleton

## What

Adds `ledger_attribution.py` — the forward-outcome tracking and per-gate
value-add analysis engine that extends the S2 decision ledger:

### Schema
- `decision_outcomes` table: one row per (as_of, scope, ticker, gate) recording
  realized forward returns at 5d/20d/60d horizons, entry/exit prices, metadata

### API
- `write_outcomes()` — append realized outcomes (append-only, idempotent)
- `gate_value_report()` — per-gate per-verdict report: n, avg_fwd_ret, hit_rate
- `gate_information_value()` — single-gate VOI: allow_avg_ret − block_avg_ret
- `outcome_coverage()` — per-date join ratio (S5 AC: >=95% for aged decisions)

### CLI
- `renquant-orchestrator gate-value [--gate G --horizon 20 --start-date --end-date]`
  — full report or single-gate VOI

## Why

The decision ledger records WHAT each gate decided. This module records WHAT
HAPPENED NEXT. The join enables: "did blocking GOOG on 07-02 save money?"
"is P-WF-GATE adding value?" — the attribution query that makes gate tuning
evidence-based instead of opinion-based.

## Tests

12 new tests covering: write/idempotency, value report (basic + filtered),
gate VOI computation, outcome coverage, multiple horizons, metadata.
All 1927 tests pass.
