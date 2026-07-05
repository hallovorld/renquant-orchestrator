# S5 outcome observer scheduled job registration

**Date:** 2026-07-05
**PR:** (this PR)
**Sprint item:** S5 decision ledger

## What changed

Registered `outcome_observer` in the scheduled job inventory
(`scheduled_jobs.py`). The outcome observer module itself was built in PR #351;
this PR wires it into the orchestration infrastructure so launchd/cron can
discover and schedule it.

- Job ID: `outcome_observer`
- Cadence: weekly
- Command: `renquant-orchestrator run-job outcome_observer`
- Migration state: `native_multirepo`
- Umbrella state dependency: `runs.alpaca.db` (entry prices + forward returns)

Updated test assertions (total 31 -> 32, native 29 -> 30,
umbrella_state_dependency_job_count 19 -> 20) and strategy snapshot.

## Status

S5 substrate: decision_ledger + gate_registry + outcome_backfiller +
outcome_observer all delivered. Remaining gap = umbrella RunnerAdapter caller
(live tree, cannot modify from agent).
