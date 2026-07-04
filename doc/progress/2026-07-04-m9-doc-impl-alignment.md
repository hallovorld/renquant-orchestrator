# M9: Doc/Impl Alignment — Snapshot Tooling + Audit

**Date:** 2026-07-04
**PR:** (this PR)
**Master plan ref:** M9 — "#210/#212 text alignment + generated strategy-104.md snapshot + CI staleness check"

## What shipped

1. **`scripts/generate_strategy_snapshot.py`** — generates a machine-readable JSON
   snapshot of the orchestrator's configured surface:
   - 31 CLI subcommands
   - 2 pyproject entrypoints
   - 31 scheduled jobs (job_ids from the repo-owned `scheduled_jobs` registry)
   - 37 design docs
   - 86 source modules

2. **`data/strategy_snapshot.json`** — committed baseline for CI comparison.

3. **`tests/test_doc_alignment.py`** — 5 tests:
   - `test_snapshot_not_stale`: compares ALL FIVE fields (CLI subcommands,
     pyproject entrypoints, scheduled jobs, design docs, source modules) between
     the live snapshot and the committed baseline; fails with a clear diff
     message if any changed without updating the baseline.
   - `test_snapshot_catches_scheduled_jobs_drift` /
     `test_snapshot_catches_design_docs_drift`: regression tests proving the
     staleness check actually fires on injected drift in these two fields (not
     just present syntactically).
   - `test_design_docs_exist`: verifies every doc listed in the snapshot exists
     on disk.
   - `test_cli_subcommand_count_sanity`: catches accidental mass-removal of
     CLI subcommands (floor at 25).

## Round 2 (review)

Codex found the claimed contract didn't match what CI actually enforced:
`test_snapshot_not_stale` only compared `cli_subcommands`/`pyproject_entrypoints`/
`source_modules`, silently excluding `scheduled_jobs` and `design_docs` despite
the module docstring claiming all fields were covered. Worse, `scheduled_jobs`
was derived from the local user's `~/Library/LaunchAgents` directory — machine-local
state that would make any CI comparison meaningless (a runner or a different
developer's laptop has completely different plists installed).

Fixed both:
- `scheduled_jobs` now reads `job_id`s from `renquant_orchestrator.scheduled_jobs`
  (the repo-owned job registry already used by PRs #316/#317/#319 this session)
  instead of local launchd state — genuinely repo-owned, reproducible in CI.
- `design_docs` is a plain repo-owned file listing (same shape as `source_modules`,
  which was already compared) — wired into the real comparison rather than trimmed.
- Added two regression tests proving the wiring is real: each injects a synthetic
  drift into one field and confirms `test_snapshot_not_stale`'s comparison logic
  (now extracted into `_assert_snapshot_matches`) actually raises.
- Regenerated `data/strategy_snapshot.json` against the new `scheduled_jobs` source
  (the job-id naming scheme is unrelated to the old plist-derived names, so this is
  a full replacement of that field, not an incremental diff).

## Audit findings (divergences to track, not fix here)

| Design doc | Status | Divergence |
|---|---|---|
| #208 (105 intraday arch) | 10 modules implemented | Stage-2 executor built but gate-locked; broker envelope (#224) not yet built |
| #210 (model freshness) | Monitor exists | Enforcer in PR #328 (not yet merged); auto-fallback path not wired to retrain flow |
| #212 (shadow freshness) | Diagnosis complete (#323/#324) | rawlabel rebuild needed (operator action); shadow promote not yet automated |
| As-built docs (104/105/106/107) | All 4 exist | Written 2026-07-04; will drift as PRs merge — this snapshot CI catches it |

## How to use

When you add/remove a CLI subcommand, module, or entrypoint:

```bash
python scripts/generate_strategy_snapshot.py --update
git add data/strategy_snapshot.json
```

The CI test will remind you if you forget.
