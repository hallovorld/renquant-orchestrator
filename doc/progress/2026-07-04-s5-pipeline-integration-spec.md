# S5: Decision-ledger pipeline integration specification

DATE: 2026-07-04
TYPE: Design specification (no code changes)

## What

Authored `doc/design/2026-07-04-s5-decision-ledger-pipeline-integration.md` —
the integration spec for wiring the decision ledger into the pipeline.

Covers: gate names to instrument, data contract (table schemas), freshness
gate design, forward-return population paths (bootstrap + live), and the
OXY 07-01 canonical fixture specification.

## Why

S5 (decision-ledger wiring) is the single biggest critical-path blocker for
S8 (Track A), M-SIG (signal measurement), M3 (shrinkage review), and 107
attribution validation. The orchestrator modules are built (#335 merged);
the pipeline side needs a clear spec to wire them up.

## Status

Design only — pipeline PR required to implement.

## Round 2 (Codex review — contract drift)

Codex found two mismatches between the spec's Data Contract section and the
real `ledger_attribution.py` substrate:

1. **Schema drift**: the doc's `decision_outcomes` DDL listed placeholder
   columns (`exit_price`, `exit_date`, `exit_reason`, `created_at`) that don't
   exist. Corrected to the real columns: `exit_price_5d`, `exit_price_20d`,
   `exit_price_60d`, `recorded_at`. A pipeline implementer following the old
   text would have wired against non-existent columns.
2. **Semantics drift**: Step 3 Path B described a scheduled job "updating the
   outcome row" as each forward horizon (5d/20d/60d) elapses. But
   `write_outcomes()` is `INSERT OR IGNORE` against a fixed
   `(as_of, scope, ticker, gate)` primary key — it cannot update an
   already-written row, so incremental per-horizon updates are structurally
   impossible under the real v1 contract (a second insert on an existing PK
   is a silent no-op). Rewrote Path B to describe the real mechanism instead:
   a scheduled job waits until a decision is fully aged (≥60d, the longest
   tracked horizon — matching `readiness_monitor.check_decision_ledger()`'s
   own "aged" threshold), computes all three forward returns together, and
   writes the outcome row once. This is option (a) — align the doc to the
   real append-only v1 contract — not a request for a future schema/API
   change, since the write-once-when-fully-aged pattern fully satisfies the
   S5 AC using what's already shipped.
