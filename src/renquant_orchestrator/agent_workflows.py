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
  * A PR branch has one GitHub identity: its PR creator. Every GitHub commit
    attribution must resolve to that identity. A mixed-identity branch is a
    merge blocker and the owner must rebuild it from a clean base; reviewers
    never push repairs to a peer-owned branch.
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
  * An agent never reviews a PR it authored or contributed to, and never
    commits to a peer-owned PR branch.
  * An agent never appears in its own review queue.
  * ``merge`` requires: an APPROVED review on the current head, at least
    one completed check, all reported checks success, and NO stop label
    (``agent:manual-hold`` / ``agent:cost-cap`` / ``agent:rebase-conflict``).
  * Authorship is read from the canonical ``agent:<name>`` label
    (doc/ops/agent-automation.md §2.1); branch-prefix fallback for PRs
    opened before the label convention.
"""
from __future__ import annotations

import base64
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

PROGRESS_DOC_RE = re.compile(r"^doc/progress/\d{4}-\d{2}-\d{2}-[^/]+\.md$")
FIXED_BY_LOGIN_RE = re.compile(
    r"(?im)^\s*fixed\s+by\s+([a-z0-9](?:[a-z0-9-]{0,37}))\b"
)
PROGRESS_DOC_REQUIRED_FIELDS = ("STATUS:", "WHAT:", "WHY/DIR:", "EVIDENCE:", "NEXT:")
PROGRESS_EVIDENCE_FIELDS = (
    "artifact:",
    "prod or exp:",
    "existing data:",
    "best-known?:",
    "scope:",
)
PROD_PATH_RULES = (
    ("production parquet data", re.compile(r"(^|/)data/.*\.parquet$", re.IGNORECASE)),
    ("production strategy config", re.compile(r"(^|/)strategy_config\.json$", re.IGNORECASE)),
    ("live state", re.compile(r"(^|/)live_state(?:\.[^/]+)?\.json$", re.IGNORECASE)),
    ("production artifacts", re.compile(r"(^|/)artifacts/prod/", re.IGNORECASE)),
    (
        "committed walk-forward corpora",
        re.compile(
            r"(^|/)(?:artifacts/)?(?:walkforward[^/]*|wf[^/]*)/.*\.(?:parquet|csv|db|jsonl)$",
            re.IGNORECASE,
        ),
    ),
)


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


def _gh_file_text(repo: str, path: str, ref: str, token: Optional[str]) -> str:
    """Return decoded file contents for a PR head ref via the contents API."""
    payload = _gh_json(
        ["api", f"repos/{repo}/contents/{path}?ref={ref}"],
        token,
    ) or {}
    if payload.get("encoding") != "base64":
        raise RuntimeError(
            f"unsupported content encoding for {repo}:{path}@{ref}: {payload.get('encoding')!r}"
        )
    content = str(payload.get("content") or "")
    return base64.b64decode(content).decode("utf-8", errors="replace")


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
    if re.search(r"Generated with \[Claude Code\]", body, flags=re.IGNORECASE):
        return "claude"
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


def _marker_present(body: str | None, *, action: str, agent: str) -> bool:
    return f"{action} by {agent}".lower() in str(body or "").lower()


def _changed_paths(pr: dict) -> list[str]:
    return [
        str(row.get("path") or "")
        for row in (pr.get("files") or [])
        if str(row.get("path") or "")
    ]


def _progress_doc_paths(pr: dict) -> list[str]:
    return [path for path in _changed_paths(pr) if PROGRESS_DOC_RE.match(path)]


def progress_doc_findings(pr: dict) -> list[str]:
    paths = _progress_doc_paths(pr)
    findings: list[str] = []
    if not paths:
        return ["missing progress doc `doc/progress/<date>-<slug>.md`"]
    if len(paths) > 1:
        return [f"multiple progress docs present: {', '.join(paths)}"]

    content = pr.get("progressDocContent")
    if not isinstance(content, str) or not content.strip():
        return [f"progress doc content unavailable for `{paths[0]}`"]

    missing_fields = [field for field in PROGRESS_DOC_REQUIRED_FIELDS if field not in content]
    if missing_fields:
        findings.append(
            "progress doc missing required fields: " + ", ".join(missing_fields)
        )

    evidence_line = re.search(r"(?im)^EVIDENCE:\s*(.+)$", content)
    if evidence_line and evidence_line.group(1).strip().lower() != "n/a":
        lowered = content.lower()
        missing = [field for field in PROGRESS_EVIDENCE_FIELDS if field not in lowered]
        if missing:
            findings.append(
                "progress doc evidence block missing fields: " + ", ".join(missing)
            )
    return findings


def production_path_findings(pr: dict) -> list[str]:
    findings: list[str] = []
    for path in _changed_paths(pr):
        for label, pattern in PROD_PATH_RULES:
            if pattern.search(path):
                findings.append(f"writes protected production path `{path}` ({label})")
                break
    return findings


def contract_findings(pr: dict) -> list[str]:
    return (
        progress_doc_findings(pr)
        + production_path_findings(pr)
        + branch_identity_findings(pr)
    )


def _review_commit(review: dict) -> Optional[str]:
    """Commit SHA a review was submitted against, across gh JSON shapes.

    ``gh pr list/view --json reviews`` — the shape ``fetch_open_prs`` returns
    — nests the SHA as ``commit.oid``; the REST API uses a flat ``commit_id``.
    Reading only ``commit_id`` made every predicate see zero reviews at head,
    so review queues re-listed already-reviewed PRs forever and merge queues
    could never see an approval.
    """
    commit = review.get("commit")
    if isinstance(commit, dict) and commit.get("oid"):
        return str(commit["oid"])
    value = review.get("commit_id")
    return str(value) if value else None


def _reviews_at_head(pr: dict) -> list[dict]:
    head = pr.get("headRefOid")
    return [
        r for r in (pr.get("reviews") or [])
        if _review_commit(r) == head or head is None
    ]


def _submitted_at(review: dict) -> str:
    """ISO-8601 submission time (gh: ``submittedAt``; REST: ``submitted_at``)."""
    return str(review.get("submittedAt") or review.get("submitted_at") or "")


def _effective_reviews_at_head(pr: dict) -> list[dict]:
    """Latest state-changing review per reviewer on the current head.

    Mirrors GitHub's ``reviewDecision`` semantics: a reviewer's newer
    APPROVED or CHANGES_REQUESTED supersedes their earlier one. A DISMISSED
    review retracts that reviewer's prior state entirely — GitHub dismissal
    neutralizes the vote, it does not flip it to approved — unless a later
    review from the same reviewer supersedes the dismissal again. COMMENTED
    records never veto or approve and are excluded here (findings-scanning
    that needs COMMENTED bodies, e.g. ``has_unaddressed_findings``, reads
    the raw review list instead). Without this reduction a reviewer who
    requested changes and later approved the same head would block
    ``is_approved`` — and therefore the review/merge queues — forever.
    """
    latest: dict[str, dict] = {}
    for idx, review in enumerate(_reviews_at_head(pr)):
        if review.get("state") not in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            continue
        key = _login(review.get("author") or review.get("user")) or f"#anon-{idx}"
        prev = latest.get(key)
        if prev is None or _submitted_at(review) >= _submitted_at(prev):
            latest[key] = review
    return [r for r in latest.values() if r.get("state") != "DISMISSED"]


def _login(value: Any) -> str:
    """Normalize a GitHub actor value from ``gh`` JSON."""
    if isinstance(value, dict):
        value = value.get("login")
    return str(value or "").casefold()


def commit_contributor_logins(pr: dict) -> frozenset[str]:
    """Return GitHub logins attributed to commits on this PR branch."""
    logins: set[str] = set()
    for commit in pr.get("commits") or []:
        for author in commit.get("authors") or []:
            login = _login(author)
            if login:
                logins.add(login)
    return frozenset(logins)


def branch_identity_findings(pr: dict) -> list[str]:
    """Return merge-blocking findings for a mixed-identity PR branch.

    GitHub exposes commit co-authors here. In this control plane they are not
    advisory: a co-author trailer or a direct peer push both produce a branch
    whose attribution can no longer support an independent review/merge
    decision. The PR owner must recreate the head from a clean base under its
    own GitHub identity.
    """
    owner = _login(pr.get("author"))
    contributors = commit_contributor_logins(pr)
    if not contributors:
        return []
    if not owner:
        return [
            "cannot verify single-owner branch identity: PR creator login is missing"
        ]
    unexpected = sorted(login for login in contributors if login != owner)
    if not unexpected:
        return []
    listed = ", ".join(f"`{login}`" for login in unexpected)
    return [
        "mixed GitHub commit attribution on a single-owner PR branch: "
        f"creator `{owner}`; additional attribution {listed}. PR owner must "
        "rebuild/squash the branch from the target base without Co-Authored-By "
        "trailers or peer commits."
    ]


def explicit_contributor_logins(pr: dict) -> frozenset[str]:
    """Return reviewers who explicitly disclosed a direct fix on this PR.

    A visible marker is the reliable, auditable attribution surface when
    GitHub commit co-author data is ambiguous. The marker deliberately uses
    the GitHub login, not the logical agent name, so it can be compared to
    the review actor without a local account mapping.
    """
    logins: set[str] = set()
    for item in [*(pr.get("comments") or []), *(pr.get("reviews") or [])]:
        match = FIXED_BY_LOGIN_RE.search(str(item.get("body") or ""))
        if match:
            logins.add(_login(match.group(1)))
    return frozenset(logins)


def reviewer_is_pr_contributor(pr: dict, reviewer_login: str | None) -> bool:
    """Whether a reviewer explicitly disclosed a direct fix on this PR."""
    login = _login(reviewer_login)
    return bool(login) and login in explicit_contributor_logins(pr)


def review_is_independent(pr: dict, review: dict) -> bool:
    """An approval is independent only when its author did not contribute."""
    return not reviewer_is_pr_contributor(pr, _login(review.get("author")))


def has_head_approval_from_agent(pr: dict, agent: str) -> bool:
    revs = _effective_reviews_at_head(pr)
    if any(r.get("state") == "CHANGES_REQUESTED" for r in revs):
        return False
    return any(
        r.get("state") == "APPROVED"
        and _marker_present(r.get("body"), action="reviewed", agent=agent)
        and review_is_independent(pr, r)
        for r in revs
    )


def has_head_changes_requested_from_agent(pr: dict, agent: str) -> bool:
    """This agent's effective review on the current head requests changes.

    Once the agent has recorded findings against the exact head, re-queueing
    the PR for review only produces duplicate reviews; the next move is the
    author's fix push, which changes the head and re-opens review.
    """
    return any(
        r.get("state") == "CHANGES_REQUESTED"
        and _marker_present(r.get("body"), action="reviewed", agent=agent)
        for r in _effective_reviews_at_head(pr)
    )


def is_approved(pr: dict) -> bool:
    """The effective review state on the current head is approval.

    Effective = latest state-changing review per reviewer (GitHub
    ``reviewDecision`` semantics): at least one APPROVED, none
    CHANGES_REQUESTED.
    """
    revs = _effective_reviews_at_head(pr)
    if any(r.get("state") == "CHANGES_REQUESTED" for r in revs):
        return False
    return any(
        r.get("state") == "APPROVED" and review_is_independent(pr, r)
        for r in revs
    )


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

    Signal (conservative): an effective CHANGES_REQUESTED review on the
    current head, OR a review/comment carrying a severity tag
    (BLOCKER/HIGH/MED) at the current head. A reviewer's CHANGES_REQUESTED
    (or APPROVED) superseded by their own later state-changing review no
    longer counts — that per-reviewer reduction is exactly what
    ``_effective_reviews_at_head`` gives us, so its bodies are used as-is.
    But that reduction correctly drops COMMENTED reviews for vote-counting
    purposes — a COMMENTED review never flips ``reviewDecision`` and never
    supersedes/gets superseded — which is the WRONG reduction for
    findings-scanning: a COMMENTED review can still carry a severity-tagged
    finding that needs a fix. So COMMENTED review bodies at head are added
    back in unreduced, on top of (not instead of) the vote-reduced bodies.
    The agent itself makes the final read of what to fix; this just decides
    whether the PR belongs in the fix queue.
    """
    revs = _effective_reviews_at_head(pr)
    if any(r.get("state") == "CHANGES_REQUESTED" for r in revs):
        return True
    commented_at_head = [r for r in _reviews_at_head(pr) if r.get("state") == "COMMENTED"]
    blob = " ".join(
        str(r.get("body") or "") for r in revs
    ) + " " + " ".join(
        str(r.get("body") or "") for r in commented_at_head
    ) + " " + " ".join(
        str(c.get("body") or "") for c in (pr.get("comments") or [])
    )
    return bool(re.search(r"\b(BLOCKER|HIGH|MED)\b", blob))


def has_review_findings_history(pr: dict) -> bool:
    blob = " ".join(
        str(r.get("state") or "") + " " + str(r.get("body") or "")
        for r in (pr.get("reviews") or [])
    ) + " " + " ".join(
        str(c.get("body") or "") for c in (pr.get("comments") or [])
    )
    return bool(re.search(r"\b(CHANGES_REQUESTED|BLOCKER|HIGH|MED)\b", blob))


def has_fix_marker(pr: dict, agent: str) -> bool:
    return any(
        _marker_present(c.get("body"), action="fixed", agent=agent)
        for c in (pr.get("comments") or [])
    )


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
    reviewer_login: str | None = None,
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
        peer_approved = has_head_approval_from_agent(pr, agent)
        findings = contract_findings(pr)
        author_needs_fix_marker = has_review_findings_history(pr) and not has_fix_marker(pr, author or "")
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
            # Review the OTHER agent's PRs only, and never a PR this GitHub
            # actor explicitly fixed. Mixed branch attribution is a hard
            # finding; reviewers must not repair the peer branch.
            if author != peer:
                continue
            if reviewer_is_pr_contributor(pr, reviewer_login):
                continue
            if stop:
                continue
            if peer_approved and not findings:
                continue  # already has a clean approval — nothing to add
            if has_head_changes_requested_from_agent(pr, agent):
                # This agent already recorded findings against this exact
                # head; re-reviewing it would only duplicate the review.
                # The author's fix push (a new head) re-opens review.
                continue
            notes = list(findings)
            if is_approved(pr) and not peer_approved:
                notes.append(f"missing `reviewed by {agent}` approval marker on head review")
            if notes:
                item.note = "; ".join(notes)
            out.append(item)
        elif workflow == "fix":
            # Fix YOUR OWN PRs that carry unaddressed findings.
            if author != agent:
                continue
            if stop:
                continue
            needs_findings_fix = has_unaddressed_findings(pr, agent)
            needs_contract_fix = bool(findings)
            needs_fix_marker = bool(author) and author_needs_fix_marker
            if not (needs_findings_fix or needs_contract_fix or needs_fix_marker):
                continue
            notes: list[str] = []
            if needs_findings_fix:
                notes.append("has unaddressed review findings")
            notes.extend(findings)
            if needs_fix_marker:
                notes.append(f"missing `fixed by {agent}` audit comment")
            item.note = "; ".join(notes)
            out.append(item)
        elif workflow == "merge":
            # Merge YOUR OWN PRs that are approved + green + unblocked.
            if author != agent:
                continue
            if stop:
                item.note = f"blocked by {stop}"
                continue
            if findings:
                item.note = "; ".join(findings)
                continue
            if author_needs_fix_marker:
                item.note = f"missing `fixed by {agent}` audit comment"
                continue
            if not has_head_approval_from_agent(pr, peer):
                continue
            if not checks_green(pr, allow_no_checks=allow_no_checks):
                continue
            item.note = f"approved by `{peer}` + green + contract-clean → mergeable"
            out.append(item)
    return out


# ─────────────────────────── gh fetch + actions ─────────────────────────

_PR_FIELDS = (
    "number,title,headRefName,headRefOid,state,isDraft,url,labels,body,"
    "reviews,statusCheckRollup,comments,author"
)


def fetch_open_prs(repo: str, token: Optional[str]) -> list[dict]:
    """Fetch open PRs with the fields build_queue needs."""
    prs = _gh_json(
        ["pr", "list", "--repo", repo, "--state", "open",
         "--limit", "100", "--json", _PR_FIELDS],
        token,
    ) or []
    for pr in prs:
        number = pr.get("number")
        if number is None:
            continue
        detail = _gh_json(
            ["pr", "view", str(number), "--repo", repo, "--json", "files,commits"],
            token,
        ) or {}
        pr["files"] = detail.get("files") or []
        pr["commits"] = detail.get("commits") or []
        progress_paths = _progress_doc_paths(pr)
        if len(progress_paths) == 1:
            try:
                pr["progressDocContent"] = _gh_file_text(
                    repo,
                    progress_paths[0],
                    str(pr.get("headRefName") or ""),
                    token,
                )
            except RuntimeError:
                # The progress-doc path is present in the diff (e.g. a revert
                # PR that deletes it) but no longer exists at head, so the
                # contents API 404s. Leave progressDocContent unset rather
                # than letting the fetch failure propagate: an uncaught
                # exception here previously crashed plan-building for the
                # WHOLE repo over one PR's deleted file, hiding every other
                # PR's queue entry too. progress_doc_findings() already
                # reports "content unavailable" for a missing
                # progressDocContent, which is the correct, actionable
                # finding for this case.
                pass
    return prs


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
    reviewer_login: str | None = None
    if workflow == "review" and any(pr.get("commits") for pr in prs):
        reviewer_login = github_login(token) if token else _login(
            _gh_json(["api", "user"], None)
        )
    queue = build_queue(
        agent,
        workflow,
        prs,
        allow_no_checks=allow_no_checks,
        reviewer_login=reviewer_login,
    )
    plan: dict = {
        "agent": agent,
        "workflow": workflow,
        "repo": repo,
        "peer": other_agent(agent),
        "n_open_prs": len(prs),
        "allow_no_checks": bool(allow_no_checks),
        "require_distinct_actor_tokens": bool(require_distinct_actor_tokens),
        "reviewer_login": reviewer_login,
        "queue": [w.to_dict() for w in queue],
        "executed": [],
    }
    if workflow == "review" and reviewer_login:
        plan["reviewer_separation_exclusions"] = [
            {
                "number": pr.get("number"),
                "url": pr.get("url"),
                "reason": "current reviewer disclosed a direct PR fix",
            }
            for pr in prs
            if reviewer_is_pr_contributor(pr, reviewer_login)
        ]
        plan["branch_identity_violations"] = [
            {
                "number": pr.get("number"),
                "url": pr.get("url"),
                "reason": "; ".join(branch_identity_findings(pr)),
            }
            for pr in prs
            if branch_identity_findings(pr)
        ]
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
            + ("read the diff plus the PR progress doc, enforce the agent control contract, and post "
               "ONE consolidated review with your token. Check for the committed "
               "`doc/progress/<date>-<slug>.md`, protect production paths, and reject unsupported "
               "model/data conclusions that lack the documented evidence block. "
               f"The review body must include visible text `reviewed by {agent}` "
               "(gh pr review --approve|--request-changes|--comment) — "
               "request changes only for BLOCKER/HIGH/MED."
               if workflow == "review" else
               "read the review findings, make the smallest fix, add or repair the committed "
               "`doc/progress/<date>-<slug>.md` when required, avoid protected production paths, run "
               f"focused tests, then comment `fixed by {agent}`, commit only under "
               "the PR creator identity (no Co-Authored-By trailer), and push. "
               "Never push to a peer-owned PR branch; request a clean owner rebuild instead.")
        )
    return plan
