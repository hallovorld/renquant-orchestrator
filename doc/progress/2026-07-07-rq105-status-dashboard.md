# 2026-07-07 — rq105 status dashboard

**PR**: orchestrator feature

## What

One-command status dashboard for rq105:

```bash
python ops/renquant105/rq105_status.py
```

Shows in one screen:
- launchd job states (running / exit code)
- today's log files (exists / size / freshness)
- batch scores availability for today
- latest qualifying DB run (date + scored count)
- paper account cash
- recent errors from launchd stderr logs

## Why

No way to quickly check if 105 is healthy without manually running
`launchctl list | grep rq105`, `ls logs/rq105/`, checking the DB, etc.
Operator asked for a quick dashboard command.

## Scope

New file: `ops/renquant105/rq105_status.py`. Read-only, no side effects.
