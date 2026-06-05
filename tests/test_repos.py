"""Unit tests for the cross-repo control plane.

Manifest parsing + dispatch policy is pure/mockable; git/gh shell out.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import repos as R


def _manifest(tmp_path: Path) -> Path:
    p = tmp_path / "subrepos.lock.json"
    p.write_text(json.dumps({
        "source_repo": {"name": "RenQuant",
                        "local_path": str(tmp_path / "RenQuant"),
                        "remote": "https://github.com/hallovorld/RenQuant"},
        "subrepos": [
            {"name": "renquant-common",
             "local_path": str(tmp_path / "renquant-common"),
             "remote": "https://github.com/hallovorld/renquant-common.git"},
            {"name": "renquant-pipeline",
             "local_path": str(tmp_path / "renquant-pipeline"),
             "remote": "https://github.com/hallovorld/renquant-pipeline"},
        ],
    }))
    return p


def test_owner_repo_strips_git_suffix():
    assert R._owner_repo_from_remote("https://github.com/o/r.git") == "o/r"
    assert R._owner_repo_from_remote("https://github.com/o/r") == "o/r"


def test_load_manifest_umbrella_first(tmp_path):
    entries = R.load_manifest(_manifest(tmp_path))
    assert [e.name for e in entries] == ["RenQuant", "renquant-common", "renquant-pipeline"]
    assert entries[0].role == "umbrella"
    assert entries[1].owner_repo == "hallovorld/renquant-common"


def test_select_repos_all_and_named(tmp_path):
    entries = R.load_manifest(_manifest(tmp_path))
    assert len(R.select_repos(entries, "all")) == 3
    assert len(R.select_repos(entries, None)) == 3
    assert [e.name for e in R.select_repos(entries, "renquant-common")] == ["renquant-common"]
    assert [e.name for e in R.select_repos(entries, "hallovorld/renquant-pipeline")] == ["renquant-pipeline"]
    with pytest.raises(ValueError):
        R.select_repos(entries, "nope")


def test_list_action(tmp_path):
    out = R.run_repos(action="list", repo="all", manifest=_manifest(tmp_path))
    assert out["n_repos"] == 3
    assert {r["name"] for r in out["repos"]} == {"RenQuant", "renquant-common", "renquant-pipeline"}


def test_exec_requires_command(tmp_path):
    with pytest.raises(ValueError):
        R.run_repos(action="exec", repo="all", manifest=_manifest(tmp_path), exec_cmd=None)


def test_agent_requires_as_and_workflow(tmp_path):
    with pytest.raises(ValueError):
        R.run_repos(action="agent", repo="all", manifest=_manifest(tmp_path))


def test_cross_repo_merge_execute_requires_allow_all(tmp_path):
    """Blast-radius gate: merge --execute --repo all must opt in."""
    with pytest.raises(ValueError, match="allow-all"):
        R.run_repos(action="agent", repo="all", manifest=_manifest(tmp_path),
                    agent="claude", workflow="merge", execute=True)


def test_single_repo_merge_execute_does_not_require_allow_all(tmp_path, monkeypatch):
    """Narrowing to one repo is allowed without --allow-all."""
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [],
    )
    out = R.run_repos(action="agent", repo="renquant-common",
                      manifest=_manifest(tmp_path), agent="claude",
                      workflow="merge", execute=True)
    assert out["n_repos"] == 1
    assert out["repos"][0]["plan"]["queue"] == []


def test_cross_repo_merge_cap_stops_after_max(tmp_path, monkeypatch):
    """--allow-all --max-merges 1 must stop executing after 1 merge."""
    # Every repo has one mergeable PR.
    def _prs(owner_repo, _token):
        return [{
            "number": 1, "title": "t", "headRefName": "claude/x",
            "headRefOid": "s1", "state": "OPEN", "isDraft": False, "url": "u",
            "labels": [{"name": "agent:claude"}],
            "reviews": [{"state": "APPROVED", "commit_id": "s1"}],
            "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}],
            "comments": [],
        }]
    merges = []
    monkeypatch.setattr("renquant_orchestrator.agent_workflows.fetch_open_prs", _prs)
    monkeypatch.setattr("renquant_orchestrator.agent_workflows.comment_pr",
                        lambda *a, **k: (0, "ok"))
    monkeypatch.setattr("renquant_orchestrator.agent_workflows.merge_pr",
                        lambda repo, number, token, strategy="merge":
                            merges.append(repo) or (0, "merged"))
    out = R.run_repos(action="agent", repo="all", manifest=_manifest(tmp_path),
                      agent="claude", workflow="merge", execute=True,
                      allow_all=True, max_merges=1)
    # 3 repos each have a mergeable PR, but the cap stops after 1 merge.
    assert out["merge_cap"] == 1
    assert out["total_merged"] == 1
    assert len(merges) == 1


def test_review_action_is_cross_repo_without_gate(tmp_path, monkeypatch):
    """review is read/non-destructive → no allow-all needed across all repos."""
    monkeypatch.setattr(
        "renquant_orchestrator.agent_workflows.fetch_open_prs",
        lambda _repo, _token: [],
    )
    out = R.run_repos(action="agent", repo="all", manifest=_manifest(tmp_path),
                      agent="claude", workflow="review")
    assert out["n_repos"] == 3
    assert all("plan" in r for r in out["repos"])


# ── CLI arg-parsing regression (the REMAINDER-swallow bug) ───────────────

def test_cli_repos_agent_flags_not_swallowed(monkeypatch, capsys):
    """`repos agent --as claude --workflow review` must parse the flags;
    the earlier exec_cmd=REMAINDER greedily ate them."""
    from renquant_orchestrator import cli
    captured = {}

    def _fake_run_repos(**kw):
        captured.update(kw)
        return {"ok": True}

    monkeypatch.setattr("renquant_orchestrator.repos.run_repos", _fake_run_repos)
    rc = cli.main(["repos", "agent", "--as", "claude", "--workflow", "review",
                   "--repo", "all"])
    assert rc == 0
    assert captured["agent"] == "claude"
    assert captured["workflow"] == "review"
    assert captured["action"] == "agent"


def test_cli_repos_exec_splits_on_double_dash(monkeypatch):
    from renquant_orchestrator import cli
    captured = {}
    monkeypatch.setattr("renquant_orchestrator.repos.run_repos",
                        lambda **kw: captured.update(kw) or {"ok": True})
    rc = cli.main(["repos", "exec", "--repo", "renquant-common", "--",
                   "git", "status", "--short"])
    assert rc == 0
    assert captured["action"] == "exec"
    assert captured["repo"] == "renquant-common"
    assert captured["exec_cmd"] == ["git", "status", "--short"]
