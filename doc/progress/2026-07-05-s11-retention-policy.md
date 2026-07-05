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
   the semantic timestamp parsed from each filename, returns prunable paths
   beyond the retention window. Only deletes when `dry_run=False`.

3. **CLI**: `renquant-orchestrator prune-artifacts [--execute] [--repo PATH] [--json]`
   Defaults to dry-run.

## Safety

- Dry-run by default; `--execute` required for deletion.
- Tests use `tmp_path`, never real production paths.
- No writes to production data paths.

## Round 2 (codex review)

STATUS: fixed
WHAT: two issues in the retention policy's authority model. (1) The
executable delete path defaulted to a hard-coded workstation root
(`/Users/renhao/git/github/RenQuant`) instead of the repo's normal
runtime-path contract or an explicit required path. (2) The keep/delete
decision was driven by file mtime rather than the semantic timestamp already
embedded in each artifact filename.
WHY-DIR: for a destructive command, a hard-coded path is too brittle (could
silently point at the wrong machine/tree), and mtime is unsafe as a
chronology key because a copy, restore, touch, or sync can reorder it
independent of the artifact's actual logical age -- causing the wrong
rollback/staging snapshot to be selected for deletion.
EVIDENCE: (1) `--execute` now requires an explicit `--repo` (refuses to
guess a workstation path for a destructive delete); dry-run may still
default via `runtime_paths.default_repo_root()`, the same canonical resolver
used elsewhere in this repo (`#374`, `#391`). (2) Added `ArtifactFamily.
timestamp_regex`/`timestamp_format` per family and `_parse_artifact_
timestamp()`, replacing the mtime-based sort key. New test
`test_prune_uses_parsed_timestamp_not_mtime` constructs 3 files with mtime
deliberately reordered opposite to their filename chronology and confirms
the correct (filename-oldest) file is selected as prunable -- confirmed via
`git stash`/manual sort-key revert that this exact scenario silently deleted
the wrong (actual-latest) file under the pre-fix mtime-based sort. Full
module suite 29/29; full repo suite 3006/3008 (2 pre-existing unrelated
failures in `test_bundle_consistency_ci_gate.py`, confirmed reproducing on
clean `origin/main`).
NEXT: none.

## Files

- `src/renquant_orchestrator/retention_policy.py`
- `src/renquant_orchestrator/cli.py` (wired new subcommand)
- `tests/test_retention_policy.py` (29 tests)
- `doc/progress/2026-07-05-s11-retention-policy.md` (this file)
