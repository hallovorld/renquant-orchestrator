# Model freshness monitor — CLI + scheduled job wiring

**Date**: 2026-07-04
**PR**: (this PR)
**Design doc**: doc/design/2026-06-30-model-freshness-governance.md (#210)

## What

The model freshness monitor (`model_freshness_monitor.py`, 1381 lines, existing)
was a complete module with no operational surface. This PR wires it into:

1. **CLI subcommand**: `renquant-orchestrator model-freshness [args]` — forwards
   to the monitor's `main()` with full argument passthrough
2. **Job dispatcher**: `model_freshness_monitor` in `job_runner.py`
3. **Scheduled job inventory**: daily ops job, `production_safe=True`,
   launchd label `com.renquant.model-freshness`

## Why

The monitor checks freshness across all three model populations (prod XGB panel,
shadow PatchTST, per-ticker tournament) against data-cutoff-keyed policies.
Without CLI/scheduler wiring, it can only be invoked via `python -m` which
bypasses the orchestrator's operational surface and job audit trail.

## Tests

All 1912 tests pass. Scheduled job inventory counts updated (21→22 total,
19→20 native_multirepo, 15→16 umbrella_state_dependency).
