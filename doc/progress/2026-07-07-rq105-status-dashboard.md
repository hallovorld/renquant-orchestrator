# 2026-07-07 — rq105 status dashboard (v2)

**PR**: orchestrator feature — supersedes closed #417

## What

One-command status dashboard for rq105:

```bash
python ops/renquant105/rq105_status.py
```

Shows in one screen:
- launchd job states (dynamic discovery via `com.renquant.rq105-*` prefix)
- today's log files (exists / size / freshness)
- batch scores availability for today
- latest qualifying DB run (date + scored count)
- paper account cash
- recent errors from launchd stderr logs

## Why

Operator asked for a quick way to check 105 health without manually
running multiple commands.

## v1→v2 changes (addresses Codex review on #417)

- Path resolution via `runtime_paths.default_repo_root()` (not hardcoded)
- Batch-scores threshold imported from `export_batch_scores.MIN_ROWS`
  (single source of truth — was hardcoded 30, now tracks canonical 25)
- Launchd jobs discovered dynamically by prefix, not a hardcoded label list
- DB query uses `created_at DESC` ordering (matches canonical exporter)

## Scope

New file: `ops/renquant105/rq105_status.py`. Read-only, no side effects.
