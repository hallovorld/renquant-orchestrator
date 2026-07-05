# S11 Artifact Retention Policy and Pruning

**Date:** 2026-07-05
**Ticket:** s11-staging-backup-retention-policy (roadmap-backlog.json)
**Status:** implemented

## Problem

The S11 live-tree inventory (PR #241) identified 46 untracked promote-pipeline
files accumulating with no pruning:

- 20 timestamped `panel-ltr` / `panel-rank-calibration` weekly staging files
- 21 weekly/monthly rollback snapshots
- 3 `subrepos.lock.json.promote-bak.*` backups

These are written by `kernel/model_acceptance.py` (staging + rollback) and
`scripts/promote_pin.py` (lock backup) with no retention logic.

## Solution

New module `src/renquant_orchestrator/retention_policy.py` with:

1. **Retention config** per artifact family:
   - `staging_panel_ltr`: keep 4 (weekly cadence = ~1 month)
   - `staging_calibration`: keep 4
   - `rollback_snapshots`: keep 8
   - `lock_backups`: keep 5

2. **`prune_stale_artifacts(root, *, dry_run=True)`** scans by glob, sorts by
   mtime, returns prunable paths beyond the retention window. Only deletes
   when `dry_run=False`.

3. **CLI**: `renquant-orchestrator prune-artifacts [--execute] [--repo PATH] [--json]`
   Defaults to dry-run.

## Safety

- Dry-run by default; `--execute` required for deletion.
- Tests use `tmp_path`, never real production paths.
- No writes to production data paths.

## Files

- `src/renquant_orchestrator/retention_policy.py` (new)
- `src/renquant_orchestrator/cli.py` (wired new subcommand)
- `tests/test_retention_policy.py` (new, 19 tests)
- `doc/progress/2026-07-05-s11-retention-policy.md` (this file)
