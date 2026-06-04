"""Orchestrator-driven multi-agent PR workflows (review / fix / merge).

This is the local-agent replacement for the GitHub-event/CI-CD review
automation. The agents (Claude Code CLI, Codex CLI) ARE the LLMs, so we
do not need cloud Actions to invoke a model. The orchestrator owns the
deterministic parts — **queue resolution, policy, and merging** — and the
agent drives the judgment parts (writing a review, writing a fix).

Three workflows, defined per agent:

  review : the OTHER agent's open PRs that this agent should review.
  fix    : this agent's OWN open PRs that have unaddressed review findings.
  merge  : this agent's OWN open PRs that are approved + green + unblocked
           — the orchestrator merges these directly (no LLM needed).

Identity / token
----------------
``--as <agent>`` selects which GitHub token to use, resolved from (in
order): ``--token``, env ``RENQUANT_<AGENT>_GH_TOKEN`` (e.g.
``RENQUANT_CLAUDE_GH_TOKEN``), env ``GH_TOKEN``/``GITHUB_TOKEN``. Giving
each agent its OWN token means:
  * commits / reviews / merges are attributed to that agent, and
  * GitHub's native "you cannot approve your own pull request" rule
    enforces the review-separation invariant for free — an agent
    literally cannot self-approve, so an APPROVED review on a PR is
    always a genuine second opinion.
  * Every agent-authored review/fix comment should also carry visible
    ``reviewed by <agent>`` / ``fixed by <agent>`` text because GitHub
    account attribution alone is not enough when agents share operator
    accounts or co-authored commits.
  * Before any orchestrator merge, the workflow posts a visible
    ``merged by <agent>`` PR comment and only merges if that audit comment
    succeeds.

Trigger model
-------------
The user (or a ``/loop``) tells an agent to run a workflow. For
``review``/``fix`` the agent calls ``agent-workflow ... --workflow review``
to get its JSON worklist, then processes each item (read diff → post
review; read findings → edit + push) with its own token. For ``merge``
the orchestrator executes ``gh pr merge`` directly under ``--execute``.

Policy (encoded here, not in CI)
--------------------------------
  * An agent never reviews its own PR (queue excludes self-authored).
  * An agent never appears in its own review queue.
  * ``merge`` requires: an APPROVED review on the current head, at least
    one completed check, all reported checks success, and NO stop label
    (``agent:manual-hold`` / ``agent:cost-cap`` / ``agent:rebase-conflict``).
  * Authorship is read from the canonical ``agent:<name>`` label
    (doc/ops/agent-automation.md §2.1); branch-prefix fallback for PRs
    opened before the label convention.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

#: Canonical agents. The "other" agent is who you review.
AGENTS = ("claude", "codex")

#: Labels that block any merge regardless of approval/checks.
STOP_LABELS = ("agent:manual-hold", "agent:cost-cap", "agent:rebase-conflict")


def other_agent(agent: str) -> str:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
    return "codex" if agent == "claude" else "claude"


def resolve_token(agent: str, explicit: Optional[str] = None) -> Optional[str]:
    """Resolve the gh token for an agent (see module docstring order)."""
    if explicit:
        return explicit
    for var in (
        f"RENQUANT_{agent.upper()}_GH_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        val = os.environ.get(var)
        if val:
            return val
    return None


# ─────────────────────────── gh shell layer ────────────────────────────

def _gh_json(args: Sequence[str], token: Optional[str]) -> Any:
    """Run ``gh <args>`` with the agent token and parse stdout as JSON."""
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True, text=True, env=env, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def _gh_run(args: Sequence[str], token: Optional[str]) -> tuple[int, str]:
    """Run ``gh <args>`` for an action (merge/comment); return (rc, output)."""
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True, text=True, env=env, check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


# ─────────────────────────── pure policy layer ──────────────────────────

def pr_authorship(pr: dict) -> Optional[str]:
    """Return the authoring agent from labels, else branch-prefix fallback."""
    labels = {lbl.get("name") for lbl in (pr.get("labels") or [])}
    for a in AGENTS:
        if f"agent:{a}" in labels:
            return a
    head = str(pr.get("headRefName") or "")
    for a in AGENTS:
        if head.startswith(f"{a}/"):
            return a
    return None


def has_stop_label(pr: dict) -> Optional[str]:
    labels = {lbl.get("name") for lbl in (pr.get("labels") or [])}
    for s in STOP_LABELS:
        if s in labels:
            return s
    return None


def _reviews_at_head(pr: dict) -> list[dict]:
    head = pr.get("headRefOid")
    return [r for r in (pr.get("reviews") or []) if r.get("commit_id") == head or head is None]


def is_approved(pr: dict) -> bool:
    """An APPROVED review exists on the current head and none requests changes."""
    revs = _reviews_at_head(pr)
    if any(r.get("state") == "CHANGES_REQUESTED" for r in revs):
        return False
    return any(r.get("state") == "APPROVED" for r in revs)


def checks_green(pr: dict) -> bool:
    """At least one check exists and every reported check is non-failing.

    The merge workflow is a local automation gate, not GitHub branch
    protection. Treating an empty rollup as green would let repos with no CI
    or missing check data auto-merge under /loop.
    """
    roll = pr.get("statusCheckRollup") or []
    if not roll:
        return False
    for c in roll:
        concl = (c.get("conclusion") or "").upper()
        status = (c.get("status") or "").upper()
        if status and status != "COMPLETED":
            return False  # pending / in_progress
        if concl and concl not in ("SUCCESS", "SKIPPED", "NEUTRAL"):
            return False
    return True


def has_unaddressed_findings(pr: dict, agent: str) -> bool:
    """True if there's a review/comment with findings the author hasn't yet
    superseded with a newer push.

    Signal (conservative): a CHANGES_REQUESTED review on the current head,
    OR a review/comment carrying a severity tag (BLOCKER/HIGH/MED) at the
    current head. The agent itself makes the final read of what to fix; this
    just decides whether the PR belongs in the fix queue.
    """
    revs = _reviews_at_head(pr)
    if any(r.get("state") == "CHANGES_REQUESTED" for r in revs):
        return True
    blob = " ".join(
        str(r.get("body") or "") for r in revs
    ) + " " + " ".join(
        str(c.get("body") or "") for c in (pr.get("comments") or [])
    )
    import re
    return bool(re.search(r"\b(BLOCKER|HIGH|MED)\b", blob))


@dataclass
class WorkItem:
    number: int
    title: str
    head_ref: str
    head_oid: str
    author_agent: Optional[str]
    url: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "number": self.number, "title": self.title,
            "head_ref": self.head_ref, "head_oid": self.head_oid,
            "author_agent": self.author_agent, "url": self.url, "note": self.note,
        }


def build_queue(agent: str, workflow: str, prs: list[dict]) -> list[WorkItem]:
    """Pure queue resolution over a list of PR dicts (unit-testable)."""
    if workflow not in ("review", "fix", "merge"):
        raise ValueError(f"unknown workflow {workflow!r}")
    peer = other_agent(agent)
    out: list[WorkItem] = []
    for pr in prs:
        if pr.get("state") and pr.get("state") != "OPEN":
            continue
        if pr.get("isDraft"):
            continue
        author = pr_authorship(pr)
        stop = has_stop_label(pr)
        item = WorkItem(
            number=pr.get("number"),
            title=str(pr.get("title") or ""),
            head_ref=str(pr.get("headRefName") or ""),
            head_oid=str(pr.get("headRefOid") or ""),
            author_agent=author,
            url=str(pr.get("url") or ""),
        )
        if workflow == "review":
            # Review the OTHER agent's PRs only; never your own.
            if author != peer:
                continue
            if stop:
                continue
            if is_approved(pr):
                continue  # already has a clean approval — nothing to add
            out.append(item)
        elif workflow == "fix":
            # Fix YOUR OWN PRs that carry unaddressed findings.
            if author != agent:
                continue
            if stop:
                continue
            if not has_unaddressed_findings(pr, agent):
                continue
            item.note = "has unaddressed review findings"
            out.append(item)
        elif workflow == "merge":
            # Merge YOUR OWN PRs that are approved + green + unblocked.
            if author != agent:
                continue
            if stop:
                item.note = f"blocked by {stop}"
                continue
            if not is_approved(pr):
                continue
            if not checks_green(pr):
                continue
            item.note = "approved + green → mergeable"
            out.append(item)
    return out


# ─────────────────────────── gh fetch + actions ─────────────────────────

_PR_FIELDS = (
    "number,title,headRefName,headRefOid,state,isDraft,url,labels,"
    "reviews,statusCheckRollup,comments,author"
)


def fetch_open_prs(repo: str, token: Optional[str]) -> list[dict]:
    """Fetch open PRs with the fields build_queue needs."""
    return _gh_json(
        ["pr", "list", "--repo", repo, "--state", "open",
         "--limit", "100", "--json", _PR_FIELDS],
        token,
    ) or []


def merge_pr(repo: str, number: int, token: Optional[str], strategy: str = "merge") -> tuple[int, str]:
    return _gh_run(
        ["pr", "merge", str(number), "--repo", repo, f"--{strategy}", "--delete-branch"],
        token,
    )


def comment_pr(repo: str, number: int, body: str, token: Optional[str]) -> tuple[int, str]:
    """Post a PR comment through gh."""
    return _gh_run(["pr", "comment", str(number), "--repo", repo, "--body", body], token)


def merge_audit_comment(agent: str, item: WorkItem) -> str:
    """Visible audit comment posted immediately before an automated merge."""
    return (
        f"merged by `{agent}` via `renquant-orchestrator agent-workflow merge --execute`\n\n"
        f"- PR author agent: `{item.author_agent or 'unknown'}`\n"
        f"- Head branch: `{item.head_ref}`\n"
        f"- Head SHA: `{item.head_oid}`"
    )


def run_agent_workflow(
    *,
    agent: str,
    workflow: str,
    repo: str,
    token: Optional[str],
    execute: bool = False,
    merge_strategy: str = "merge",
) -> dict:
    """Resolve the queue and (for merge + --execute) act on it.

    Returns a structured plan. For review/fix the plan is the worklist the
    calling agent should process; for merge with --execute the plan records
    the merge results.
    """
    prs = fetch_open_prs(repo, token)
    queue = build_queue(agent, workflow, prs)
    plan: dict = {
        "agent": agent,
        "workflow": workflow,
        "repo": repo,
        "peer": other_agent(agent),
        "n_open_prs": len(prs),
        "queue": [w.to_dict() for w in queue],
        "executed": [],
    }
    if workflow == "merge" and execute:
        for w in queue:
            comment_rc, comment_out = comment_pr(
                repo,
                w.number,
                merge_audit_comment(agent, w),
                token,
            )
            if comment_rc != 0:
                plan["executed"].append({
                    "number": w.number,
                    "merged": False,
                    "commented": False,
                    "output": comment_out[:300],
                })
                continue
            rc, out = merge_pr(repo, w.number, token, strategy=merge_strategy)
            plan["executed"].append({
                "number": w.number, "merged": rc == 0, "commented": True, "output": out[:300],
            })
    elif workflow in ("review", "fix"):
        plan["instructions"] = (
            f"Agent '{agent}' should process each queued PR: "
            + ("read the diff and post ONE consolidated review with your token. "
               f"The review body must include visible text `reviewed by {agent}` "
               "(gh pr review --approve|--request-changes|--comment) — "
               "request changes only for BLOCKER/HIGH/MED."
               if workflow == "review" else
               "read the review findings, make the smallest fix, run focused "
               f"tests, then comment `fixed by {agent}`, commit (with your "
               "Co-Authored-By trailer), and push.")
        )
    return plan
