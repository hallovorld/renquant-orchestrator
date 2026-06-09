"""Unit tests for the orchestrator-driven multi-agent PR workflows.

Pure queue/policy logic only — no network (build_queue takes PR dicts).
"""
from __future__ import annotations

import pytest

from renquant_orchestrator.agent_workflows import (
    agent_identity_health,
    audit_merged_prs,
    build_queue,
    checks_green,
    is_approved,
    merge_audit_comment,
    merge_audit_status,
    other_agent,
    pr_authorship,
    resolve_token,
    resolve_token_with_source,
    run_agent_workflow,
)


def _pr(num, *, author=None, head=None, state="OPEN", draft=False,
        labels=None, reviews=None, checks=None, comments=None, body=""):
    lbls = [{"name": n} for n in (labels or [])]
    if author and f"agent:{author}" not in (labels or []):
        lbls.append({"name": f"agent:{author}"})
    return {
        "number": num, "title": f"PR {num}",
        "headRefName": head or f"{author or 'x'}/branch-{num}",
        "headRefOid": f"sha{num}", "state": state, "isDraft": draft,
        "url": f"https://github.com/o/r/pull/{num}",
        "labels": lbls,
        "body": body,
        "reviews": [dict(r, commit_id=r.get("commit_id", f"sha{num}")) for r in (reviews or [])],
        "statusCheckRollup": checks or [],
        "comments": comments or [],
    }


def test_other_agent():
    assert other_agent("claude") == "codex"
    assert other_agent("codex") == "claude"
    with pytest.raises(ValueError):
        other_agent("devin")


def test_pr_authorship_label_then_branch():
    assert pr_authorship(_pr(1, author="claude")) == "claude"
    # branch-prefix fallback when no label
    assert pr_authorship({"labels": [], "headRefName": "codex/foo"}) == "codex"
    assert pr_authorship({"labels": [], "headRefName": "feat/foo"}) is None


def test_pr_authorship_uses_visible_body_author_before_branch():
    assert pr_authorship({
        "labels": [],
        "body": "## Traceability\n- author: Codex\n",
        "headRefName": "feature/no-agent-prefix",
    }) == "codex"


def test_resolve_token_env_precedence(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("RENQUANT_CLAUDE_GH_TOKEN", raising=False)
    assert resolve_token("claude", "explicit") == "explicit"
    monkeypatch.setenv("RENQUANT_CLAUDE_GH_TOKEN", "claude-tok")
    monkeypatch.setenv("GH_TOKEN", "generic-tok")
    assert resolve_token("claude") == "claude-tok"      # agent-specific wins
    assert resolve_token("codex") == "generic-tok"      # falls back to GH_TOKEN


def test_resolve_token_with_source_is_diagnostic_safe(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("RENQUANT_CODEX_GH_TOKEN", raising=False)
    monkeypatch.setenv("RENQUANT_CODEX_GH_TOKEN", "secret")

    assert resolve_token_with_source("codex") == (
        "secret",
        "RENQUANT_CODEX_GH_TOKEN",
    )
    assert resolve_token_with_source("codex", "explicit") == (
        "explicit",
        "--token",
    )


def test_agent_identity_health_requires_distinct_logins(monkeypatch):
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.github_login",
        lambda token: {"claude-token": "shared", "codex-token": "shared"}[token],
    )

    health = agent_identity_health(
        claude_token="claude-token",
        codex_token="codex-token",
    )

    assert health["ok"] is False
    assert "same GitHub login" in " ".join(health["warnings"])


def test_agent_identity_health_accepts_distinct_logins(monkeypatch):
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.github_login",
        lambda token: {"claude-token": "claude-user", "codex-token": "codex-user"}[token],
    )

    health = agent_identity_health(
        claude_token="claude-token",
        codex_token="codex-token",
    )

    assert health == {
        "ok": True,
        "agents": {
            "claude": {
                "token_source": "--token",
                "token_present": True,
                "login": "claude-user",
            },
            "codex": {
                "token_source": "--token",
                "token_present": True,
                "login": "codex-user",
            },
        },
        "require_actor_tokens": False,
        "warnings": [],
    }


def test_agent_identity_health_strict_requires_actor_specific_tokens(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "shared-token")
    monkeypatch.delenv("RENQUANT_CLAUDE_GH_TOKEN", raising=False)
    monkeypatch.delenv("RENQUANT_CODEX_GH_TOKEN", raising=False)
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.github_login",
        lambda _token: "shared-operator",
    )

    health = agent_identity_health(require_actor_tokens=True)

    assert health["ok"] is False
    assert health["require_actor_tokens"] is True
    assert health["agents"]["claude"]["token_present"] is False
    assert health["agents"]["codex"]["token_present"] is False
    assert "claude token is missing" in health["warnings"]
    assert "codex token is missing" in health["warnings"]


def test_agent_identity_health_strict_accepts_actor_specific_tokens(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "shared-token")
    monkeypatch.setenv("RENQUANT_CLAUDE_GH_TOKEN", "claude-token")
    monkeypatch.setenv("RENQUANT_CODEX_GH_TOKEN", "codex-token")
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.github_login",
        lambda token: {"claude-token": "claude-user", "codex-token": "codex-user"}[token],
    )

    health = agent_identity_health(require_actor_tokens=True)

    assert health["ok"] is True
    assert health["agents"]["claude"]["token_source"] == "RENQUANT_CLAUDE_GH_TOKEN"
    assert health["agents"]["codex"]["token_source"] == "RENQUANT_CODEX_GH_TOKEN"
    assert health["agents"]["claude"]["login"] == "claude-user"
    assert health["agents"]["codex"]["login"] == "codex-user"


# ── review queue: the OTHER agent's PRs, not yet approved ───────────────

def test_review_queue_picks_peer_prs_only():
    prs = [
        _pr(1, author="codex"),                       # claude should review
        _pr(2, author="claude"),                      # claude's own — skip
        _pr(3, author="codex", reviews=[{"state": "APPROVED"}]),  # already approved — skip
    ]
    q = build_queue("claude", "review", prs)
    assert [w.number for w in q] == [1]


def test_review_queue_accepts_body_authorship_for_traceability():
    prs = [
        _pr(
            1,
            head="feature/no-agent-prefix",
            labels=[],
            body="## Traceability\n- author agent: Codex\n",
        ),
    ]

    q = build_queue("claude", "review", prs)

    assert [w.number for w in q] == [1]
    assert q[0].author_agent == "codex"


def test_review_queue_skips_stop_labelled_and_drafts():
    prs = [
        _pr(1, author="codex", labels=["agent:manual-hold"]),
        _pr(2, author="codex", draft=True),
        _pr(3, author="codex"),
    ]
    assert [w.number for w in build_queue("claude", "review", prs)] == [3]


def test_an_agent_never_reviews_its_own_pr():
    prs = [_pr(1, author="claude")]
    assert build_queue("claude", "review", prs) == []


# ── fix queue: your own PRs with unaddressed findings ───────────────────

def test_fix_queue_changes_requested():
    prs = [
        _pr(1, author="claude", reviews=[{"state": "CHANGES_REQUESTED"}]),
        _pr(2, author="claude", reviews=[{"state": "APPROVED"}]),   # clean — skip
        _pr(3, author="codex", reviews=[{"state": "CHANGES_REQUESTED"}]),  # not mine — skip
    ]
    assert [w.number for w in build_queue("claude", "fix", prs)] == [1]


def test_fix_queue_severity_comment_on_commented_review():
    prs = [
        _pr(1, author="claude",
            reviews=[{"state": "COMMENTED", "body": "**BLOCKER** — bug here"}]),
        _pr(2, author="claude",
            reviews=[{"state": "COMMENTED", "body": "looks fine, minor nit"}]),
    ]
    assert [w.number for w in build_queue("claude", "fix", prs)] == [1]


# ── merge queue: your own, approved + green + unblocked ─────────────────

def test_merge_queue_requires_approved_and_green():
    ok = _pr(1, author="claude",
             reviews=[{"state": "APPROVED"}],
             checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}])
    not_approved = _pr(2, author="claude",
                       checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}])
    failing = _pr(3, author="claude",
                  reviews=[{"state": "APPROVED"}],
                  checks=[{"conclusion": "FAILURE", "status": "COMPLETED"}])
    pending = _pr(4, author="claude",
                  reviews=[{"state": "APPROVED"}],
                  checks=[{"conclusion": "", "status": "IN_PROGRESS"}])
    held = _pr(5, author="claude", labels=["agent:manual-hold"],
               reviews=[{"state": "APPROVED"}],
               checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}])
    q = build_queue("claude", "merge", [ok, not_approved, failing, pending, held])
    assert [w.number for w in q] == [1]


def test_merge_queue_changes_requested_blocks_even_with_approval():
    pr = _pr(1, author="claude",
             reviews=[{"state": "APPROVED"}, {"state": "CHANGES_REQUESTED"}],
             checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}])
    assert build_queue("claude", "merge", [pr]) == []


def test_checks_green_no_checks_is_not_green():
    assert checks_green({"statusCheckRollup": []}) is False


def test_checks_green_allows_no_checks_only_with_explicit_opt_in():
    assert checks_green({"statusCheckRollup": []}, allow_no_checks=True) is True


def test_merge_queue_requires_at_least_one_check():
    pr = _pr(1, author="claude", reviews=[{"state": "APPROVED"}])
    assert build_queue("claude", "merge", [pr]) == []


def test_merge_queue_can_allow_no_checks_by_explicit_opt_in():
    pr = _pr(1, author="claude", reviews=[{"state": "APPROVED"}])
    assert [w.number for w in build_queue(
        "claude",
        "merge",
        [pr],
        allow_no_checks=True,
    )] == [1]


def test_is_approved_only_counts_head_reviews():
    pr = _pr(1, author="claude",
             reviews=[{"state": "APPROVED", "commit_id": "OLD"}])
    pr["headRefOid"] = "NEW"
    # the only APPROVED review is against an old commit → not approved at head
    assert is_approved(pr) is False


def test_review_and_fix_instructions_require_visible_agent_text(monkeypatch):
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [_pr(1, author="codex")],
    )

    review = run_agent_workflow(
        agent="claude", workflow="review", repo="o/r", token=None,
    )
    assert "reviewed by claude" in review["instructions"]

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [
            _pr(
                2,
                author="claude",
                reviews=[{"state": "COMMENTED", "body": "**HIGH** bug"}],
            )
        ],
    )
    fix = run_agent_workflow(agent="claude", workflow="fix", repo="o/r", token=None)
    assert "fixed by claude" in fix["instructions"]


def test_merge_execute_comments_before_merge(monkeypatch):
    calls = []
    pr = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [pr],
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.comment_pr",
        lambda repo, number, body, token: (
            calls.append(("comment", repo, number, body)) or (0, "ok")
        ),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.merge_pr",
        lambda repo, number, token, strategy="merge": (
            calls.append(("merge", repo, number, strategy)) or (0, "merged")
        ),
    )

    plan = run_agent_workflow(
        agent="claude", workflow="merge", repo="o/r", token=None, execute=True,
    )

    assert plan["executed"] == [
        {"number": 1, "merged": True, "commented": True, "output": "merged"}
    ]
    assert calls[0][0] == "comment"
    assert "merged by `claude`" in calls[0][3]
    assert calls[1] == ("merge", "o/r", 1, "merge")


def test_merge_execute_blocks_when_actor_identity_preflight_fails(monkeypatch):
    calls = []
    pr = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [pr],
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.agent_identity_health",
        lambda require_actor_tokens=False: {
            "ok": False,
            "warnings": ["claude and codex tokens resolve to the same GitHub login"],
            "require_actor_tokens": require_actor_tokens,
            "agents": {},
        },
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.comment_pr",
        lambda *args, **kwargs: calls.append(("comment", args, kwargs)) or (0, "ok"),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.merge_pr",
        lambda *args, **kwargs: calls.append(("merge", args, kwargs)) or (0, "merged"),
    )

    plan = run_agent_workflow(
        agent="claude",
        workflow="merge",
        repo="o/r",
        token=None,
        execute=True,
        require_distinct_actor_tokens=True,
    )

    assert plan["merge_blocked"] is True
    assert plan["executed"] == []
    assert "same GitHub login" in plan["block_reason"]
    assert calls == []


def test_merge_execute_actor_identity_preflight_allows_merge(monkeypatch):
    calls = []
    pr = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [pr],
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.agent_identity_health",
        lambda require_actor_tokens=False: {
            "ok": True,
            "warnings": [],
            "require_actor_tokens": require_actor_tokens,
            "agents": {},
        },
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.comment_pr",
        lambda repo, number, body, token: (
            calls.append(("comment", repo, number, body)) or (0, "ok")
        ),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.merge_pr",
        lambda repo, number, token, strategy="merge": (
            calls.append(("merge", repo, number, strategy)) or (0, "merged")
        ),
    )

    plan = run_agent_workflow(
        agent="claude",
        workflow="merge",
        repo="o/r",
        token=None,
        execute=True,
        require_distinct_actor_tokens=True,
    )

    assert plan["identity_preflight"]["ok"] is True
    assert plan["executed"] == [
        {"number": 1, "merged": True, "commented": True, "output": "merged"}
    ]
    assert [call[0] for call in calls] == ["comment", "merge"]


def test_run_agent_workflow_surfaces_allow_no_checks(monkeypatch):
    pr = _pr(1, author="claude", reviews=[{"state": "APPROVED"}])
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [pr],
    )

    default = run_agent_workflow(
        agent="claude", workflow="merge", repo="o/r", token=None,
    )
    allowed = run_agent_workflow(
        agent="claude",
        workflow="merge",
        repo="o/r",
        token=None,
        allow_no_checks=True,
    )

    assert default["allow_no_checks"] is False
    assert default["queue"] == []
    assert allowed["allow_no_checks"] is True
    assert [item["number"] for item in allowed["queue"]] == [1]


def test_merge_execute_does_not_merge_when_audit_comment_fails(monkeypatch):
    calls = []
    pr = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [pr],
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.comment_pr",
        lambda repo, number, body, token: (1, "comment failed"),
    )
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.merge_pr",
        lambda *args, **kwargs: calls.append(("merge", args, kwargs)) or (0, "merged"),
    )

    plan = run_agent_workflow(
        agent="claude", workflow="merge", repo="o/r", token=None, execute=True,
    )

    assert plan["executed"] == [
        {"number": 1, "merged": False, "commented": False, "output": "comment failed"}
    ]
    assert calls == []


def test_merge_audit_comment_names_agent_author_and_head():
    item = build_queue(
        "claude",
        "merge",
        [
            _pr(
                7,
                author="claude",
                head="claude/audit",
                reviews=[{"state": "APPROVED"}],
                checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
            )
        ],
    )[0]

    body = merge_audit_comment("claude", item)

    assert "merged by `claude`" in body
    assert "Pre-merge audit marker" in body
    assert "PR author agent: `claude`" in body
    assert "Head branch: `claude/audit`" in body


def test_merge_audit_status_accepts_pre_merge_marker():
    pr = _pr(1, author="codex", state="MERGED")
    pr["mergedAt"] = "2026-06-09T00:10:00Z"
    pr["mergedBy"] = {"login": "codex-user"}
    pr["comments"] = [{
        "body": "merged by `codex` via `renquant-orchestrator agent-workflow merge --execute`",
        "createdAt": "2026-06-09T00:09:59Z",
        "author": {"login": "codex-user"},
    }]

    status = merge_audit_status(pr)

    assert status["status"] == "ok"
    assert status["has_pre_merge_audit"] is True
    assert status["pre_merge_audit_comment_author"] == "codex-user"
    assert status["post_merge_audit_count"] == 0


def test_merge_audit_status_rejects_post_merge_marker_as_pre_merge():
    pr = _pr(2, author="claude", state="MERGED")
    pr["mergedAt"] = "2026-06-09T00:10:00Z"
    pr["mergedBy"] = {"login": "owner"}
    pr["comments"] = [{
        "body": "merged by `claude` post-merge audit marker",
        "createdAt": "2026-06-09T00:10:01Z",
        "author": {"login": "owner"},
    }]

    status = merge_audit_status(pr)

    assert status["status"] == "missing_pre_merge_audit"
    assert status["has_pre_merge_audit"] is False
    assert status["pre_merge_audit_comment_at"] is None
    assert status["post_merge_audit_count"] == 1


def test_audit_merged_prs_summarizes_missing_pre_merge_markers(monkeypatch):
    ok_pr = _pr(1, author="codex", state="MERGED")
    ok_pr["mergedAt"] = "2026-06-09T00:10:00Z"
    ok_pr["comments"] = [{
        "body": "merged by `codex`",
        "createdAt": "2026-06-09T00:09:59Z",
        "author": {"login": "codex-user"},
    }]
    missing_pr = _pr(2, author="claude", state="MERGED")
    missing_pr["mergedAt"] = "2026-06-09T00:11:00Z"
    missing_pr["comments"] = []
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_merged_prs",
        lambda _repo, _token, limit=50: [ok_pr, missing_pr],
    )

    audit = audit_merged_prs("o/r", token=None, limit=25)

    assert audit["repo"] == "o/r"
    assert audit["limit"] == 25
    assert audit["n_merged_prs"] == 2
    assert audit["n_missing_pre_merge_audit"] == 1
    assert audit["ok"] is False
