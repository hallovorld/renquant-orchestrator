# GOAL-3 — 44.5% of what a repo-wide walk sees in this repo is not in this repo

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-3 (architecture compliance / twins)

## Measured

`[本次实测 2026-08-01]`, `Path('.').rglob('*.py')` in `renquant-orchestrator`:

| | |
|---|--:|
| files the walk returns | **5,238** |
| untracked **environment** (`.venv` &c) | 2,419 |
| inside a **nested checkout** | **2,329** — **44.5% of the walk** |
| nested checkouts found | **6** |
| tracked `.py` basenames with ≥1 stale twin | **414** |
| most duplicated basename | `__init__.py` ×267 |

Six abandoned agent worktrees, each a near-complete checkout of this repo on a different
branch, live inside the working tree. `git ls-files` cannot see them — `.git/info/exclude`
hides them — but `grep -r`, `rglob` and `os.walk` all can, and **none** of the four
repo-walking ops tools filters them (`ops/run_bundle_schema_audit.py`,
`ops/undelivered_alert_scan.py`, `ops/import_resolution_check.py`,
`ops/umbrella_script_shadow_check.py` — 0 references to `.claude` or `ls-files` between
them).

## Why this belongs to GOAL-3

The twin-implementation registry exists because two copies of one behaviour drift apart
and a guard ends up checking the wrong one. These worktrees are **414 basenames' worth of
twins that nobody registered**, pinned to branches that stopped moving weeks ago. A search
for a symbol returns the stale copy beside the real one with nothing distinguishing them,
and *"which of these is production?"* is precisely the question the registry was built to
answer.

**This is not hypothetical.** Investigating the WF gate earlier this session, a
`grep -rn wf_gate_metadata` over this repo returned
`.claude/worktrees/agent-a20d725b9ab099a41/scripts/kpi_scorecard.py` among its first hits —
a stale copy. It was noticed. The failure mode is the day it is not.

## The correction that makes this a usable signal

My first version reported *"90.6% of the walk is untracked"* — and **2,419 of those files
were `.venv`**. Every Python repo trips that forever: a guard that always fires says
nothing. The rule now separates **untracked environment** from **files inside a nested
checkout**, and nested checkouts are found **structurally** (a directory carrying a `.git`
entry — file *or* directory, since worktrees carry a file) rather than by matching
`.claude/worktrees`. A name list is the fail-open version: the next tool to park a checkout
elsewhere would be invisible to it.

Measured across the four sibling repos on this machine `[本次实测]`, the corrected rule
separates them cleanly:

| repo | nested | share | verdict |
|---|--:|--:|---|
| `renquant-orchestrator` | 2,329 | 44.5% | **FIRES** |
| `renquant-pipeline` | 0 | 0.0% | clean — its 8,464 untracked are all `.venv` |
| `renquant-model` | 0 | 0.0% | clean |
| `renquant-strategy-104` | 0 | 0.0% | clean |

`renquant-pipeline` is the proof: under the first rule it was the *worst* repo at 95.5%;
under the corrected one it is clean, because none of it is a copy of itself.

## Not claimed, and not done

That any specific stale file has caused a wrong conclusion — one near-miss is recorded
above and that is the whole evidence. That the worktrees should be removed: a worktree may
be an in-flight branch, `git worktree list` is the authority, and the tool never deletes,
never invokes `git worktree`, and never writes. **No worktree was removed by this work.**
Making the four existing walkers filter nested checkouts is a follow-up, not this PR — it
changes what four merged detectors report, and that deserves its own before/after.

## Tests

10. Including both halves of the correction: a 30-file `.venv` does **not** fire, and a
nested checkout does; a `.git` **file** counts as well as a directory; a checkout inside a
checkout is not double-counted; and a non-repo root **SKIPs with 3** rather than treating
an empty tracked set as "everything is untracked". Suite: **5161 passed, 2 skipped**, run
before the push.
