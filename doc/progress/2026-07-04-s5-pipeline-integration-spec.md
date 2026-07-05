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

## Round 2 (Codex review)

Codex blocked on a spec/implementation-contract mismatch: Step 4's OXY 07-01
fixture section specified that `decision_outcome_validator` should return a
`PASS` on a single-fixture replay, but the validator's real contract
(`MIN_SAMPLE_SIZE = 5`, `INSUFFICIENT_DATA` below threshold) cannot produce a
`PASS` for n=1. Fixed by changing the acceptance criterion to
`overall_verdict == "INSUFFICIENT_DATA"`, with an explicit note reframing this
step as a write-side plumbing check (verdict rows are structurally correct,
validator runs without erroring) rather than a statistical-significance
check — explicitly ruling out lowering `min_sample` to force a `PASS`, since
that would defeat the threshold's purpose rather than validate anything.

Also addressed codex's secondary, non-blocking concern: the "fail-open on
ledger-write import/version-skew" behavior in the Safety section is now
framed as an explicit, deliberate operational tradeoff (availability of the
daily run over ledger-coverage completeness) rather than an implicit
default, since S5 is a critical measurement substrate for several downstream
programs.
