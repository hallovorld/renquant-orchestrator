# Decision outcome validator

**Date:** 2026-07-04
**PR:** TBD
**Status:** ready for review

## What

Gate accuracy validation module that joins decision-ledger verdicts to
realized forward returns from `decision_outcomes` and computes per-gate
accuracy metrics. Detects systematic gate failures.

## Changes

1. **`decision_outcome_validator.py`** — validation engine:
   - Joins `decision_ledger` × `decision_outcomes` on (as_of, scope, gate)
   - Per-gate metrics: precision, recall, accuracy, value-of-gate
   - Verdicts: PASS, OVER_RESTRICTIVE, UNDER_RESTRICTIVE, VALUE_DESTRUCTIVE,
     INSUFFICIENT_DATA
   - Structured report with overall verdict
   - CLI: `rq decision-validate [--db] [--horizon] [--gate] [--json] [--strict]`

2. **`cli.py`** — added `decision-validate` subcommand

3. **15 tests** covering: correct gate, over-restrictive, under-restrictive,
   value-destructive, insufficient data, empty DB, multiple gates, date/gate
   filter, horizon variants, CLI (missing DB, missing tables, JSON output,
   strict mode, text output).

## Why

The decision ledger records gate verdicts but has no mechanism to validate
whether gates make correct decisions. This is the missing confidence piece
for 104: without it, we can't prove gates are adding value vs destroying it.

The existing `ledger_attribution` module provides outcome storage and basic
reporting (gate_value_report, gate_information_value), but lacks accuracy
classification, systematic failure detection, and structured validation
verdicts.

## Design

Read-only — never writes to any database or file. Consumes the same
`decision_ledger` + `decision_outcomes` schema that `ledger_attribution`
writes. Gate accuracy is defined as: did ALLOW decisions lead to positive
returns (true positives), did BLOCK decisions correctly avoid losers (true
negatives)?
