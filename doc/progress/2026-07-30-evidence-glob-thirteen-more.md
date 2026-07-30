# 13 more jobs measured on their real surface — and weekly-wf-promote IS running   (PR pending)

STATUS:    delivered
WHAT:      Assigns `evidence_glob` to the 13 remaining jobs that are the **sole occupant**
           of their log directory and write dated files. Read-only tooling change.
WHY/DIR:   GOAL-5 / GOAL-1. The liveness scan measures `StandardOutPath`, a proxy that
           never updates for a wrapper that redirects. #630 and #633 fixed five jobs;
           these are every remaining one where the assignment is provably unambiguous.
EVIDENCE:  §1.
NEXT:      17 jobs still measured by proxy. They share log directories (the `pit-*` trio)
           or write no dated files, and are **not** mechanically assignable.

## §1 EVIDENCE

`[VERIFIED — ops/launchd_liveness_scan.py --json, before and after]`

| | before | after |
|---|---|---|
| `EVIDENCE_FRESH` | 18 | **24** |
| `NO_EVIDENCE_STALE` | 20 | **14** |
| `measured_by_proxy` | 35 / 40 | **22 / 40** |

## §2 A CLAIM OF MINE THIS REFUTES

In #627 I singled out `weekly-wf-promote`: *"its log has not been written since
**2026-05-17** … every claim of the form 'the weekly retrain was admitted by the gate'
assumes that job runs."*

**Measured on its real surface: `EVIDENCE_FRESH`, 0 missed firings, last write
2026-07-29.** The job runs. That reading was a proxy artefact and the warning built on it
was wrong. Also corrected by the same measurement: `conditional-retrain104` (FRESH,
07-29) and `retrain-alpha158-linear` (FRESH, **today**).

**What survives:** `daily103` is still `NO_EVIDENCE_STALE` with **66 missed firings**,
last write 2026-04-28 — now measured on its *real* dated-file surface, so that staleness
is not a proxy artefact. Consistent with the retired 103 generation.

## §3 The assignment criterion, and what it refuses

A glob was assigned only where the job is the **sole occupant of its log directory**
across all 40 manifested plists. The `pit-c1-features` / `pit-estimate-snapshot` /
`pit-liveness` trio share one directory and report the same newest file; assigning a
directory-wide glob there would hand one job's evidence to two others. They stay
unassigned.

## §4 A test of mine that was wrong, and how

`test_no_shared_log_directory_was_assigned_a_glob` **failed** on first run. The
invariant I asserted was too strong: six rq105 jobs share `logs/rq105/` and three carry a
glob, but those globs key on a **unique filename stem** (`session_scheduler_*.log`), so
the shared directory is harmless. The real invariant is narrower — *a **directory-wide**
glob may only be used in a single-occupancy directory* — and the test now asserts that.

## §5 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree | 7 failed, 4579 passed, 5 skipped, 27 warnings in 120.51s (0:02:00) |
| this branch | 7 failed, 4582 passed, 5 skipped, 27 warnings in 116.56s (0:01:56) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §6 Live-surface impact

None. `program_args` and `program_args_sha256` untouched, so no manifest drift. The scan
is read-only and still not wired into any scheduled job.
