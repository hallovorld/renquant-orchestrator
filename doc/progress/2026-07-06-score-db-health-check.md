# 2026-07-06 — Score DB health check script

**PR**: add `scripts/check_score_db_health.py`

## What

Diagnostic script that verifies score_distribution data health:
- Warns on misleading empty `score_db.sqlite3` (0-byte placeholder)
- Verifies actual `data/runs.<broker>.db` has rows and recent data
- Reports date coverage and percentile table status

## Why

`backtesting/renquant_104/score_db.sqlite3` is a 0-byte empty file that
looks like a broken score database. Actual score data lives in
`data/runs.alpaca.db` (3808 rows, 56 daily percentile snapshots). The
empty file is misleading and caused confusion during MU top-up investigation.

## Scope

- New diagnostic script only, no behavior changes
- Exit 0 = healthy, exit 1 = issues found
