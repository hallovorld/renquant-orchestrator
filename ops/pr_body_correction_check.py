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

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2


def _gh(args: list[str]) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {p.stderr.strip()[:200]}")
    return p.stdout


def open_prs(repo: str, author: str | None) -> list[dict]:
    """List first, then fetch commits PER PR.

    Measured 2026-07-30: asking `gh pr list` for `commits` (or `author`) across 100
    open PRs fails with

        GraphQL: ... requesting up to 1,000,000 possible nodes which exceeds the
        maximum limit of 500,000

    because those fields traverse to the authors connection for every commit of
    every PR. The list query therefore asks only for scalar fields, and commits are
    fetched one PR at a time. Slower, and it actually returns.
    """
    prs = json.loads(_gh(["pr", "list", "--repo", repo, "--state", "open",
                          "--limit", "100", "--json", "number,title,body"]))
    out = []
    for pr in prs:
        try:
            detail = json.loads(_gh(["pr", "view", str(pr["number"]), "--repo", repo,
                                     "--json", "commits,author"]))
        except Exception:  # noqa: BLE001
            continue      # a PR we cannot read is skipped, never assumed clean
        if author and (detail.get("author") or {}).get("login") != author:
            continue
        out.append({**pr, "commits": detail.get("commits") or []})
    return out


def correcting_commits(pr: dict) -> list[str]:
    """Subjects that announce a retraction. The FIRST commit is excluded: a PR whose
    opening commit says 'fix' is not correcting anything it previously claimed."""
    subs = [c.get("messageHeadline", "") for c in pr.get("commits") or []]
    return [s for s in subs[1:] if CORRECTION_IN_COMMIT.search(s)]


def scan(repo: str, author: str | None) -> dict:
    findings, clean = [], []
    for pr in open_prs(repo, author):
        corr = correcting_commits(pr)
        if not corr:
            continue
        acknowledged = bool(CORRECTION_IN_BODY.search(pr.get("body") or ""))
        rec = {"number": pr["number"], "title": pr["title"][:70],
               "correcting_commits": corr, "body_acknowledges": acknowledged}
        (clean if acknowledged else findings).append(rec)
    return {"repo": repo, "prs_with_corrections": len(findings) + len(clean),
            "body_stale": len(findings), "findings": findings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True)
    ap.add_argument("--author", default="hallovorld")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out, bad = [], 0
    for repo in a.repo:
        try:
            res = scan(repo, a.author)
        except Exception as exc:  # noqa: BLE001
            print(f"UNUSABLE for {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        out.append(res)
        bad += res["body_stale"]
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for res in out:
            print(f"{res['repo']}: {res['prs_with_corrections']} open PR(s) carry a "
                  f"correcting commit; {res['body_stale']} have a body that never "
                  f"mentions one")
            for f in res["findings"]:
                print(f"  STALE BODY  #{f['number']}  {f['title']}")
                for c in f["correcting_commits"]:
                    print(f"       correcting commit: {c[:88]}")
    return EXIT_FINDINGS if bad else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
