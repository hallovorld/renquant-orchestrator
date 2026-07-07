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

## Round 2 (codex review)

STATUS: fixed
WHAT: two issues — (1) the branch carried unrelated files from the
already-merged concentration-cap research PR (#403), a stale-branch artifact;
(2) `--repo-dir` defaulted to a hardcoded `~/git/github/RenQuant` umbrella
path instead of this repo's canonical runtime-path convention.
WHY-DIR: (1) rebasing onto `origin/main` collapsed the diff back down to
just this script + its progress doc — confirmed via `git diff origin/main
--stat`. (2) codex correctly flagged the hardcoded umbrella default as the
wrong convention for the multi-repo direction; switched to
`runtime_orchestrator.runtime_paths.default_data_root()`, the same
canonical resolver used by this session's other path-authority fixes
(`#374`'s readiness checker, `#391`'s standing measurement job, `#396`'s
retention policy). Also removed a stale docstring claim (a "point 4"
per-ticker diagnostic that was never actually implemented in the code).
EVIDENCE: added `tests/test_check_score_db_health.py` proving the default
path resolution genuinely calls `default_data_root()` (not a hardcoded
guess) and that an explicit `--repo-dir` still overrides it. Confirmed both
tests fail against the pre-fix module (which never imports
`default_data_root` at all — `AttributeError`) and pass after. Full suite
3146/3149 (no new failures).
NEXT: none.
