# 2026-07-07 — rq105 reliability hardening

**PR**: fix(rq105): shell wrappers + plist fixes for batch-scores and liveness

## Problem

4 of 6 rq105 launchd jobs were failing daily:

| Job | Exit | Root cause |
|---|---|---|
| batch-scores-export | 1 | plist ran python directly — no PYTHONPATH, no shell wrapper |
| liveness | 1 | plist ran python directly — same issue |
| session-scheduler | 1 | `-run` has `--mode paper` (CLI doesn't accept it) — fixed in #420 |
| shadow-serving | 2 | `-run` missing feature-snapshot check — fixed in #416 |

The systemic bug: `batch-scores-export` and `liveness` plists invoked
python directly instead of going through a shell wrapper. This skipped
PYTHONPATH setup, so any import outside the venv's installed packages
(e.g. `renquant_common.notify`, subrepo modules) would fail.

## Fix

1. Created `run_batch_scores_export.sh` — shell wrapper with PYTHONPATH,
   logging redirect, and ntfy on failure
2. Created `run_liveness_check.sh` — same pattern
3. Updated both plists to call the shell wrappers instead of python directly
4. Added `test_rq105_ops_wrappers.py` — 7 tests ensuring ALL plists use
   shell wrappers, all wrappers set PYTHONPATH, reference the pinned
   checkout, and log to the correct directory

## Deployment

After merge, the `-run` checkout must be synced to pick up:
- The two new shell wrappers
- The updated plists (need `launchctl unload` + `launchctl load`)
- The MIN_ROWS=25 fix from #415
- The session-scheduler fix from #420
- The shadow-serving feature-snapshot check from #416
