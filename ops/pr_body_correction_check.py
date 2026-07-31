#!/usr/bin/env python3
"""A correction that lands only in the diff is half a correction (GOAL-5).

**The failure.** On 2026-07-30 review rejected renquant-model#129 not for its
content but for its **description**: the branch had already withdrawn `t(0.975,7)`,
the derived MDE, the block-count/year table, the detection floor and the
recommendation — and the PR body still presented every one of them as a conclusion.
Anyone reading the PR rather than the diff would have taken the withdrawn version
as the finding.

Sweeping my other open PRs by hand found the same shape immediately: orch#648 and
orch#646 each carried three commits, the later ones corrections, and **zero**
correction language in the body `[VERIFIED — manual sweep, 2026-07-30]`.

**Why the body is load-bearing.** On a design PR it is the *first* surface review
and readers meet. A stale body does not merely lag; it actively republishes a claim
the author has retracted, with the author's name on it.

**The check.** If a branch carries a commit whose subject announces a correction,
the PR body must acknowledge one. That is a weak condition on purpose — it cannot
judge whether the acknowledgement is *adequate*, and it is not trying to. It closes
the case where there is none at all, which is the case that actually happened three
times in one afternoon.

**A scan is not a verdict unless it read every selected PR.** The first version of
this file skipped a PR whose detail fetch failed. That is the same fail-open shape
the tool exists to catch: a partial GitHub outage would have printed a clean line
while omitting exactly the PRs it could not read `[VERIFIED — codex review of #652,
2026-07-31T00:34Z]`. Unreadable PRs are now preserved as UNMEASURABLE rows, they
stay in the denominator (`measured/selected`), and they make the command nonzero.

    python ops/pr_body_correction_check.py --repo hallovorld/renquant-orchestrator
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

#: A commit subject announcing that something previously stated is no longer true.
#: Deliberately narrow: `fix(...)` alone is NOT here. Fixing a bug in the code is
#: the normal business of a PR and says nothing about the body; retracting a CLAIM
#: is what obliges the description to move.
CORRECTION_IN_COMMIT = re.compile(
    r"\b(correct(ion|ed|s)?|withdraw(n|s)?|retract(ed|ion|s)?|supersed(e|ed|es)|"
    r"not established|no longer|was wrong|overbroad|unsafe)\b", re.I)

#: What counts as the body acknowledging one.
CORRECTION_IN_BODY = re.compile(
    r"\b(correct(ion|ed)?|withdraw(n)?|retract(ed|ion)?|supersed(ed|es)|"
    r"rewritten after|used to say|no longer)\b", re.I)

#: Per-PR outcome. UNMEASURABLE is the DEFAULT a row is born with; a row only
#: earns one of the other three by being read end to end. Nothing enumerates the
#: ways a read can fail — the ways it can SUCCEED are enumerated instead, so a
#: failure mode nobody anticipated still lands on UNMEASURABLE rather than on OK.
STATUS_UNMEASURABLE = "unmeasurable"
STATUS_STALE_BODY = "stale_body"
STATUS_ACKNOWLEDGED = "acknowledged"
STATUS_NO_CORRECTIONS = "no_corrections"

#: Exit codes.
#:
#: EXIT_UNMEASURABLE is DISTINCT from EXIT_FINDINGS and takes PRECEDENCE over it:
#: if any selected PR could not be read, the run is reported as incomplete even
#: when it also found stale bodies. The findings are still printed — they are real
#: — but the run is not a verdict on the repo, and a caller that branches on the
#: code must not be handed "1 finding" as if that were the whole answer. Both are
#: nonzero, so the common `if rc != 0` check catches either. The one thing that
#: must never happen is a partial read being indistinguishable from EXIT_OK.
EXIT_OK, EXIT_FINDINGS, EXIT_ERROR, EXIT_UNMEASURABLE = 0, 1, 2, 3


def _gh(args: list[str]) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {p.stderr.strip()[:200]}")
    return p.stdout


def list_open_prs(repo: str) -> list[dict]:
    """Scalar fields only, for every open PR.

    Measured 2026-07-30, re-measured 2026-07-31Z: asking `gh pr list` for `commits`
    across 100 open PRs fails with

        GraphQL: ... requesting up to 1,000,000 possible nodes which exceeds the
        maximum limit of 500,000

    because that field traverses to the authors connection for every commit of
    every PR. `author` on its own does NOT trip the limit and is requested here
    `[VERIFIED — gh pr list --json number,author --limit 100, rc=0, 2026-07-31Z]`;
    an earlier draft of this docstring said it did. Asking for the author in LIST
    is what lets an unreadable PR still be classified as in- or out-of-scope:
    selection no longer depends on the fetch that may fail.
    """
    return json.loads(_gh(["pr", "list", "--repo", repo, "--state", "open",
                           "--limit", "100", "--json", "number,title,body,author"]))


def commit_subjects(repo: str, number: int) -> list[str]:
    """Commit subjects for ONE PR, or raise.

    Raises rather than returning `[]` when the field is absent or empty: every PR
    has at least one commit, so an empty list means the read did not happen, and
    "no commits" would launder that into "no corrections".
    """
    detail = json.loads(_gh(["pr", "view", str(number), "--repo", repo,
                             "--json", "commits"]))
    commits = detail.get("commits")
    if not isinstance(commits, list) or not commits:
        raise RuntimeError(f"PR #{number}: commits field absent or empty")
    return [c.get("messageHeadline", "") for c in commits]


def correcting_commits(subjects: list[str]) -> list[str]:
    """Subjects that announce a retraction. The FIRST commit is excluded: a PR whose
    opening commit says 'fix' is not correcting anything it previously claimed."""
    return [s for s in subjects[1:] if CORRECTION_IN_COMMIT.search(s)]


def scan(repo: str, author: str | None) -> dict:
    """Every selected PR gets a preserved row. Selection is decided from the LIST
    payload, so a detail failure cannot remove a PR from the denominator."""
    rows: list[dict] = []
    for pr in list_open_prs(repo):
        login = (pr.get("author") or {}).get("login")
        if author and login is not None and login != author:
            continue  # demonstrably someone else's PR: out of scope, not unmeasured
        row = {"number": pr.get("number"), "title": (pr.get("title") or "")[:70],
               "status": STATUS_UNMEASURABLE, "reason": None,
               "correcting_commits": [], "body_acknowledges": None}
        rows.append(row)
        if author and login is None:
            # Cannot prove membership either way -> stays UNMEASURABLE.
            row["reason"] = "author absent from list payload; scope undecidable"
            continue
        try:
            subjects = commit_subjects(repo, row["number"])
        except Exception as exc:  # noqa: BLE001
            row["reason"] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        corr = correcting_commits(subjects)
        row["correcting_commits"] = corr
        if not corr:
            row["status"] = STATUS_NO_CORRECTIONS
            continue
        acknowledged = bool(CORRECTION_IN_BODY.search(pr.get("body") or ""))
        row["body_acknowledges"] = acknowledged
        row["status"] = STATUS_ACKNOWLEDGED if acknowledged else STATUS_STALE_BODY

    unmeasurable = [r for r in rows if r["status"] == STATUS_UNMEASURABLE]
    findings = [r for r in rows if r["status"] == STATUS_STALE_BODY]
    with_corr = [r for r in rows if r["status"] in (STATUS_STALE_BODY,
                                                    STATUS_ACKNOWLEDGED)]
    return {"repo": repo,
            "selected": len(rows),
            "measured": len(rows) - len(unmeasurable),
            "unmeasurable": unmeasurable,
            "prs_with_corrections": len(with_corr),
            "body_stale": len(findings),
            "findings": findings,
            "rows": rows}


def render(res: dict) -> list[str]:
    lines = [f"{res['repo']}: measured {res['measured']}/{res['selected']} selected "
             f"PR(s); {res['prs_with_corrections']} carry a correcting commit; "
             f"{res['body_stale']} have a body that never mentions one"]
    for f in res["findings"]:
        lines.append(f"  STALE BODY    #{f['number']}  {f['title']}")
        for c in f["correcting_commits"]:
            lines.append(f"       correcting commit: {c[:88]}")
    for u in res["unmeasurable"]:
        lines.append(f"  UNMEASURABLE  #{u['number']}  {u['title']}")
        lines.append(f"       not read: {u['reason']}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True)
    ap.add_argument("--author", default="hallovorld")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out, stale, unread = [], 0, 0
    for repo in a.repo:
        try:
            res = scan(repo, a.author)
        except Exception as exc:  # noqa: BLE001
            # The LIST query failed: not even the selected set is known.
            print(f"UNUSABLE for {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        out.append(res)
        stale += res["body_stale"]
        unread += len(res["unmeasurable"])
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for res in out:
            for line in render(res):
                print(line)
        if unread:
            print(f"INCOMPLETE: {unread} selected PR(s) could not be read; this run "
                  f"is not a clean bill of health", file=sys.stderr)
    if unread:
        return EXIT_UNMEASURABLE
    return EXIT_FINDINGS if stale else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
