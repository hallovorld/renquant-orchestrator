# Wire outcome_observer into job_runner dispatch

**Date**: 2026-07-05
**Sprint**: 3-day sprint (2026-07-03~07-06)
**Scope**: S5 forward-outcome infrastructure

## What

`outcome_observer` was registered in `scheduled_jobs.py` (#353, merged) but
missing from `job_runner._MODULE_JOBS`. Running `renquant-orchestrator run-job
outcome_observer` would fail with "unknown scheduled job id" — the collector
existed but was unreachable through the standard dispatch path.

## Why

S5 (decision-ledger wiring) requires forward-outcome population for the
"fwd-outcome join ≥95%" acceptance criterion. Without this fix, the outcome
collector can't run through the scheduled-job dispatch surface.

## Changes

- Added `outcome_observer` → `renquant_orchestrator.outcome_observer` mapping
  in `job_runner._MODULE_JOBS`
- Added dispatch test in `test_cli.py`
- Updated strategy snapshot

## NEXT

- Codex review + merge
- N1 liveness: verify outcome_observer runs end-to-end on production DB
