#!/usr/bin/env python3
"""How far behind `origin/main` is each checkout the scheduled jobs actually run from?

`ops/run_surface_drift_check.py` validates `.subrepo_runtime/repos/*` against the pins
in `subrepos.lock.json`. That answers *"does the runtime checkout match the lock?"* — a
question about **internal consistency between two copies**. It never asks whether the
lock pin is itself current, so a lock pinned to an old commit reports clean forever.

Measured 2026-07-30, which is why this exists:

* `.subrepo_runtime/repos/renquant-orchestrator` — the copy the drift scan checks —
  is **195 commits** behind `origin/main`;
* `renquant-orchestrator-run` — the copy **17 launchd jobs actually execute** — is
  **110 commits** behind;
* neither contains `effective_train_cutoff_date`, merged that morning, so every artifact
  trained since keeps failing the WF gate's cutoff contract, correctly.

The subject here is therefore taken from **what the jobs reference**, not from a separate
list that can fall out of step with them: every absolute path in
`ops/launchd_manifest.json`'s `program_args` is resolved to its enclosing git checkout,
and each distinct checkout is measured against `origin/main`.

**The bound is CHOSEN, not derived, and is stated as such.** Alarming on any drift at all
would fire every time a PR merges and be muted within a day; alarming only on a large
number lets a week of fixes sit unshipped. 20 commits is roughly two review cycles on this
repo's current cadence. It is a judgement call and it is the only number here that is not
a measurement.

**Read-only.** Runs `git` **only** against checkouts under the GitHub root — never inside
the umbrella, where a sub-agent's `git reset --hard` once caused an incident. Writes
nothing.

Exit codes: ``0`` every referenced checkout is within the bound, ``1`` one is not or a
reference cannot be resolved, ``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

MANIFEST = Path(__file__).resolve().parent / "launchd_manifest.json"
GITHUB = Path(os.environ.get("RQ_GITHUB_ROOT", "/Users/renhao/git/github"))
UMBRELLA_NAME = "RenQuant"

#: Chosen, not derived — see the module docstring.
MAX_COMMITS_BEHIND = 20

_ABS = re.compile(rf"^{re.escape(str(GITHUB))}/([^/]+)/")


def reference_repo_for(name: str) -> str:
    """The checkout whose `origin/main` is trusted as the reference for `name`.

    A `-run` checkout is a deployment copy of its dev sibling; its own remote-tracking
    refs may be arbitrarily old. The dev checkout is the one this process fetches, so it
    is the only place a current `origin/main` is guaranteed.
    """
    return name[:-4] if name.endswith("-run") else name


def referenced_checkouts(manifest: Path) -> dict[str, list[str]]:
    """checkout name -> the job labels that reference it, from program_args."""
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    jobs = raw.get("jobs", raw)
    items = jobs.items() if isinstance(jobs, dict) else jobs
    out: dict[str, list[str]] = defaultdict(list)
    for label, cfg in items:
        for arg in (cfg or {}).get("program_args", []):
            m = _ABS.match(str(arg))
            if m:
                out[m.group(1)].append(label)
    return {k: sorted(set(v)) for k, v in out.items()}


def measure(name: str) -> dict[str, Any]:
    """HEAD and distance from origin/main for one checkout. Never raises."""
    repo = GITHUB / name
    out: dict[str, Any] = {"checkout": name, "path": str(repo)}
    if name == UMBRELLA_NAME:
        # The umbrella is a live shared tree and is NOT measured here: running git
        # inside it is forbidden on this programme. Reported so its absence from the
        # numbers is visible rather than silently assumed fine.
        out.update(status="SKIPPED_UMBRELLA",
                   detail="git is never run inside the umbrella; its freshness needs a "
                          "different mechanism")
        return out
    if not (repo / ".git").exists():
        out.update(status="NOT_A_CHECKOUT", detail=f"{repo} is not a git checkout")
        return out
    # The distance is counted in the REFERENCE checkout, never in the one being
    # measured. A run checkout that has not fetched carries a stale `origin/main` ref
    # and, asked to compare itself against it, reports 0 behind --- it is comparing a
    # copy to its own outdated idea of the truth. That is the exact defect this tool
    # exists to catch, and the first version of this function had it: it reported
    # `renquant-orchestrator-run` as 0 behind while a fetched reference put it at 110.
    ref_repo = GITHUB / reference_repo_for(name)
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=30).stdout
        if not head:
            out.update(status="UNMEASURABLE", detail="could not read HEAD")
            return out
        # Fetch ONLY in the reference checkout, which is a dev tree we own --- and
        # REQUIRE it to succeed. Discarding this return code recreates the very
        # failure this tool exists to detect, one layer deeper: a network or auth
        # failure leaves the reference's own origin/main stale, and the rev-list
        # below then reports a confident FRESH against an old ref. An unfetched
        # reference is not a current reference.
        fetched = subprocess.run(["git", "-C", str(ref_repo), "fetch", "-q", "origin"],
                                 capture_output=True, text=True, timeout=180)
        if fetched.returncode != 0:
            out.update(status="UNMEASURABLE",
                       detail=f"fetch failed in the reference checkout {ref_repo} "
                              f"({fetched.returncode}): "
                              f"{fetched.stderr.strip()[:160]} — refusing to measure "
                              f"against a possibly stale origin/main")
            return out
        # And confirm origin/main actually resolves AFTER the fetch: a fetch can
        # succeed against a remote that has no main, which would leave rev-list
        # comparing against nothing.
        resolved = subprocess.run(
            ["git", "-C", str(ref_repo), "rev-parse", "--verify", "--quiet",
             "origin/main"], capture_output=True, text=True, timeout=30)
        if resolved.returncode != 0 or not resolved.stdout.strip():
            out.update(status="UNMEASURABLE",
                       detail=f"origin/main does not resolve in {ref_repo} after a "
                              f"successful fetch — there is no reference to measure "
                              f"against")
            return out
        behind = subprocess.run(
            ["git", "-C", str(ref_repo), "rev-list", "--count", f"{head}..origin/main"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        out.update(status="UNMEASURABLE", detail=f"{type(exc).__name__}: {exc}")
        return out
    out["reference_checkout"] = str(ref_repo)
    head = head[:9]
    if not behind.isdigit():
        out.update(status="UNMEASURABLE",
                   detail=f"could not count commits behind origin/main ({behind!r}) — "
                          f"is origin/main fetched in this checkout?")
        return out
    n = int(behind)
    out.update(head=head, commits_behind=n, dirty_files=len(dirty.splitlines()),
               status="FRESH" if n <= MAX_COMMITS_BEHIND else "STALE")
    if out["status"] == "STALE":
        out["detail"] = (f"{n} commits behind origin/main (bound {MAX_COMMITS_BEHIND}) — "
                         f"anything merged in those commits is NOT what runs")
    return out


def scan(manifest: Path = MANIFEST) -> dict[str, Any]:
    refs = referenced_checkouts(manifest)
    results = []
    for name in sorted(refs):
        r = measure(name)
        r["referenced_by_jobs"] = len(refs[name])
        r["example_jobs"] = refs[name][:3]
        results.append(r)
    return {
        "max_commits_behind": MAX_COMMITS_BEHIND,
        "checkouts_referenced": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = scan(args.manifest)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not report["results"]:
        print("FATAL: no absolute checkout paths found in program_args — nothing checked",
              file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for r in report["results"]:
            line = (f"{r['status']:18} {r['checkout'][:34]:34} "
                    f"{r.get('commits_behind', '-'):>5} behind  "
                    f"{r['referenced_by_jobs']:>3} job(s)")
            print(line)
            if r.get("detail"):
                print(f"{'':18}   {r['detail']}")
    bad = [r for r in report["results"]
           if r["status"] in ("STALE", "NOT_A_CHECKOUT", "UNMEASURABLE")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
