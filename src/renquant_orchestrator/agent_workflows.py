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
import re
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
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
    token, _source = resolve_token_with_source(agent, explicit)
    return token


def resolve_token_with_source(
    agent: str,
    explicit: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the gh token plus the source used.

    The source is intentionally safe to print in diagnostics; the token value
    is never exposed by healthcheck output.
    """
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
    if explicit:
        return explicit, "--token"
    for var in (
        f"RENQUANT_{agent.upper()}_GH_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        val = os.environ.get(var)
        if val:
            return val, var
    return None, None


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


def github_login(token: str) -> str:
    """Return the GitHub login for a token using ``gh api user``."""
    user = _gh_json(["api", "user"], token)
    login = str((user or {}).get("login") or "")
    if not login:
        raise RuntimeError("gh api user returned no login")
    return login


def agent_identity_health(
    *,
    claude_token: Optional[str] = None,
    codex_token: Optional[str] = None,
    require_actor_tokens: bool = False,
) -> dict:
    """Verify agent tokens resolve to two distinct GitHub actors.

    This is a preflight for the attribution architecture: shared tokens make
    PR authors, review authors, and ``merged by`` audit comments ambiguous.
    ``require_actor_tokens`` excludes the generic ``GH_TOKEN`` fallback so
    strict preflight can fail before any shared ambient token is used.
    """
    overrides = {"claude": claude_token, "codex": codex_token}
    actor_tokens = _actor_token_config(
        claude_token=claude_token,
        codex_token=codex_token,
    ) if require_actor_tokens else {}
    agents: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for agent in AGENTS:
        if require_actor_tokens:
            token = actor_tokens[agent]["token"]
            source = actor_tokens[agent]["source"]
        else:
            token, source = resolve_token_with_source(agent, overrides[agent])
        row: dict[str, Any] = {
            "token_source": source,
            "token_present": bool(token),
            "login": None,
        }
        if not token:
            warnings.append(f"{agent} token is missing")
        else:
            try:
                row["login"] = github_login(token)
            except RuntimeError as exc:
                row["error"] = str(exc)
                warnings.append(f"{agent} token login lookup failed")
        agents[agent] = row

    logins = [
        str(row["login"])
        for row in agents.values()
        if row.get("login")
    ]
    if len(logins) == len(AGENTS) and len(set(logins)) != len(logins):
        warnings.append("claude and codex tokens resolve to the same GitHub login")

    return {
        "ok": not warnings,
        "agents": agents,
        "require_actor_tokens": bool(require_actor_tokens),
        "warnings": warnings,
    }


def _actor_token_config(
    *,
    claude_token: Optional[str] = None,
    codex_token: Optional[str] = None,
) -> dict[str, dict[str, Optional[str]]]:
    """Resolve actor-specific tokens for verification.

    This intentionally excludes the generic ``GH_TOKEN`` fallback. The review
    automation contract requires two separately configured actor tokens, not
    one ambient token shared by both agents.
    """
    return {
        "claude": {
            "token": claude_token or os.environ.get("RENQUANT_CLAUDE_GH_TOKEN"),
            "source": "--claude-token" if claude_token else (
                "RENQUANT_CLAUDE_GH_TOKEN"
                if os.environ.get("RENQUANT_CLAUDE_GH_TOKEN")
                else None
            ),
        },
        "codex": {
            "token": codex_token or os.environ.get("RENQUANT_CODEX_GH_TOKEN"),
            "source": "--codex-token" if codex_token else (
                "RENQUANT_CODEX_GH_TOKEN"
                if os.environ.get("RENQUANT_CODEX_GH_TOKEN")
                else None
            ),
        },
    }


# ─────────────────────────── pure policy layer ──────────────────────────

def pr_authorship(pr: dict) -> Optional[str]:
    """Return the authoring agent from labels, visible PR body, or branch."""
    labels = {lbl.get("name") for lbl in (pr.get("labels") or [])}
    for a in AGENTS:
        if f"agent:{a}" in labels:
            return a
    body = str(pr.get("body") or "")
    for a in AGENTS:
        if re.search(
            rf"(?im)^\s*(?:[-*]\s*)?(?:author|author agent)\s*:\s*`?{a}`?\s*$",
            body,
        ):
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


def checks_green(pr: dict, *, allow_no_checks: bool = False) -> bool:
    """At least one check exists and every reported check is non-failing.

    The merge workflow is a local automation gate, not GitHub branch
    protection. Treating an empty rollup as green by default would let repos
    with no CI or missing check data auto-merge under /loop. Repos that
    intentionally have no checks must opt in with ``allow_no_checks``.
    """
    roll = pr.get("statusCheckRollup") or []
    if not roll:
        return bool(allow_no_checks)
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


def build_queue(
    agent: str,
    workflow: str,
    prs: list[dict],
    *,
    allow_no_checks: bool = False,
) -> list[WorkItem]:
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
            if not checks_green(pr, allow_no_checks=allow_no_checks):
                continue
            item.note = "approved + green → mergeable"
            out.append(item)
    return out


# ─────────────────────────── gh fetch + actions ─────────────────────────

_PR_FIELDS = (
    "number,title,headRefName,headRefOid,state,isDraft,url,labels,body,"
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
        "Pre-merge audit marker: the merge command starts after this comment is posted.\n\n"
        f"- PR author agent: `{item.author_agent or 'unknown'}`\n"
        f"- Head branch: `{item.head_ref}`\n"
        f"- Head SHA: `{item.head_oid}`"
    )


_MERGE_AUDIT_FIELDS = (
    "number,title,url,author,headRefName,headRefOid,labels,body,mergedAt,mergedBy,comments"
)


def fetch_merged_prs(repo: str, token: Optional[str], limit: int = 50) -> list[dict]:
    """Fetch recent merged PRs with fields needed for merge audit."""
    return _gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            _MERGE_AUDIT_FIELDS,
        ],
        token,
    ) or []


def _parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_merge_audit_comment(body: str) -> bool:
    """Return True for visible merge audit comments."""
    return bool(re.search(r"(?im)^\s*merged\s+by\b", body or ""))


def merge_audit_status(pr: dict) -> dict:
    """Audit whether a merged PR had a visible pre-merge ``merged by`` comment."""
    merged_at = _parse_github_datetime(pr.get("mergedAt"))
    pre_merge: list[dict] = []
    post_merge: list[dict] = []
    for comment in pr.get("comments") or []:
        body = str(comment.get("body") or "")
        if not is_merge_audit_comment(body):
            continue
        created_at = _parse_github_datetime(comment.get("createdAt"))
        row = {
            "created_at": comment.get("createdAt"),
            "author": (comment.get("author") or {}).get("login"),
        }
        if merged_at is not None and created_at is not None and created_at <= merged_at:
            pre_merge.append(row)
        else:
            post_merge.append(row)

    first_pre = pre_merge[0] if pre_merge else {}
    status = "ok" if pre_merge else "missing_pre_merge_audit"
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "url": pr.get("url"),
        "agent_author": pr_authorship(pr),
        "merged_at": pr.get("mergedAt"),
        "merged_by": (pr.get("mergedBy") or {}).get("login"),
        "status": status,
        "has_pre_merge_audit": bool(pre_merge),
        "pre_merge_audit_comment_at": first_pre.get("created_at"),
        "pre_merge_audit_comment_author": first_pre.get("author"),
        "post_merge_audit_count": len(post_merge),
    }


def audit_merged_prs(repo: str, token: Optional[str], limit: int = 50) -> dict:
    """Return a JSON-ready audit of recent merged PR traceability."""
    prs = fetch_merged_prs(repo, token, limit=limit)
    rows = [merge_audit_status(pr) for pr in prs]
    missing = [row for row in rows if not row["has_pre_merge_audit"]]
    return {
        "repo": repo,
        "limit": limit,
        "n_merged_prs": len(rows),
        "n_missing_pre_merge_audit": len(missing),
        "ok": not missing,
        "prs": rows,
    }


def run_agent_workflow(
    *,
    agent: str,
    workflow: str,
    repo: str,
    token: Optional[str],
    execute: bool = False,
    merge_strategy: str = "merge",
    allow_no_checks: bool = False,
    require_distinct_actor_tokens: bool = False,
) -> dict:
    """Resolve the queue and (for merge + --execute) act on it.

    Returns a structured plan. For review/fix the plan is the worklist the
    calling agent should process; for merge with --execute the plan records
    the merge results.
    """
    prs = fetch_open_prs(repo, token)
    queue = build_queue(
        agent,
        workflow,
        prs,
        allow_no_checks=allow_no_checks,
    )
    plan: dict = {
        "agent": agent,
        "workflow": workflow,
        "repo": repo,
        "peer": other_agent(agent),
        "n_open_prs": len(prs),
        "allow_no_checks": bool(allow_no_checks),
        "require_distinct_actor_tokens": bool(require_distinct_actor_tokens),
        "queue": [w.to_dict() for w in queue],
        "executed": [],
    }
    if workflow == "merge" and execute:
        if require_distinct_actor_tokens and queue:
            identity = agent_identity_health(require_actor_tokens=True)
            plan["identity_preflight"] = identity
            if not identity["ok"]:
                plan["merge_blocked"] = True
                plan["block_reason"] = "; ".join(identity["warnings"])[:300]
                return plan
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
