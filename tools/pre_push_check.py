#!/usr/bin/env python3
"""The mechanical half of the pre-push checklist.

Every contract check in `renquant_orchestrator.agent_workflows` operates on a
PR dict fetched from GitHub — it answers "is this PR compliant" AFTER the push.
Measured 2026-07-29, five separate defects in one session all happened BEFORE
that point, and each was mechanically detectable at the time:

  * a branch edited in the PRIMARY checkout on `main` instead of a worktree;
  * a branch whose base had moved, so its diff would have DELETED a file
    another PR had merged in the meantime;
  * a one-entry JSON edit reformatted the whole file (270+/270-), which does
    not break anything but makes the change unreviewable;
  * a progress doc using `EVIDENCE (§4(b)):`, which the contract checker's
    `^EVIDENCE:` match does not accept;
  * model-evaluation research committed to the orchestrator instead of
    `renquant-model` (repo placement).

Reviewers caught them. That is the expensive way to catch a category error
that `git` can answer in a second.

This runs the first four as GATES. Repo placement is reported as INFO, not a
verdict — see `placement_notes`. Claiming to enforce something this script
cannot actually decide would repeat the mistake CLAUDE.md opens by naming: a
prompt that raises compliance is not enforcement, and labelling it as such is
worse than leaving it to review.

The progress-doc contract is NOT reimplemented here; it is imported from
`agent_workflows`, so the two cannot drift.

Read-only: plain git queries. Never mutates a checkout.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from renquant_orchestrator.agent_workflows import (  # noqa: E402
    progress_doc_findings,
)

#: Checkouts an agent must never commit to directly: they are the machine's
#: own working copies, and a branch made here is one `git checkout` away from
#: disturbing whatever the operator had open.
PRIMARY_CHECKOUT_MARKERS = ("/git/github/renquant-", "/git/github/RenQuant")

#: Branches that are never a valid place to author a change.
PROTECTED_BRANCHES = ("main", "master")


@dataclass(frozen=True)
class Finding:
    check: str
    message: str
    gate: bool = True     # False => informational, does not fail the run


def _git(repo: str, *args: str) -> str | None:
    try:
        res = subprocess.run(["git", "-C", repo, *args],
                             capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def check_not_authoring_on_a_protected_branch(repo: str) -> list[Finding]:
    """A change must be authored on a feature branch, not `main`."""
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return [Finding("branch", f"cannot read the current branch in {repo}")]
    if branch in PROTECTED_BRANCHES:
        return [Finding(
            "branch",
            f"authoring on protected branch {branch!r}. Create a worktree "
            f"(`git worktree add <path> -b <branch> origin/main`) and move the "
            f"change there; a stray edit on main is one `git checkout` away "
            f"from disturbing whatever the operator had open.",
        )]
    return []


def check_base_is_current(repo: str, base: str) -> list[Finding]:
    """A stale base silently turns other people's merges into deletions."""
    behind = _git(repo, "rev-list", "--count", f"HEAD..{base}")
    if behind is None:
        return [Finding("base", f"cannot compare HEAD against {base}")]
    if int(behind) > 0:
        return [Finding(
            "base",
            f"branch is {behind} commit(s) behind {base}. Anything merged into "
            f"{base} since you branched will appear in your diff as a DELETION. "
            f"Rebase before pushing.",
        )]
    return []


def check_diff_is_scoped(repo: str, base: str) -> list[Finding]:
    """Deletions and whole-file rewrites need explicit intent."""
    out: list[Finding] = []
    names = _git(repo, "diff", "--diff-filter=D", "--name-only", base)
    if names:
        deleted = [n for n in names.splitlines() if n.strip()]
        out.append(Finding(
            "scope",
            f"{len(deleted)} file(s) DELETED relative to {base}: "
            + ", ".join(deleted[:5]) + ("; …" if len(deleted) > 5 else "")
            + ". If that is not the point of this change, your base is stale.",
        ))
    numstat = _git(repo, "diff", "--numstat", base)
    for line in (numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":
            continue
        added, removed, path = int(parts[0]), int(parts[1]), parts[2]
        # A near-total rewrite of a file that also survives is the reformat
        # signature: it passes every test and makes review impossible.
        if removed >= 50 and added >= removed * 0.9:
            out.append(Finding(
                "scope",
                f"{path}: {added} added / {removed} removed — a whole-file "
                f"rewrite. If you meant to change a few entries, an editor or "
                f"serializer reformatted the rest; redo as a targeted edit so "
                f"the diff shows what you actually changed.",
            ))
    return out


def _added_progress_docs(repo: str, base: str) -> list[str]:
    names = _git(repo, "diff", "--diff-filter=AM", "--name-only", base) or ""
    return [n for n in names.splitlines()
            if n.startswith("doc/progress/") and n.endswith(".md")]


def check_progress_doc(repo: str, base: str) -> list[Finding]:
    """Reuses the PR-time contract so the two cannot drift."""
    paths = _added_progress_docs(repo, base)
    if not paths:
        return [Finding("progress-doc",
                        "no doc/progress/<date>-<slug>.md added or modified")]
    out: list[Finding] = []
    for path in paths:
        content = _git(repo, "show", f"HEAD:{path}")
        if content is None:
            try:
                content = (Path(repo) / path).read_text(encoding="utf-8")
            except OSError:
                out.append(Finding("progress-doc", f"{path}: unreadable"))
                continue
        pr = {"files": [{"path": path}], "progressDocContent": content}
        for msg in progress_doc_findings(pr):
            out.append(Finding("progress-doc", f"{path}: {msg}"))
    return out


def placement_notes(repo: str, base: str) -> list[Finding]:
    """INFO only: which areas this change touches, so placement is a decision.

    Deliberately NOT a gate. Whether a change belongs in this repo depends on
    what the code MEANS, and a regex that guesses would either miss the real
    cases or block correct ones. Naming the touched areas and the repo's own
    boundary doc is the honest amount of help a script can give.
    """
    names = _git(repo, "diff", "--name-only", base) or ""
    tops = sorted({n.split("/")[0] for n in names.splitlines() if n.strip()})
    if not tops:
        return []
    return [Finding(
        "placement",
        f"touches {', '.join(tops)} — confirm against this repo's Hard "
        f"Boundaries in CLAUDE.md before pushing (model/eval research belongs "
        f"in renquant-model; pipeline internals in renquant-pipeline).",
        gate=False,
    )]


def run(repo: str, base: str) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_not_authoring_on_a_protected_branch(repo)
    findings += check_base_is_current(repo, base)
    findings += check_diff_is_scoped(repo, base)
    findings += check_progress_doc(repo, base)
    findings += placement_notes(repo, base)
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--skip-progress-doc", action="store_true",
                    help="for branches that legitimately carry none")
    args = ap.parse_args(argv)

    findings = [f for f in run(args.repo, args.base)
                if not (args.skip_progress_doc and f.check == "progress-doc")]
    gates = [f for f in findings if f.gate]
    for f in findings:
        marker = "BLOCK" if f.gate else "info "
        print(f"  [{marker}] {f.check}: {f.message}")
    if not gates:
        print("pre-push check: clean" if not findings
              else "pre-push check: clean (informational notes above)")
        return 0
    print(f"\npre-push check: {len(gates)} blocking finding(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
