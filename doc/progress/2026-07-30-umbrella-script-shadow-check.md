# 26 umbrella scripts have DIVERGED from the subrepo module they shadow   (PR pending)

STATUS:    delivered
WHAT:      Adds `ops/umbrella_script_shadow_check.py` plus a committed registry of every
           umbrella `scripts/*.py` that name-shadows a sibling `src/` module, classified
           IDENTICAL or DIVERGED. Read-only.
WHY/DIR:   GOAL-3. renquant-orchestrator#623 R2 is one instance and it cost five weeks of
           `book_to_price = 1.68e19` because a fix landed on the umbrella's dead copy
           while the live producer sat in `renquant-base-data`. R2 is not a one-off.
EVIDENCE:  §1.
NEXT:      §3 — each of the 26 DIVERGED pairs needs a per-file disposition. The tool
           registers them; it does not adjudicate them.

## §1 EVIDENCE

`[VERIFIED — ops/umbrella_script_shadow_check.py --emit, 2026-07-30]`

| | count |
|---|---|
| umbrella `scripts/*.py` swept | 284 |
| name-shadowing a sibling `src/` module | **44** |
| of those, **DIVERGED** | **26** |
| of those, byte-IDENTICAL | 18 |
| referenced by any `.sh` or `com.renquant.*` plist | **12** |

The largest divergences sit in the WF-gate area, where "which copy runs" has already
cost real defects: `fit_walkforward_calibrators` (umbrella **+11,979 B**),
`train_walkforward_patchtst` (**−11,488 B**), `wf_config_builder` (**−8,131 B**).

## §2 THE SCOPE LIMIT — it does not catch R2 itself

Matching is by **identical filename stem**. R2 is umbrella `fetch_sec_fundamentals.py`
against base-data **`sec_fundamentals.py`** — *different stems*, so **this sweep does not
see the instance that motivated it.**

I found that only because a test I wrote asserting "R2 is registered" **failed**. The
test now pins the opposite, so nobody reads "44 pairs registered" as "the twin surface is
covered". Catching renamed twins needs content similarity rather than names, which trades
a clean signal for false positives — a separate tool, not a quiet widening of this one.

## §3 What the tool refuses to claim

*"Not referenced by a `.sh` or a plist"* is **not** proof a script is dead: it can be run
by hand, imported by other Python, or invoked by an agent. A shared filename is not proof
of shared purpose. So every finding is phrased as **a reader could plausibly edit the
wrong copy**, never as *this file is dead*. The 12 that **are** referenced are flagged as
such rather than filtered out.

Subrepo state is read from **`origin/main`**, not the checked-out worktree — a sibling can
sit on a feature branch, and comparing against that would make the answer depend on
someone else's uncommitted state. A test pins that.

## §4 Safety

The tool never runs `git` **inside** the umbrella — a sub-agent's `git reset --hard` in
that shared live checkout caused an incident. `test_the_tool_never_runs_git_inside_the_umbrella`
asserts the source never pairs `git -C` with the umbrella path. Nothing is written, no
file is mutated.

## §5 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree | 7 failed, 4577 passed, 5 skipped, 27 warnings in 121.46s (0:02:01) |
| this branch | 7 failed, 4592 passed, 5 skipped, 27 warnings in 125.20s (0:02:05) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`
