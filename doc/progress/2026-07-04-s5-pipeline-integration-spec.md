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
