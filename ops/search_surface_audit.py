#!/usr/bin/env python3
"""44.5% of what a repo-wide walk sees in this repo is not in the repo. (GOAL-3)

MEASURED 2026-08-01 in `renquant-orchestrator`:

===============================================  =======
`Path('.').rglob('*.py')` returns                  5 238
  …untracked ENVIRONMENT (`.venv` &c)              2 419   uninteresting
  …inside a NESTED CHECKOUT                        2 329   **44.5% of the walk**
tracked `.py` basenames with >= 1 stale copy         414
===============================================  =======

THE SPLIT IS THE WHOLE POINT. A first version reported "90.6% of the walk is untracked" —
and 2 419 of those were `.venv`. Every Python repo trips that forever, which is a guard
that always fires and therefore says nothing. Measured across the four sibling repos on
this machine, the corrected rule separates them cleanly:

    renquant-orchestrator   nested 2 329 / 44.5%   ->  FIRES   (6 nested checkouts)
    renquant-pipeline       nested     0 /  0.0%   ->  clean   (its 8 464 are all .venv)
    renquant-model          nested     0 /  0.0%   ->  clean
    renquant-strategy-104   nested     0 /  0.0%   ->  clean

Six abandoned agent worktrees, each a near-complete checkout of this repo on a different
branch, live inside the working tree. `git ls-files` cannot see them — `.git/info/exclude`
hides them — but `grep -r`, `rglob` and `os.walk` all can.

WHO IS ACTUALLY EXPOSED — NARROWED AFTER MEASURING `[本次实测 2026-08-01]`. An earlier
draft of this file said "every ops detector in this repo that walks the tree does so
without filtering them". That overstated it, and the check is: which committed tool walks
a root that CONTAINS the nested checkouts?

  * `run_bundle_schema_audit.py`  — walks caller-supplied directories; no in-repo caller.
  * `undelivered_alert_scan.py`   — walks `RenQuant/logs`, outside any checkout.
  * `umbrella_script_shadow_check.py` — reads siblings via `git ls-tree origin/main`.
  * `tests/test_market_calendar_repoint.py` — walks `REPO_ROOT/{src,scripts,ops}`, none
    of which contains a worktree.

**Zero committed tools are exposed today.** The contamination is real for INTERACTIVE
search — a `grep -rn wf_gate_metadata` in this repo returned
`.claude/worktrees/agent-a20d725b9ab099a41/scripts/kpi_scorecard.py` among its first hits
during this session — and it is a standing hazard for the next tool that walks from the
repo root. It is not, today, a defect in any shipped detector.

AND THE REPO ALREADY CONTAINS THE ANSWER. `umbrella_script_shadow_check.subrepo_modules()`
enumerates sibling sources with `git ls-tree -r --name-only origin/main`, and its docstring
gives the reason in its own words: *"a sibling checkout can sit on a feature branch, and
comparing against whatever happens to be checked out would make the answer depend on
someone else's uncommitted state."* That is the pattern anything walking a repo should
copy, and it is cited here rather than reinvented.

WHY THIS IS A GOAL-3 PROBLEM SPECIFICALLY. The twin-implementation registry exists because
two copies of one behaviour drift apart and a guard ends up checking the wrong one. These
worktrees are **414 basenames' worth of twins that nobody registered**, pinned to branches
that stopped moving weeks ago. A repo-wide search for a symbol returns the stale copy
alongside the real one with nothing to tell them apart, and "which of these is production?"
is exactly the question the registry was built to answer.

THIS IS NOT HYPOTHETICAL. While investigating the WF gate this session, a `grep -rn
wf_gate_metadata` over this repo returned
`.claude/worktrees/agent-a20d725b9ab099a41/scripts/kpi_scorecard.py` — a stale copy of a
script — among its first hits. It was noticed. The failure mode is that one day it is not,
and a finding gets published about code that has not run in weeks.

WHAT THIS TOOL DOES. It reports, for a given root, how much of a naive walk lies inside a
nested checkout, which subtrees dominate, and how many tracked basenames have stale twins.
Nested checkouts are found **structurally** — a directory carrying a `.git` entry — never
by matching a name like `.claude/worktrees`, because a name list is the fail-open version:
the next tool to park a checkout elsewhere would be invisible to it. It does **not** delete
anything: a worktree may be an in-flight branch, and `git worktree list` is the authority
on that, not this file.

WHAT IT DOES NOT CLAIM. That any specific stale file has caused a wrong conclusion — one
near-miss is recorded above and that is the evidence, no more. That the worktrees should be
removed; that is the operator's call and `git worktree remove` is theirs to run.

Read-only. Never writes, never invokes `git worktree`, never deletes.

Exit codes: ``0`` the nested-checkout share is under the threshold, ``1`` at or over it, ``2``
usage/IO error, ``3`` SKIPPED — not a git repository, so "tracked" is undefined and
nothing was measured.
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

#: Above this share of a naive walk sitting in a NESTED CHECKOUT, a repo-wide grep returns
#: more stale duplicates of this repo than the repo. Not tuned to make today pass: today
#: measures 44.5% and this fires.
DEFAULT_MAX_NESTED_SHARE = 0.10


def nested_checkout_roots(root: Path) -> list[Path]:
    """Directories under `root` that are THEMSELVES checkouts.

    Detected STRUCTURALLY -- a directory carrying a `.git` entry -- not by matching names
    like `.claude/worktrees`. A name list is the fail-open version: the next tool to park
    a checkout somewhere else is invisible to it. Worktrees carry a `.git` FILE rather
    than a directory, so both are accepted.

    This is also what separates the signal from the noise. `.venv` is untracked and
    enormous and completely uninteresting -- it is not a copy of THIS repo. A nested
    checkout is, and that is the thing that makes a repo-wide search ambiguous.
    """
    out = []
    for git in root.rglob(".git"):
        if git.parent == root:
            continue
        # Do not descend into a checkout to find checkouts inside it: the outermost one
        # already accounts for everything under it.
        if any(str(git.parent).startswith(str(o) + "/") for o in out):
            continue
        out.append(git.parent)
    return sorted(out)


def tracked_files(root: Path) -> set[str] | None:
    """`git ls-files`, or None when this is not a git repository.

    None is the SKIPPED signal, not an empty set. An empty set would make every file look
    untracked and turn a non-repo directory into a maximal alarm — a detector reporting a
    catastrophe it never measured.
    """
    try:
        res = subprocess.run(["git", "-C", str(root), "ls-files"],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return set(res.stdout.split())


def audit(root: Path, pattern: str = "*.py",
          max_share: float = DEFAULT_MAX_NESTED_SHARE) -> dict:
    tracked = tracked_files(root)
    if tracked is None:
        return {"status": "not_a_git_repo", "root": str(root)}

    walked = [p for p in root.rglob(pattern) if ".git/" not in str(p) + "/"]
    rel = [str(p.relative_to(root)) for p in walked]
    untracked = [r for r in rel if r not in tracked]

    # THE DISTINCTION THAT MAKES THIS USEFUL. The first version reported "90.6% of the
    # walk is untracked" -- and 2 418 of those files were `.venv`. Every Python repo would
    # trip that forever, which is a guard that always fires and therefore says nothing.
    # What matters is the untracked files that are COPIES OF THIS REPO.
    nested = [str(d.relative_to(root)) for d in nested_checkout_roots(root)]
    in_nested = [r for r in untracked
                 if any(r == n or r.startswith(n + "/") for n in nested)]
    environment = [r for r in untracked if r not in set(in_nested)]

    by_root = collections.Counter(r.split("/", 1)[0] for r in in_nested)

    tracked_names = collections.Counter(
        Path(t).name for t in tracked if Path(t).match(pattern))
    stale_names = collections.Counter(Path(r).name for r in in_nested)
    shadowed = sorted(n for n in tracked_names if n in stale_names)

    share = (len(in_nested) / len(rel)) if rel else 0.0
    return {
        "status": "checked",
        "root": str(root),
        "pattern": pattern,
        "n_walked": len(rel),
        "n_untracked": len(untracked),
        "n_in_nested_checkout": len(in_nested),
        "n_untracked_environment": len(environment),
        "nested_checkout_roots": nested,
        "nested_share": round(share, 4),
        "max_nested_share": max_share,
        "over_threshold": share >= max_share,
        "nested_by_top_level": dict(by_root.most_common(10)),
        "n_tracked_basenames_with_a_stale_twin": len(shadowed),
        "example_shadowed_basenames": shadowed[:10],
        "most_duplicated": (stale_names.most_common(1)[0] if stale_names else None),
        "scope_note": (
            "Reports contamination of the SEARCH surface. It does not claim any stale "
            "file has caused a wrong conclusion, and it never deletes: a worktree may be "
            "an in-flight branch, and `git worktree list` is the authority on that."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--pattern", default="*.py")
    ap.add_argument("--max-nested-share", type=float,
                    default=DEFAULT_MAX_NESTED_SHARE, dest="max_nested_share")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = audit(a.root, a.pattern, a.max_nested_share)
    except OSError as exc:
        print(f"search-surface: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if rep["status"] != "checked":
        print(f"SKIPPED: {a.root} is not a git repository — 'tracked' is undefined and "
              f"nothing was measured.", file=sys.stderr)
        return 3

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"  walk of {rep['pattern']!r} under {rep['root']}")
        print(f"    returned            {rep['n_walked']:>7,}")
        print(f"    untracked           {rep['n_untracked']:>7,}")
        print(f"      environment       {rep['n_untracked_environment']:>7,}  "
              f"(.venv &c -- not copies of this repo, not the signal)")
        print(f"      NESTED CHECKOUT   {rep['n_in_nested_checkout']:>7,}  "
              f"({rep['nested_share']:.1%} of the walk)")
        print(f"    threshold           {rep['max_nested_share']:>7.1%}  "
              f"-> {'OVER' if rep['over_threshold'] else 'ok'}")
        print("\n  nested-checkout files, by top-level directory:")
        for k, v in rep["nested_by_top_level"].items():
            print(f"    {v:>7,}  {k}")
        print(f"\n  tracked basenames with a stale twin: "
              f"{rep['n_tracked_basenames_with_a_stale_twin']}")
        if rep["example_shadowed_basenames"]:
            print(f"    e.g. {', '.join(rep['example_shadowed_basenames'][:6])}")
        if rep["most_duplicated"]:
            n, c = rep["most_duplicated"]
            print(f"    most duplicated: {n} x{c}")
        print("\n  " + rep["scope_note"])

    return 1 if rep["over_threshold"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
