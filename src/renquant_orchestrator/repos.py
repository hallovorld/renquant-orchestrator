"""The single cross-repo control-plane entrypoint.

One command to operate across all renquant repos, driven by the manifest
(`subrepos.lock.json`) — no monorepo, no submodules. The manifest says
*which* repos and *where* their local clones live; this module iterates.

    renquant-orchestrator repos <action> [--repo <name|all>] [options]

Actions:
  list    : the repos this control plane manages (from the manifest)
  status  : per-repo git status — branch, dirty?, ahead/behind origin/main
  sync    : fetch all; fast-forward `main` on clean repos (§3.2-safe)
  prs     : open PRs across every repo, in one view
  exec    : run an arbitrary command in each repo's local clone
  agent   : run a per-agent PR workflow (review/fix/merge) across repos —
            the cross-repo form of `agent-workflow`

Design: doc/cross-repo-control-plane-design.md (merged PR #23, hardened by
#24). Read-only actions default to `--repo all`; cross-repo MERGE execution
is gated behind `--allow-all` + a bounded `--max-merges` so a bad approval
cannot silently fan a merge across every repo.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_MANIFEST = Path("/Users/renhao/git/github/RenQuant/subrepos.lock.json")

#: Actions that change remote/local state (vs read-only).
MUTATING_ACTIONS = {"sync", "exec", "agent"}


@dataclass(frozen=True)
class RepoEntry:
    name: str
    local_path: Path
    owner_repo: str          # "hallovorld/renquant-common"
    role: str = "subrepo"    # "umbrella" | "subrepo"

    @property
    def exists(self) -> bool:
        return (self.local_path / ".git").exists()


def _owner_repo_from_remote(remote: str) -> str:
    tail = remote.split("github.com/", 1)[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[RepoEntry]:
    """Parse the manifest into the managed repo set (umbrella first)."""
    data = json.loads(Path(path).read_text())
    out: list[RepoEntry] = []
    src = data.get("source_repo") or {}
    if src.get("local_path") and src.get("remote"):
        out.append(RepoEntry(
            name=src["name"], local_path=Path(src["local_path"]),
            owner_repo=_owner_repo_from_remote(src["remote"]), role="umbrella",
        ))
    for s in data.get("subrepos") or []:
        if not (s.get("local_path") and s.get("remote")):
            continue
        out.append(RepoEntry(
            name=s["name"], local_path=Path(s["local_path"]),
            owner_repo=_owner_repo_from_remote(s["remote"]), role="subrepo",
        ))
    return out


def select_repos(entries: list[RepoEntry], repo: Optional[str]) -> list[RepoEntry]:
    """`repo` is None/"all" → all; else match by name or owner/repo."""
    if not repo or repo == "all":
        return entries
    want = repo.split("/")[-1]
    sel = [e for e in entries if e.name == want or e.owner_repo == repo]
    if not sel:
        raise ValueError(f"repo {repo!r} not in manifest")
    return sel


# ─────────────────────────── shell helpers ─────────────────────────────

def _git(path: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _run(path: Path, cmd: Sequence[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(path), capture_output=True, text=True, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _gh_json(args: Sequence[str], token: Optional[str] = None) -> Any:
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


# ─────────────────────────── per-repo actions ──────────────────────────

def repo_status(e: RepoEntry) -> dict:
    if not e.exists:
        return {"repo": e.name, "present": False}
    _, branch = _git(e.local_path, "branch", "--show-current")
    _, porcelain = _git(e.local_path, "status", "--porcelain")
    ahead = behind = None
    rc, counts = _git(e.local_path, "rev-list", "--left-right", "--count",
                      "origin/main...HEAD")
    if rc == 0 and "\t" in counts:
        b, a = counts.split("\t")
        behind, ahead = int(b), int(a)
    return {
        "repo": e.name, "present": True, "branch": branch or "(detached)",
        "dirty": bool(porcelain.strip()), "ahead": ahead, "behind": behind,
    }


def repo_sync(e: RepoEntry) -> dict:
    """Fetch; fast-forward main only when on a clean main (§3.2-safe)."""
    if not e.exists:
        return {"repo": e.name, "present": False}
    _git(e.local_path, "fetch", "origin", "--quiet")
    _, branch = _git(e.local_path, "branch", "--show-current")
    _, porcelain = _git(e.local_path, "status", "--porcelain")
    if branch == "main" and not porcelain.strip():
        rc, out = _git(e.local_path, "pull", "--ff-only", "origin", "main")
        return {"repo": e.name, "fetched": True, "ff": rc == 0,
                "detail": out.splitlines()[-1] if out else ""}
    return {"repo": e.name, "fetched": True, "ff": False,
            "detail": f"on {branch or 'detached'}"
                      f"{' (dirty)' if porcelain.strip() else ''} — fetch only"}


def repo_open_prs(e: RepoEntry, token: Optional[str] = None) -> dict:
    try:
        prs = _gh_json(["pr", "list", "--repo", e.owner_repo, "--state", "open",
                        "--json", "number,title,headRefName,author,isDraft",
                        "--limit", "100"], token) or []
    except RuntimeError as exc:
        return {"repo": e.name, "error": str(exc)}
    return {"repo": e.name, "open_prs": [
        {"number": p["number"], "title": p["title"], "branch": p["headRefName"],
         "author": (p.get("author") or {}).get("login"), "draft": p.get("isDraft", False)}
        for p in prs
    ]}


def repo_exec(e: RepoEntry, cmd: Sequence[str]) -> dict:
    if not e.exists:
        return {"repo": e.name, "present": False}
    rc, out = _run(e.local_path, cmd)
    return {"repo": e.name, "rc": rc, "output": out[-2000:]}


# ─────────────────────────── dispatcher ────────────────────────────────

def run_repos(
    *,
    action: str,
    repo: Optional[str],
    manifest: Path = DEFAULT_MANIFEST,
    exec_cmd: Optional[Sequence[str]] = None,
    # agent action passthrough:
    agent: Optional[str] = None,
    workflow: Optional[str] = None,
    execute: bool = False,
    merge_strategy: str = "merge",
    allow_no_checks: bool = False,
    allow_all: bool = False,
    max_merges: int = 0,
    token: Optional[str] = None,
) -> dict:
    entries = select_repos(load_manifest(manifest), repo)
    result: dict = {"action": action, "repo_selector": repo or "all",
                    "n_repos": len(entries), "repos": []}

    if action == "list":
        result["repos"] = [
            {"name": e.name, "owner_repo": e.owner_repo,
             "local_path": str(e.local_path), "role": e.role, "present": e.exists}
            for e in entries
        ]
        return result
    if action == "status":
        result["repos"] = [repo_status(e) for e in entries]
        return result
    if action == "sync":
        result["repos"] = [repo_sync(e) for e in entries]
        return result
    if action == "prs":
        result["repos"] = [repo_open_prs(e, token) for e in entries]
        result["total_open"] = sum(len(r.get("open_prs", [])) for r in result["repos"])
        return result
    if action == "exec":
        if not exec_cmd:
            raise ValueError("repos exec requires a command after --")
        result["command"] = list(exec_cmd)
        result["repos"] = [repo_exec(e, exec_cmd) for e in entries]
        return result
    if action == "agent":
        if not agent or not workflow:
            raise ValueError("repos agent requires --as and --workflow")
        # Blast-radius gate (design §9 Q3): a cross-repo MERGE that actually
        # executes must be opted into explicitly and bounded — a single bad
        # approval must not silently fan a merge across every repo.
        cross_repo = (repo in (None, "all")) and len(entries) > 1
        if workflow == "merge" and execute and cross_repo and not allow_all:
            raise ValueError(
                "cross-repo `repos agent --workflow merge --execute` requires "
                "--allow-all and a bounded --max-merges (refusing to merge "
                "across every repo on an implicit selector). Narrow with "
                "--repo <one>, or pass --allow-all --max-merges N."
            )
        from .agent_workflows import resolve_token, run_agent_workflow
        tok = resolve_token(agent, token)
        merged_so_far = 0
        cap = max_merges if (workflow == "merge" and execute and allow_all) else None
        for e in entries:
            do_execute = execute
            if cap is not None and merged_so_far >= cap:
                # Hit the cross-repo merge cap — stop executing further merges
                # but still report the remaining queues (dry).
                do_execute = False
            try:
                plan = run_agent_workflow(
                    agent=agent, workflow=workflow, repo=e.owner_repo, token=tok,
                    execute=do_execute, merge_strategy=merge_strategy,
                    allow_no_checks=allow_no_checks,
                    require_distinct_actor_tokens=workflow == "merge" and do_execute,
                )
                if cap is not None:
                    merged_so_far += sum(
                        1 for x in plan.get("executed", []) if x.get("merged")
                    )
            except Exception as exc:  # noqa: BLE001 — isolate per-repo failure
                plan = {"repo": e.owner_repo, "error": str(exc)}
            result["repos"].append({"repo": e.name, "plan": plan})
        if cap is not None:
            result["merge_cap"] = cap
            result["total_merged"] = merged_so_far
        return result
    raise ValueError(f"unknown repos action {action!r}")
