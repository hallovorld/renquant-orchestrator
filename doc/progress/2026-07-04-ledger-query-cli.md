# Decision ledger query CLI

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S5 (decision-ledger wiring)

## What

Adds `renquant-orchestrator ledger-query` CLI subcommand to query the S2 decision
ledger — the append-only gate-verdict event store that records every gate's
allow/halve/block verdict per run. This is the orchestrator-side read surface for
the S5 wiring (write-side is pipeline/gate_registry).

### Features
- `--date YYYY-MM-DD` — query a specific date (default: today)
- `--scope` — filter by scope (default: "daily")
- `--verdict allow|halve|block` — filter by verdict
- `--gate SUBSTRING` — filter by gate name (substring match)
- `--days N` — show last N days instead of a single date
- `--summary` — aggregate per-gate verdict counts instead of raw rows
- `--db PATH` — override the default DB path

### Example usage
```bash
# What blocked today?
renquant-orchestrator ledger-query --verdict block

# WF gate history over the last 7 days
renquant-orchestrator ledger-query --gate WF --days 7 --summary

# Full detail for a specific date
renquant-orchestrator ledger-query --date 2026-07-01
```

## Why

The decision ledger AC is "every live run writes; fwd-outcome join ≥95% for aged
decisions." The write side is pipeline/gate_registry work. The read side — the
autopsy query that "replaces hours of log archaeology" — was missing a CLI surface.
This makes the ledger actionable from the operator's terminal.

## Tests

5 new tests covering: basic query, verdict filter, gate substring filter, summary
mode with multi-day range, empty DB. All 1917 tests pass.
