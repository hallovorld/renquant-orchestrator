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

## CI fix — the check reported 44 deletions when it had nothing to look at

The first push went red in CI, and the failure was the tool's own design rather than a
flaky runner. `survey()` globs `UMBRELLA/scripts/*.py`, and `UMBRELLA` defaults to an
absolute path on the operator's machine. CI has no umbrella checkout, so the glob
returned nothing, and `verify()` — which cannot tell "found no scripts" from "there was
nothing to search" — reported all **44 registered pairs as `no longer shadows anything
— re-emit`** `[VERIFIED — reproduced by neutralising the new guard: 44 problems without
it, 1 with it, this session]`.

That is this repo's recurring guard-validates-the-wrong-object shape, in a guard
written to catch a twin-file defect. It is worse than a CI annoyance: the emitted
remedy is **"re-emit"**, and following it on a machine with a moved or missing checkout
would overwrite the registry with an empty one — destroying the very record the check
exists to hold, while reporting success.

Fixed by making absence a distinct, loud state:

* `umbrella_present()` separates "no tree to survey" from "surveyed and found nothing".
* `verify()` returns a single `UNVERIFIABLE: … the 44 registered pairs were NOT
  checked` instead of 44 phantom deletions.
* `main()` exits **2** for "could not check" against **1** for "checked, found drift".
  A caller that cannot tell those apart will eventually treat an unrunnable check as a
  passing one — which is exactly the failure this registry exists to prevent.
* The assertions that compare the registry to a live tree are marked
  `@needs_umbrella` — they are integration tests about the operator's disk, not unit
  tests of the logic. Two new tests run **everywhere** and assert that an absent
  umbrella is never clean and exits 2, so the skip cannot quietly become a pass.

`[VERIFIED — this session]` 17 passed locally; with the umbrella absent (`RQ_ROOT` at a
nonexistent path, i.e. the CI case) 10 passed, 7 skipped, 0 failed.

## Round 2 — I fixed one half of the fail-open and left the other

The umbrella fix above closed the case where the *umbrella* tree is missing. Codex
found the same shape still open on the **sibling** side, and it was the more dangerous
half.

`_sh()` returned `proc.stdout` regardless of the exit code, so an unreachable sibling
checkout, a missing `origin/main`, or a failed `ls-tree` all produced `b""` — which
`subrepo_modules()` read as *"this repo has an empty `src/` tree"*. Two consequences:

* `--emit` would print a registry missing that repo's pairs. That output is **committed
  as the baseline**, so a transient failure at emit time silently erases coverage
  permanently, and the resulting registry looks complete.
* `verify()` could report **clean** over a surface it never read.

The second is subtle enough to be worth reproducing rather than describing, so I did
`[VERIFIED — this session]`: `renquant-pipeline` has **zero** registered pairs, so with
the old `_sh()` an unreachable `renquant-pipeline` left the live/known diff empty and
`verify()` returned `[]`. Not a wrong answer about the registry — the tool never looked
at that repo, and said so by saying nothing. With the gate in place the same setup
returns one `UNVERIFIABLE` naming the missing checkout.

Fix, closing both directions:

* `_sh()` **raises `Unverifiable`** on a non-zero exit instead of returning stdout.
* `check_siblings()` validates **every** configured sibling — checkout exists, and
  `origin/main` is readable — **up front**, so a partial answer cannot be assembled.
* `survey()` gates on it and raises rather than returning a partial dict.
* `--emit` catches that and **exits 2 with nothing on stdout**. Refusing to print is
  the point: an emitted partial registry gets committed and becomes the baseline.
* `verify()` maps it to the same single `UNVERIFIABLE … were NOT checked` line as the
  umbrella branch, and `main()` exits **2**.

Seven new tests, one per failure mode, including the exact silent-clean scenario above
with an assertion that the chosen victim still has zero registered pairs — so if the
registry grows a pair for it, the test tells you to pick another rather than quietly
stopping to reproduce the bug.

`[VERIFIED — this session]` 25 passed locally; 17 passed / 7 skipped / 0 failed with
the umbrella absent (the CI case).

**The lesson worth keeping:** I fixed the instance codex pointed at and did not sweep
the file for the same shape. `_sh()` was three lines above the function I was editing.
