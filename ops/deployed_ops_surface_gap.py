#!/usr/bin/env python3
"""31 of 80 ops surfaces are absent or stale on the machine that runs them. (GOAL-1)

Every scheduled job's plist executes out of `renquant-orchestrator-run`, not out of this
repository. `run_surface_drift_check` already alarms when that checkout's HEAD differs from
`origin/main` — but it reports a **commit mismatch**, and a commit id does not say what the
drift COSTS. This does.

MEASURED 2026-08-01, with the deployed checkout **158 commits** behind `origin/main`:

=================================================  ====
`ops/` files on `origin/main`                        80
  …present in the deployed checkout                  60
  …**entirely absent from the machine**              **20**
of the 60 present, **differing from `origin/main`**  **11**
=================================================  ====

Absent includes `ops/ops_audit.py` — **the aggregator itself** — together with
`run_ops_audit.sh`, its plist, and nine of the detectors it aggregates
(`failclosed_env_check`, `gate_stamp_parity`, `wf_cut_independence`,
`shadow_lane_preflight`, `ack_ledger_audit`, `strategy_config_primary_parity`,
`booster_identity_census`, `booster_divergence_probe`, `subrepo_pin_lag_check`).

WHY THIS IS THE FINDING AND NOT A FOOTNOTE. A detector that is merged, correct, tested and
**not on the machine** contributes exactly nothing, and it looks identical in the PR queue
to one that is protecting the book. This repo already has the rule — *merged is not
deployed* — and it keeps costing: the shadow sentinel's lane-declared-but-unwatched check
is merged and has **0 occurrences** in the deployed file, so on every scheduled run it does
not merely skip, it does not exist.

WHAT THIS TOOL DOES NOT DO. It does not sync anything. Advancing the deployed checkout is a
machine landing and an operator action; this reports the size and content of the gap so
that decision is made against a list rather than a commit count. It never writes, never
mutates a job, and never runs git against the umbrella tree.

Read-only. Uses `git ls-tree` / `git diff --quiet` against the deployed checkout only.

Exit codes: ``0`` no gap, ``1`` at least one absent or divergent surface, ``2`` usage/IO
error, ``3`` SKIPPED — the deployed checkout is missing or is not a git repository, so
nothing was established.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_RUN = Path("/Users/renhao/git/github/renquant-orchestrator-run")
DEFAULT_SUBTREE = "ops"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return r.returncode, r.stdout


def survey(run_repo: Path, ref: str, subtree: str) -> dict:
    """Absent / divergent / identical, against `ref` in the DEPLOYED checkout's own object
    store — never against this working tree.

    The comparison runs inside the deployed repo deliberately: asking THIS checkout what
    `origin/main` contains and then diffing paths by name would compare two things that
    were never fetched together, which is how a stale local ref produces a confident wrong
    answer.
    """
    if not (run_repo / ".git").exists():
        return {"status": "not_a_checkout", "run_repo": str(run_repo)}
    rc, _ = _git(run_repo, "rev-parse", "--verify", ref)
    if rc != 0:
        return {"status": "ref_unresolvable", "run_repo": str(run_repo), "ref": ref}

    rc, head = _git(run_repo, "rev-parse", "HEAD")
    rc2, target = _git(run_repo, "rev-parse", ref)
    rc3, behind = _git(run_repo, "rev-list", "--count", f"HEAD..{ref}")
    rc4, ahead = _git(run_repo, "rev-list", "--count", f"{ref}..HEAD")

    _, main_ls = _git(run_repo, "ls-tree", "-r", "--name-only", ref, "--", subtree)
    _, run_ls = _git(run_repo, "ls-tree", "-r", "--name-only", "HEAD", "--", subtree)
    on_ref = set(main_ls.split())
    on_run = set(run_ls.split())

    absent = sorted(on_ref - on_run)
    # A file the MACHINE has and the ref does not is its own condition — a retired tool
    # still installed, or a local edit. Reported, never folded into "absent".
    extra = sorted(on_run - on_ref)
    divergent = []
    for f in sorted(on_ref & on_run):
        code = subprocess.run(["git", "-C", str(run_repo), "diff", "--quiet",
                               "HEAD", ref, "--", f], capture_output=True).returncode
        if code == 1:
            divergent.append(f)
        elif code not in (0, 1):
            # Neither same nor different — an error. Recording it as divergent would
            # invent a diff; recording it as identical would hide one.
            divergent.append(f"{f} [COMPARISON FAILED rc={code}]")

    return {
        "status": "checked",
        "run_repo": str(run_repo),
        "ref": ref,
        "deployed_head": head.strip(),
        "ref_head": target.strip(),
        "commits_behind": int(behind.strip() or 0),
        "commits_ahead": int(ahead.strip() or 0),
        "n_on_ref": len(on_ref),
        "n_on_machine": len(on_run),
        "absent_from_machine": absent,
        "divergent_on_machine": divergent,
        "present_only_on_machine": extra,
        "n_gap": len(absent) + len(divergent),
        "scope_note": (
            "Reports the size and content of the gap. It does NOT sync: advancing the "
            "deployed checkout is a machine landing and an operator action. A commit "
            "count says a gap exists; this says what is in it."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-repo", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--subtree", default=DEFAULT_SUBTREE)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = survey(a.run_repo, a.ref, a.subtree)
    except OSError as exc:
        print(f"deployed-gap: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if rep["status"] != "checked":
        print(f"SKIPPED: {rep['status']} for {rep['run_repo']} — nothing was established.",
              file=sys.stderr)
        return 3

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"  deployed {rep['run_repo']}")
        print(f"    HEAD {rep['deployed_head'][:12]}  vs {rep['ref']} "
              f"{rep['ref_head'][:12]}")
        print(f"    {rep['commits_behind']} commit(s) behind, "
              f"{rep['commits_ahead']} ahead")
        print(f"\n  {a.subtree}/ on {rep['ref']}: {rep['n_on_ref']}   "
              f"on the machine: {rep['n_on_machine']}")
        print(f"    ABSENT from the machine : {len(rep['absent_from_machine'])}")
        for f in rep["absent_from_machine"]:
            print(f"        {f}")
        print(f"    DIVERGENT on the machine: {len(rep['divergent_on_machine'])}")
        for f in rep["divergent_on_machine"]:
            print(f"        {f}")
        if rep["present_only_on_machine"]:
            print(f"    present ONLY on the machine: "
                  f"{len(rep['present_only_on_machine'])}")
            for f in rep["present_only_on_machine"]:
                print(f"        {f}")
        print(f"\n  {rep['scope_note']}")

    return 1 if rep["n_gap"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
