# M9: Doc/Impl Alignment — Snapshot Tooling + Audit

**Date:** 2026-07-04
**PR:** (this PR)
**Master plan ref:** M9 — "#210/#212 text alignment + generated strategy-104.md snapshot + CI staleness check"

## What shipped

1. **`scripts/generate_strategy_snapshot.py`** — generates a machine-readable JSON
   snapshot of the orchestrator's configured surface:
   - 31 CLI subcommands
   - 2 pyproject entrypoints
   - 32 scheduled jobs (launchd plists)
   - 37 design docs
   - 86 source modules

2. **`data/strategy_snapshot.json`** — committed baseline for CI comparison.

3. **`tests/test_doc_alignment.py`** — 3 tests:
   - `test_snapshot_not_stale`: compares live snapshot to baseline; fails with
     a clear diff message if CLI/entrypoints/modules changed without updating
     the baseline.
   - `test_design_docs_exist`: verifies every doc listed in the snapshot exists
     on disk.
   - `test_cli_subcommand_count_sanity`: catches accidental mass-removal of
     CLI subcommands (floor at 25).

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
