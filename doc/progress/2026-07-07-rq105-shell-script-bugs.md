# 2026-07-07 — Fix rq105 shell script bugs

**PR**: orchestrator bugfix

## Bugs found

### 1. `run_session_scheduler.sh`: missing subrepo PYTHONPATH + activation gate

The repo version was missing two changes that were manually applied to the
`-run` deployment checkout by the operator on 2026-07-06:

- **subrepo PYTHONPATH**: the scheduler imports from pipeline/model/execution
  subrepos at runtime, but the repo script only had orchestrator+common on
  PYTHONPATH. Without subrepo paths, the scheduler fails on import.
- **RENQUANT_INTRADAY_DECISIONING=1**: the triple-gate activation was
  uncommented in `-run` but still commented out in the repo.

The `-run` checkout also had a stale `--mode paper` argument that the CLI
does not accept (mode is controlled via config, not CLI). This caused the
deployed scheduler to fail with `unrecognized arguments: --mode paper`.
The repo version correctly does NOT have `--mode paper`.

### 2. `run_shadow_serving.sh`: feature-snapshot gate blocks execution

The repo version still had a feature-snapshot pre-check that exits 1 if
`feature_snapshot_<date>.json` does not exist. But PR #416 (merged) made
`--feature-snapshot-json` optional in the Python CLI, and the deployed
`-run` version already runs without it. The repo script was out of sync:
- Removed the feature-snapshot existence check (no producer exists)
- Removed `--feature-snapshot-json` from the CLI invocation

## Root cause

The repo shell scripts fell behind operator hotfixes applied directly to
the `-run` deployment checkout. This PR syncs the repo to match the
correct deployed behavior (minus the `--mode paper` bug).
