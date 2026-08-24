"""Unit tests for the orchestrator-driven multi-agent PR workflows.

Pure queue/policy logic only — no network (build_queue takes PR dicts).
"""
from __future__ import annotations

import pytest

from renquant_orchestrator.agent_workflows import (
    agent_identity_health,
    audit_merged_prs,
    branch_identity_findings,
    build_queue,
    checks_green,
    commit_contributor_logins,
    contract_findings,
    explicit_contributor_logins,
    fetch_open_prs,
    has_head_approval_from_agent,
    has_head_changes_requested_from_agent,
    has_unaddressed_findings,
    is_approved,
    merge_audit_comment,
    merge_audit_status,
    other_agent,
    pr_authorship,
    progress_doc_findings,
    reviewer_is_pr_contributor,
    resolve_token,
    resolve_token_with_source,
    run_agent_workflow,
)


def _pr(num, *, author=None, head=None, state="OPEN", draft=False,
        labels=None, reviews=None, checks=None, comments=None, body="", files=None,
        progress_doc_content=None, commits=None, github_author=None):
    lbls = [{"name": n} for n in (labels or [])]
    if author and f"agent:{author}" not in (labels or []):
        lbls.append({"name": f"agent:{author}"})
    norm_reviews = []
    for r in (reviews or []):
        row = dict(r, commit_id=r.get("commit_id", f"sha{num}"))
        if (
            row.get("state") == "APPROVED"
            and "body" not in row
            and author in {"claude", "codex"}
        ):
            reviewer = "codex" if author == "claude" else "claude"
            row["body"] = f"reviewed by {reviewer}"
        norm_reviews.append(row)
    if files is None:
        files = [{"path": f"doc/progress/2026-06-17-pr-{num}.md"}]
    if progress_doc_content is None:
        progress_doc_content = (
            "# Progress\n"
            "STATUS: delivered\n"
            "WHAT: test fixture\n"
            "WHY/DIR: test fixture\n"
            "EVIDENCE: n/a\n"
            "NEXT: none\n"
        )
    return {
        "number": num, "title": f"PR {num}",
        "headRefName": head or f"{author or 'x'}/branch-{num}",
        "headRefOid": f"sha{num}", "state": state, "isDraft": draft,
        "url": f"https://github.com/o/r/pull/{num}",
        "labels": lbls,
        "body": body,
        "reviews": norm_reviews,
        "statusCheckRollup": checks or [],
        "author": {"login": github_author or f"{author or 'unknown'}-owner"},
        "comments": comments or [],
        "commits": commits or [],
        "files": files,
        "progressDocContent": progress_doc_content,
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


def test_pr_authorship_detects_claude_generated_body_signature():
    assert pr_authorship({
        "labels": [],
        "body": "Frozen for operator review.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)",
        "headRefName": "feature/no-agent-prefix",
    }) == "claude"


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


def test_review_queue_excludes_a_reviewer_who_contributed_to_peer_pr():
    prs = [
        _pr(
            1,
            author="codex",
            comments=[{"body": "fixed by claude-reviewer (agent: claude)"}],
        ),
    ]

    assert build_queue(
        "claude", "review", prs, reviewer_login="claude-reviewer",
    ) == []


def test_mixed_commit_attribution_is_a_merge_blocker():
    pr = _pr(
        1,
        author="claude",
        github_author="claude-owner",
        commits=[
            {"authors": [{"login": "claude-owner"}, {"login": "codex-owner"}]},
            {"authors": [{"login": None}]},
        ],
    )

    assert commit_contributor_logins(pr) == frozenset({"claude-owner", "codex-owner"})
    findings = branch_identity_findings(pr)
    assert len(findings) == 1
    assert "mixed GitHub commit attribution" in findings[0]
    assert "codex-owner" in findings[0]


def test_merge_queue_excludes_mixed_identity_branch():
    pr = _pr(
        1,
        author="claude",
        github_author="claude-owner",
        commits=[{"authors": [{"login": "claude-owner"}, {"login": "codex-owner"}]}],
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    assert build_queue("claude", "merge", [pr]) == []


def test_explicit_fix_marker_blocks_contributor_approval():
    pr = _pr(
        1,
        author="claude",
        comments=[{"body": "fixed by codex-reviewer (agent: codex)"}],
        reviews=[{
            "state": "APPROVED",
            "body": "reviewed by codex",
            "author": {"login": "codex-reviewer"},
        }],
    )

    assert explicit_contributor_logins(pr) == frozenset({"codex-reviewer"})
    assert reviewer_is_pr_contributor(pr, "CODEX-REVIEWER") is True
    assert has_head_approval_from_agent(pr, "codex") is False
    assert is_approved(pr) is False


def test_contributor_approval_does_not_count_as_independent():
    pr = _pr(
        1,
        author="claude",
        comments=[{"body": "fixed by codex-reviewer (agent: codex)"}],
        reviews=[{
            "state": "APPROVED",
            "body": "reviewed by codex",
            "author": {"login": "codex-reviewer"},
        }],
    )

    assert has_head_approval_from_agent(pr, "codex") is False
    assert is_approved(pr) is False


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


def test_fix_queue_includes_missing_progress_doc_contract_violation():
    prs = [
        _pr(1, author="claude", files=[]),
    ]

    q = build_queue("claude", "fix", prs)

    assert [w.number for w in q] == [1]
    assert "missing progress doc" in q[0].note


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


def test_merge_queue_requires_peer_review_marker():
    pr = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED", "body": "looks good"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )

    assert build_queue("claude", "merge", [pr]) == []


def test_merge_queue_blocks_missing_fix_marker_after_findings():
    pr = _pr(
        1,
        author="claude",
        reviews=[
            {"state": "CHANGES_REQUESTED", "commit_id": "OLD", "body": "**HIGH** bug"},
            {"state": "APPROVED"},
        ],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
    )
    pr["headRefOid"] = "sha1"

    assert build_queue("claude", "merge", [pr]) == []


def test_merge_queue_blocks_progress_doc_or_production_path_contract_violations():
    missing_progress = _pr(
        1,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
        files=[],
    )
    prod_path = _pr(
        2,
        author="claude",
        reviews=[{"state": "APPROVED"}],
        checks=[{"conclusion": "SUCCESS", "status": "COMPLETED"}],
        files=[
            {"path": "doc/progress/2026-06-17-pr-2.md"},
            {"path": "backtesting/renquant_104/live_state.alpaca.json"},
        ],
    )

    assert build_queue("claude", "merge", [missing_progress, prod_path]) == []


def test_is_approved_only_counts_head_reviews():
    pr = _pr(1, author="claude",
             reviews=[{"state": "APPROVED", "commit_id": "OLD"}])
    pr["headRefOid"] = "NEW"
    # the only APPROVED review is against an old commit → not approved at head
    assert is_approved(pr) is False


# ── gh-CLI review shape + reviewer supersession (2026-07-15 incident) ──
# `gh pr list --json reviews` nests the review commit as `commit.oid` and has
# no `commit_id` key, so the predicates saw zero reviews at head: the review
# queue re-listed already-reviewed PRs forever (6 duplicate reviews per PR in
# one day) and the merge queue could never see an approval.


def test_is_approved_reads_gh_cli_review_commit_shape():
    pr = _pr(7, author="codex", reviews=[
        {"state": "APPROVED", "commit_id": None, "commit": {"oid": "sha7"},
         "author": {"login": "reviewer"},
         "submittedAt": "2026-07-15T01:00:00Z"},
    ])
    assert is_approved(pr) is True


def test_gh_cli_review_shape_still_ignores_non_head_reviews():
    pr = _pr(7, author="codex", reviews=[
        {"state": "APPROVED", "commit_id": None, "commit": {"oid": "OLD"},
         "author": {"login": "reviewer"},
         "submittedAt": "2026-07-15T01:00:00Z"},
    ])
    assert is_approved(pr) is False


def test_later_approval_supersedes_same_reviewers_changes_requested():
    pr = _pr(8, author="codex", reviews=[
        {"state": "CHANGES_REQUESTED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "reviewed by claude — MED: add the progress doc"},
        {"state": "APPROVED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T02:00:00Z",
         "body": "reviewed by claude — reconsidered, approve"},
    ])
    assert is_approved(pr) is True
    assert has_head_approval_from_agent(pr, "claude") is True
    # the superseded findings no longer put the PR in the author's fix queue
    assert has_unaddressed_findings(pr, "codex") is False
    assert build_queue("claude", "review", [pr]) == []


def test_dismissed_and_commented_reviews_never_veto_or_approve():
    pr = _pr(9, author="codex", reviews=[
        {"state": "APPROVED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T01:00:00Z", "body": "reviewed by claude"},
        {"state": "DISMISSED", "author": {"login": "rev2"},
         "submittedAt": "2026-07-15T02:00:00Z"},
        {"state": "COMMENTED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T03:00:00Z"},
    ])
    assert is_approved(pr) is True

    only_dismissed = _pr(9, author="codex", reviews=[
        {"state": "DISMISSED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T01:00:00Z"},
    ])
    assert is_approved(only_dismissed) is False


# ── a reviewer's own DISMISSED review must retract their prior vote ────
# (Codex review of PR #519: a later same-reviewer DISMISSED never cleared
# that reviewer's earlier effective state, so a dismissed CHANGES_REQUESTED
# blocked forever and a dismissed APPROVED kept counting as approved.)


def test_self_dismissed_changes_requested_clears_and_other_approval_stands():
    pr = _pr(15, author="codex", reviews=[
        {"state": "CHANGES_REQUESTED", "author": {"login": "rev1"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "reviewed by claude — MED: bug"},
        {"state": "DISMISSED", "author": {"login": "rev1"},
         "submittedAt": "2026-07-15T02:00:00Z"},
        {"state": "APPROVED", "author": {"login": "rev2"},
         "submittedAt": "2026-07-15T03:00:00Z",
         "body": "reviewed by claude"},
    ])
    # rev1's CHANGES_REQUESTED was retracted by their own DISMISSED; only
    # rev2's still-valid APPROVED should count.
    assert is_approved(pr) is True


def test_self_dismissed_approval_no_longer_counts_as_approved():
    pr = _pr(16, author="codex", reviews=[
        {"state": "APPROVED", "author": {"login": "rev1"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "reviewed by claude"},
        {"state": "DISMISSED", "author": {"login": "rev1"},
         "submittedAt": "2026-07-15T02:00:00Z"},
    ])
    # rev1 dismissed their own approval — it must not count as approved.
    assert is_approved(pr) is False


# ── severity-tagged COMMENTED reviews must still surface as findings ───
# (Codex review of PR #519: has_unaddressed_findings reused the
# vote-counting reduction, which correctly drops COMMENTED for vote
# purposes but wrongly dropped it for findings-scanning too, so a
# COMMENTED review carrying a MED/HIGH/BLOCKER tag silently disappeared
# from the author's fix queue.)


def test_commented_severity_tag_still_counts_as_unaddressed_finding():
    pr = _pr(17, author="claude", reviews=[
        {"state": "COMMENTED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "MED: still broken"},
    ], comments=[{"body": "fixed by claude"}])
    assert has_unaddressed_findings(pr, "claude") is True
    assert [w.number for w in build_queue("claude", "fix", [pr])] == [17]


# ── the author's own explanatory comments must not self-perpetuate a
# finding forever (renquant-model#92/94/95, 2026-07-29) ────────────────
# The reviewer's CHANGES_REQUESTED landed on a stale commit that is no
# longer the head (superseded by a later APPROVED review at head), so the
# only remaining severity-tagged text lives in the PR author's own
# `fixed by <agent>` / follow-up comments quoting the resolved finding.
# Plain issue comments carry no head SHA, so scanning the author's own
# comments made this match forever, even after the finding was fixed.


def test_authors_own_comment_quoting_a_resolved_finding_is_not_unaddressed():
    pr = _pr(
        18,
        author="claude",
        github_author="pr-owner",
        reviews=[
            {"state": "CHANGES_REQUESTED", "author": {"login": "rev"},
             "commit_id": "sha18-stale",
             "submittedAt": "2026-07-15T01:00:00Z",
             "body": "BLOCKER: bad citation"},
            {"state": "APPROVED", "author": {"login": "rev"},
             "submittedAt": "2026-07-15T02:00:00Z",
             "body": "reviewed by codex"},
        ],
        comments=[
            {"author": {"login": "pr-owner"},
             "body": "fixed by claude — BLOCKER: bad citation — corrected the cite."},
            {"author": {"login": "pr-owner"},
             "body": "clarifying: the queue's BLOCKER note is stale, already fixed above."},
        ],
    )
    assert has_unaddressed_findings(pr, "claude") is False
    assert build_queue("claude", "fix", [pr]) == []
    # a genuine finding from someone else still counts
    pr["comments"].append({"author": {"login": "rev"}, "body": "MED: new issue found"})
    assert has_unaddressed_findings(pr, "claude") is True


def test_review_queue_skips_head_this_agent_already_requested_changes_on():
    pr = _pr(10, author="codex", reviews=[
        {"state": "CHANGES_REQUESTED", "author": {"login": "rev"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "reviewed by claude — MED: missing progress doc"},
    ])
    assert has_head_changes_requested_from_agent(pr, "claude") is True
    # reviewer side: nothing to add until the author pushes a new head
    assert build_queue("claude", "review", [pr]) == []
    # author side: the findings put it in the fix queue
    assert [w.number for w in build_queue("codex", "fix", [pr])] == [10]
    # a new head re-opens review
    pr["headRefOid"] = "sha10-v2"
    assert [w.number for w in build_queue("claude", "review", [pr])] == [10]


def test_changes_requested_without_agent_marker_still_queues_review():
    pr = _pr(11, author="codex", reviews=[
        {"state": "CHANGES_REQUESTED", "author": {"login": "operator"},
         "submittedAt": "2026-07-15T01:00:00Z",
         "body": "manual operator note, no agent marker"},
    ])
    assert [w.number for w in build_queue("claude", "review", [pr])] == [11]


def test_has_head_approval_from_agent_requires_marker():
    pr = _pr(1, author="codex", reviews=[{"state": "APPROVED", "body": "reviewed by claude"}])

    assert has_head_approval_from_agent(pr, "claude") is True
    assert has_head_approval_from_agent(pr, "codex") is False


def test_contract_findings_require_progress_doc_structure_and_block_production_paths():
    pr = _pr(
        1,
        author="claude",
        files=[
            {"path": "doc/progress/2026-06-17-pr-1.md"},
            {"path": "data/foo/bar.parquet"},
            {"path": "backtesting/renquant_104/strategy_config.json"},
        ],
        progress_doc_content="# Progress\nSTATUS: delivered\nWHAT: test only\nEVIDENCE: artifact pending\nNEXT: none\n",
    )

    findings = contract_findings(pr)

    assert any("WHY/DIR:" in finding for finding in findings)
    assert any("evidence block missing fields" in finding for finding in findings)
    assert any("data/foo/bar.parquet" in finding for finding in findings)
    assert any("strategy_config.json" in finding for finding in findings)


def test_review_and_fix_instructions_require_visible_agent_text(monkeypatch):
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [_pr(1, author="codex")],
    )

    review = run_agent_workflow(
        agent="claude", workflow="review", repo="o/r", token=None,
    )
    assert "reviewed by claude" in review["instructions"]
    assert "doc/progress/<date>-<slug>.md" in review["instructions"]
    assert "evidence block" in review["instructions"]

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
    assert "doc/progress/<date>-<slug>.md" in fix["instructions"]


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


# ── orch#988: the approve-and-merge path is audited by its own review record ──
#
# 84% of codex's merges in the measured 7d window carried no pre-merge marker —
# structurally, not carelessly: its path approves and merges in one action, and
# the marker convention is satisfiable only on the two-token agent-workflow
# path. The merger's own pre-merge APPROVED review on a peer's PR carries the
# same facts the marker encodes, so it now counts as the attestation. The gate
# keeps firing on merges with NEITHER record.


#: A real `gh pr view --json reviews` payload ALWAYS carries the reviewed
#: commit; the fixture omitted it, which is how the gap in orch#991 could exist
#: without a red test. Default: the review is of the merged head.
_MERGED_HEAD = "a" * 40


def _merged_pr_with_review(num, *, author_login, merged_by, review_state="APPROVED",
                           reviewer=None, review_at="2026-06-09T00:09:00Z",
                           merged_at="2026-06-09T00:10:00Z",
                           head_oid=_MERGED_HEAD, review_oid=None):
    pr = _pr(num, author="claude", state="MERGED")
    pr["author"] = {"login": author_login}
    pr["mergedAt"] = merged_at
    pr["mergedBy"] = {"login": merged_by}
    pr["headRefOid"] = head_oid
    pr["comments"] = []
    pr["reviews"] = [{
        "state": review_state,
        "author": {"login": reviewer or merged_by},
        "submittedAt": review_at,
        "commit": {"oid": head_oid if review_oid is None else review_oid},
    }]
    return pr


def test_merge_audit_status_accepts_the_mergers_pre_merge_approval():
    """codex's real shape (model#226): APPROVED 21:26, merged 21:26:34, no comment."""
    pr = _merged_pr_with_review(3, author_login="claude-user", merged_by="codex-user")

    status = merge_audit_status(pr)

    assert status["status"] == "review_attested"
    assert status["audited"] is True
    assert status["review_attested"] is True
    assert status["review_attested_at"] == "2026-06-09T00:09:00Z"
    # the two records never blur: this is NOT a pre-merge marker
    assert status["has_pre_merge_audit"] is False


def test_merge_audit_status_self_merge_cannot_self_attest():
    """author == merger: whatever was approved, a self-merge stays unaudited."""
    pr = _merged_pr_with_review(4, author_login="codex-user", merged_by="codex-user")

    status = merge_audit_status(pr)

    assert status["status"] == "missing_pre_merge_audit"
    assert status["audited"] is False


def test_merge_audit_status_post_merge_approval_does_not_attest():
    pr = _merged_pr_with_review(
        5, author_login="claude-user", merged_by="codex-user",
        review_at="2026-06-09T00:10:01Z",  # AFTER mergedAt
    )

    status = merge_audit_status(pr)

    assert status["status"] == "missing_pre_merge_audit"
    assert status["audited"] is False


def test_merge_audit_status_non_approving_or_third_party_review_does_not_attest():
    changes = _merged_pr_with_review(
        6, author_login="claude-user", merged_by="codex-user",
        review_state="CHANGES_REQUESTED",
    )
    third_party = _merged_pr_with_review(
        7, author_login="claude-user", merged_by="codex-user",
        reviewer="someone-else",
    )

    assert merge_audit_status(changes)["audited"] is False
    assert merge_audit_status(third_party)["audited"] is False


def test_merge_audit_status_superseded_approval_does_not_attest():
    """Approve then request-changes BEFORE the merge: the approval was
    explicitly superseded, so the merge must not report review_attested."""
    pr = _merged_pr_with_review(9, author_login="claude-user", merged_by="codex-user")
    pr["reviews"].append({
        "state": "CHANGES_REQUESTED",
        "author": {"login": "codex-user"},
        "submittedAt": "2026-06-09T00:09:30Z",  # after the approval, before mergedAt
    })

    status = merge_audit_status(pr)

    assert status["status"] == "missing_pre_merge_audit"
    assert status["review_attested"] is False
    assert status["audited"] is False


def test_merge_audit_status_reapproval_after_changes_attests():
    """CHANGES_REQUESTED then APPROVED before the merge: the latest pre-merge
    state is APPROVED, so the attestation holds."""
    pr = _merged_pr_with_review(
        10, author_login="claude-user", merged_by="codex-user",
        review_state="CHANGES_REQUESTED", review_at="2026-06-09T00:08:00Z",
    )
    pr["reviews"].append({
        "state": "APPROVED",
        "author": {"login": "codex-user"},
        "submittedAt": "2026-06-09T00:09:00Z",
        "commit": {"oid": _MERGED_HEAD},
    })

    status = merge_audit_status(pr)

    assert status["status"] == "review_attested"
    assert status["review_attested_at"] == "2026-06-09T00:09:00Z"
    assert status["audited"] is True


def test_merge_audit_status_post_merge_changes_do_not_revoke_attestation():
    """A CHANGES_REQUESTED submitted AFTER mergedAt is outside the pre-merge
    window: the pre-merge approval still attests."""
    pr = _merged_pr_with_review(11, author_login="claude-user", merged_by="codex-user")
    pr["reviews"].append({
        "state": "CHANGES_REQUESTED",
        "author": {"login": "codex-user"},
        "submittedAt": "2026-06-09T00:10:30Z",  # after mergedAt
    })

    status = merge_audit_status(pr)

    assert status["status"] == "review_attested"
    assert status["audited"] is True


def test_merge_audit_status_same_second_supersession_is_deterministic():
    """Equal timestamps: list position (submission order) breaks the tie, so
    approve-then-request-changes in the same second still does not attest."""
    pr = _merged_pr_with_review(12, author_login="claude-user", merged_by="codex-user")
    pr["reviews"].append({
        "state": "CHANGES_REQUESTED",
        "author": {"login": "codex-user"},
        "submittedAt": "2026-06-09T00:09:00Z",  # same second as the approval
    })

    status = merge_audit_status(pr)

    assert status["review_attested"] is False
    assert status["audited"] is False


def test_merge_audit_status_pre_merge_marker_still_wins_over_attestation():
    """The marker path is unchanged: when present, status stays 'ok'."""
    pr = _merged_pr_with_review(8, author_login="claude-user", merged_by="codex-user")
    pr["comments"] = [{
        "body": "merged by `codex`",
        "createdAt": "2026-06-09T00:08:00Z",
        "author": {"login": "codex-user"},
    }]

    status = merge_audit_status(pr)

    assert status["status"] == "ok"
    assert status["has_pre_merge_audit"] is True
    assert status["review_attested"] is False  # attestation not even consulted
    assert status["audited"] is True


def test_audit_merged_prs_gate_accepts_attested_and_fires_on_neither(monkeypatch):
    from datetime import datetime, timezone

    attested = _merged_pr_with_review(9, author_login="claude-user",
                                      merged_by="codex-user")
    naked = _pr(10, author="claude", state="MERGED")
    naked["author"] = {"login": "claude-user"}
    naked["mergedAt"] = "2026-06-09T00:11:00Z"
    naked["mergedBy"] = {"login": "codex-user"}
    naked["comments"] = []
    naked["reviews"] = []
    in_window = datetime(2026, 6, 10, tzinfo=timezone.utc)

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_merged_prs",
        lambda _repo, _token, limit=50: [attested, naked],
    )
    audit = audit_merged_prs("o/r", None, limit=25, now=in_window)
    assert audit["n_review_attested_in_window"] == 1
    assert audit["n_missing_in_window"] == 1  # only the record-less merge
    assert audit["ok"] is False

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_merged_prs",
        lambda _repo, _token, limit=50: [attested],
    )
    audit = audit_merged_prs("o/r", None, limit=25, now=in_window)
    assert audit["n_missing_in_window"] == 0
    assert audit["ok"] is True  # attestation alone satisfies the gate


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
    # the MEASUREMENT is unchanged by the 2026-08-05 gate rescope
    assert audit["n_missing_pre_merge_audit"] == 1
    # ...but `ok` is now the WINDOW, so the gate verdict needs a pinned `now` rather
    # than the wall clock. Before this the assertion silently depended on how far
    # 2026-06-09 happened to be from today — it would have started passing on its own.
    from datetime import datetime, timezone
    in_window = datetime(2026, 6, 10, tzinfo=timezone.utc)
    assert audit_merged_prs("o/r", None, limit=25, now=in_window)["ok"] is False


# ── fetch_open_prs: a deleted progress doc must not crash the whole repo ────
#
# Regression for orch#570 (a revert PR deleting doc/progress/<...>.md):
# fetch_open_prs previously let the contents-API 404 propagate as an
# uncaught RuntimeError, which crashed plan-building for the ENTIRE repo —
# hiding every other open PR's queue entry behind one PR's deleted file.

def test_fetch_open_prs_survives_a_deleted_progress_doc(monkeypatch):
    pr_list_payload = [{
        "number": 570,
        "title": "revert(research): remove misplaced artifacts",
        "headRefName": "codex/revert-evidence",
        "headRefOid": "deadbeef",
        "state": "OPEN",
        "isDraft": False,
        "url": "https://example.invalid/pulls/570",
        "labels": [],
        "body": "",
        "reviews": [],
        "statusCheckRollup": [],
        "comments": [],
        "author": {"login": "haorensjtu-dev"},
    }]
    detail_payload = {
        "files": [{"path": "doc/progress/2026-07-23-evidence.md"}],
        "commits": [{"authors": [{"login": "codex"}]}],
    }

    def fake_gh_json(args, token=None):
        if args[:2] == ["pr", "list"]:
            return pr_list_payload
        if args[:2] == ["pr", "view"]:
            return detail_payload
        if args[0] == "api" and "/contents/" in args[1]:
            # The file was deleted at head -- GitHub's contents API 404s,
            # which _gh_json surfaces as a RuntimeError (matches its real
            # behavior on any nonzero `gh` exit code).
            raise RuntimeError(
                f"gh {' '.join(args)} failed (rc=1): gh: Not Found (HTTP 404)"
            )
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows._gh_json", fake_gh_json
    )

    prs = fetch_open_prs("o/r", token=None)

    assert len(prs) == 1
    assert prs[0]["number"] == 570
    assert "progressDocContent" not in prs[0]
    # And the resulting finding is the correct, actionable one -- not a crash.
    assert progress_doc_findings(prs[0]) == [
        "progress doc content unavailable for `doc/progress/2026-07-23-evidence.md`"
    ]


def test_fetch_open_prs_still_fetches_progress_doc_content_when_present(monkeypatch):
    pr_list_payload = [{
        "number": 1,
        "title": "normal PR",
        "headRefName": "feature/x",
        "headRefOid": "cafebabe",
        "state": "OPEN",
        "isDraft": False,
        "url": "https://example.invalid/pulls/1",
        "labels": [],
        "body": "",
        "reviews": [],
        "statusCheckRollup": [],
        "comments": [],
        "author": {"login": "hallovorld"},
    }]
    detail_payload = {
        "files": [{"path": "doc/progress/2026-07-23-x.md"}],
        "commits": [{"authors": [{"login": "claude"}]}],
    }
    import base64

    def fake_gh_json(args, token=None):
        if args[:2] == ["pr", "list"]:
            return pr_list_payload
        if args[:2] == ["pr", "view"]:
            return detail_payload
        if args[0] == "api" and "/contents/" in args[1]:
            return {
                "encoding": "base64",
                "content": base64.b64encode(b"STATUS: x\n").decode(),
            }
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows._gh_json", fake_gh_json
    )

    prs = fetch_open_prs("o/r", token=None)

    assert prs[0]["progressDocContent"] == "STATUS: x\n"


# --- the gate must be satisfiable (operator-reported 2026-08-05) ---------------------

def _merged(num, when, *, marked):
    pr = _pr(num, author="claude", state="MERGED")
    pr["mergedAt"] = when
    pr["mergedBy"] = {"login": "hallovorld"}
    pr["comments"] = ([{"body": "merged by `claude`",
                        "createdAt": when.replace("T", "T").replace("Z", "Z"),
                        "author": {"login": "hallovorld"}}] if marked else [])
    if marked:
        # the marker must PRE-date the merge to count
        pr["comments"][0]["createdAt"] = when[:-1] + "0Z" if when.endswith("Z") else when
        pr["comments"][0]["createdAt"] = "2000-01-01T00:00:00Z"
    return pr


def test_the_gate_ignores_history_it_can_never_change(monkeypatch):
    """The defect the operator was paged about for months.

    `ok` was "no missing marker in ALL history", and the marker must pre-date the merge.
    A merged PR can still receive comments but can NEVER receive a pre-merge one, so one
    violation pinned the gate red permanently — measured 375 of 454 PRs, failing every
    five minutes regardless of anyone's future behaviour. A gate that cannot be satisfied
    is not a gate.

    Old history unmarked + the window clean must be GREEN.
    """
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    prs = [_merged(1, "2026-05-01T00:00:00Z", marked=False),   # ancient, unfixable
           _merged(2, "2026-05-02T00:00:00Z", marked=False),
           _merged(3, "2026-08-04T00:00:00Z", marked=True)]    # in-window, compliant
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, now=now)

    assert audit["ok"] is True, audit
    assert audit["n_missing_pre_merge_audit"] == 2      # history still COUNTED
    assert audit["n_missing_in_window"] == 0            # ...and not gating
    assert audit["n_merged_in_window"] == 1


def test_a_violation_INSIDE_the_window_still_fails(monkeypatch):
    """Anti-vacuity: the window must not be a way to stop failing. A recent unmarked
    merge is a real, current, actionable violation and must go red."""
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    prs = [_merged(1, "2026-05-01T00:00:00Z", marked=False),
           _merged(9, "2026-08-04T00:00:00Z", marked=False)]
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, now=now)

    assert audit["ok"] is False
    assert audit["n_missing_in_window"] == 1
    assert audit["missing_in_window"][0]["number"] == 9


def test_the_gate_CAN_go_green_by_behaviour_alone(monkeypatch):
    """The property the old gate lacked: comply for the window's length and it clears
    itself, with no retroactive edit to history."""
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    prs = [_merged(1, "2026-07-01T00:00:00Z", marked=False)]   # the only violation
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    day_of = _dt.datetime(2026, 7, 2, tzinfo=_dt.timezone.utc)
    later = _dt.datetime(2026, 7, 20, tzinfo=_dt.timezone.utc)

    assert AW.audit_merged_prs("o/r", None, now=day_of)["ok"] is False
    assert AW.audit_merged_prs("o/r", None, now=later)["ok"] is True


def test_a_TRUNCATED_window_fails_closed_instead_of_reporting_clean(monkeypatch):
    """Review round 1 on the rescope: the gate could return a FALSE GREEN.

    `fetch_merged_prs` returns only the `limit` most recent merges. When a repo merges
    more than `limit` times inside the window — measured live: 217 merges in 7 days —
    every fetched PR lies inside the window, the window extends past what was fetched,
    and an older in-window violation is simply invisible. `ok` would have read True
    while the stated window was never clean.

    A false green on a compliance gate is worse than the permanently-red gate this
    replaced: one gets ignored, the other gets believed. So an unseen window is its own
    state and fails closed.
    """
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    # every fetched PR is inside the 7d window and all are marked: nothing looks wrong,
    # and that is exactly the trap — the violation sits just beyond the fetch limit.
    prs = [_merged(n, f"2026-08-0{(n % 4) + 1}T00:00:00Z", marked=True) for n in range(1, 4)]
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, limit=3, now=now)

    assert audit["window_fully_covered"] is False
    assert audit["n_missing_in_window"] == 0      # nothing VISIBLE is missing…
    assert audit["ok"] is False                   # …and it still must not say clean
    assert "raise --limit" in (audit["coverage_note"] or "")


def test_a_window_that_IS_fully_covered_reports_clean(monkeypatch):
    """Anti-vacuity: coverage must not make the gate permanently red again. One fetched
    merge OLDER than the cutoff proves the window was fully seen."""
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    prs = [_merged(1, "2026-08-04T00:00:00Z", marked=True),
           _merged(2, "2026-06-01T00:00:00Z", marked=False)]   # predates the cutoff
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, now=now)

    assert audit["window_fully_covered"] is True
    assert audit["ok"] is True
    assert audit["n_missing_pre_merge_audit"] == 1   # the old one is still counted


def test_an_EXHAUSTED_fetch_is_covered_even_when_every_merge_is_recent(monkeypatch):
    """Review round 2/3: my first coverage rules were fail-closed but UNATTAINABLE.

    `covered = oldest < cutoff` asks the wrong question. Only TRUNCATION can hide an
    in-window merge, and a response shorter than `limit` is proof of exhaustion — there
    is nothing older to fetch, whatever the dates say. Requiring an older merge made
    every low-volume repo permanently red, which is the same defect (an unclearable
    gate) that this whole change exists to remove.
    """
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    # 2 merges returned against a limit of 200: the list was NOT capped, and both are
    # recent — under the old rule this read "uncovered" and gated red forever.
    prs = [_merged(1, "2026-08-04T00:00:00Z", marked=True),
           _merged(2, "2026-08-03T00:00:00Z", marked=True)]
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, limit=200, now=now)

    assert audit["window_fully_covered"] is True
    assert audit["coverage_note"] is None
    assert audit["ok"] is True


def test_a_repo_with_NO_merges_is_fully_observed_not_uncovered(monkeypatch):
    """Zero rows is an exhausted response, so the window was seen and it is clean.
    `bool(rows)` made emptiness indistinguishable from truncation."""
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: [])

    audit = AW.audit_merged_prs("o/r", None, limit=200, now=now)

    assert audit["n_merged_prs"] == 0
    assert audit["window_fully_covered"] is True
    assert audit["ok"] is True


def test_a_merge_exactly_ON_the_cutoff_counts_as_reaching_back_past_it(monkeypatch):
    """The window is inclusive of the cutoff (`merged_at >= cutoff` selects in-window),
    so a merge landing exactly on it HAS been observed. A strict `<` called that
    uncovered — the boundary was classified two different ways in one function."""
    import datetime as _dt
    from renquant_orchestrator import agent_workflows as AW

    now = _dt.datetime(2026, 8, 5, tzinfo=_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=AW.GATE_WINDOW_DAYS)   # 2026-07-29T00:00:00Z
    # capped list (len == limit), so coverage rests entirely on the boundary merge
    prs = [_merged(1, "2026-08-04T00:00:00Z", marked=True),
           _merged(2, cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"), marked=True)]
    monkeypatch.setattr(AW, "fetch_merged_prs", lambda *a, **k: prs)

    audit = AW.audit_merged_prs("o/r", None, limit=2, now=now)

    assert audit["n_merged_in_window"] == 2     # the boundary merge IS in the window…
    assert audit["window_fully_covered"] is True   # …and therefore was observed
    assert audit["ok"] is True


# ===========================================================================
# orch#991 — an attestation must say WHAT was approved, not only who and when
# ===========================================================================

def test_approve_A_force_push_B_merge_B_is_NOT_attested():
    """The sequence the gap admitted, verbatim:

        1. codex APPROVES head A
        2. the author force-pushes head B — no new review
        3. codex merges B

    The merger's latest pre-merge review is APPROVED, so the audit reported
    `review_attested`. Its commit was A. Nobody approved B. Reachable on this
    repo because `require_last_push_approval` is FALSE here.
    """
    pr = _merged_pr_with_review(
        20, author_login="claude-user", merged_by="codex-user",
        head_oid="b" * 40, review_oid="a" * 40,
    )

    status = merge_audit_status(pr)

    assert status["review_attested"] is False
    assert status["audited"] is False
    assert status["status"] == "review_not_bound_to_merged_commit"
    assert status["approved_commit"] == "a" * 40
    assert status["merged_commit"] == "b" * 40
    assert "head moved after the approval" in status["attestation_gap"]


def test_the_near_miss_is_reported_separately_from_no_review_at_all():
    """"approved a DIFFERENT commit" and "nobody reviewed" are different
    findings, and only one of them is a near-miss. Collapsing them to
    `missing_pre_merge_audit` would hide exactly what #991 is about."""
    moved = _merged_pr_with_review(21, author_login="claude-user",
                                   merged_by="codex-user",
                                   head_oid="b" * 40, review_oid="a" * 40)
    none_at_all = _merged_pr_with_review(22, author_login="claude-user",
                                         merged_by="codex-user")
    none_at_all["reviews"] = []

    assert merge_audit_status(moved)["status"] == "review_not_bound_to_merged_commit"
    assert merge_audit_status(none_at_all)["status"] == "missing_pre_merge_audit"


def test_an_approval_OF_the_merged_commit_still_attests():
    """The control. A check that cannot pass on the good case is a ratchet."""
    pr = _merged_pr_with_review(23, author_login="claude-user",
                                merged_by="codex-user")
    status = merge_audit_status(pr)
    assert status["status"] == "review_attested"
    assert status["review_attested"] is True
    assert status["approved_commit"] == status["merged_commit"] == _MERGED_HEAD


def test_a_review_with_NO_recorded_commit_does_not_attest():
    """Absence is not agreement: a review that cannot be shown to be OF the
    merged code does not attest to it."""
    pr = _merged_pr_with_review(24, author_login="claude-user",
                                merged_by="codex-user")
    pr["reviews"][0].pop("commit")
    status = merge_audit_status(pr)
    assert status["review_attested"] is False
    assert status["status"] == "review_not_bound_to_merged_commit"
    assert "carries no commit" in status["attestation_gap"]


def test_a_PR_with_no_recorded_head_does_not_attest():
    pr = _merged_pr_with_review(25, author_login="claude-user",
                                merged_by="codex-user")
    pr["headRefOid"] = ""
    status = merge_audit_status(pr)
    assert status["review_attested"] is False
    assert "records no merged head" in status["attestation_gap"]


def test_a_pre_merge_MARKER_still_audits_regardless_of_the_commit_check():
    """The two records never blur. The comment convention is independent — a
    marker audits even when the approval bound to a different commit, because
    the marker is its own attestation."""
    pr = _merged_pr_with_review(26, author_login="claude-user",
                                merged_by="codex-user",
                                head_oid="b" * 40, review_oid="a" * 40)
    pr["comments"] = [{
        "body": "merged by codex after review",
        "createdAt": "2026-06-09T00:09:30Z",
        "author": {"login": "codex-user"},
    }]
    status = merge_audit_status(pr)
    assert status["status"] == "ok"
    assert status["audited"] is True
