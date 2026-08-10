"""Read-only pin-identity check for the dawn preflight monitor (#968 r1).

The monitor must fail closed unless .subrepo_runtime/repos matches
subrepos.lock.json, so its 06:05 preview is bound to the SAME pinned runtime the
13:55 order path aligns to. These controls pin: clean → exit 0; a drifted HEAD,
a dirty tree, a missing repo, and an unreadable lock all → exit 1 (fail-closed);
and the receipt records the per-repo lock vs resolved HEAD.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

from dawn_pin_identity_check import check, main  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _mk_repo(root: Path, name: str, *, extra_commit: bool = False, dirty: bool = False) -> str:
    """Create a git repo at root/name; return the HEAD sha it is left on."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c1")
    head = _git(repo, "rev-parse", "HEAD")
    if extra_commit:
        (repo / "a.txt").write_text("2")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "c2")
        head = _git(repo, "rev-parse", "HEAD")
    if dirty:
        (repo / "a.txt").write_text("dirty-uncommitted")
    return head


def _lock(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "subrepos.lock.json"
    p.write_text(json.dumps({"schema_version": 1, "subrepos": entries}))
    return p


def test_clean_aligned_passes(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    h2 = _mk_repo(rt, "repo-b")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-b", "commit": h2}])
    ok, repos = check(lock, rt)
    assert ok is True
    assert all(r["ok"] and r["pinned"] and not r["dirty"] for r in repos)
    receipt = tmp_path / "r.json"
    rc = main(["--repo-dir", str(tmp_path), "--runtime-root", str(rt),
               "--lock", str(lock), "--receipt-out", str(receipt), "--now", "2026-08-10T00:00:00Z"])
    assert rc == 0
    body = json.loads(receipt.read_text())
    assert body["ok"] is True and body["entrypoint"] == "dawn_funnel_preflight"
    assert {r["name"] for r in body["repos"]} == {"repo-a", "repo-b"}


def test_drifted_head_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    # repo-b's runtime HEAD advances past the lock commit
    h2_lock = _mk_repo(rt, "repo-b", extra_commit=False)
    _git(rt / "repo-b", "commit", "-q", "--allow-empty", "-m", "drift")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-b", "commit": h2_lock}])
    ok, repos = check(lock, rt)
    assert ok is False
    b = next(r for r in repos if r["name"] == "repo-b")
    assert b["pinned"] is False and b["ok"] is False
    assert main(["--repo-dir", str(tmp_path), "--runtime-root", str(rt), "--lock", str(lock)]) == 1


def test_dirty_tree_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a", dirty=True)
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1}])
    ok, repos = check(lock, rt)
    assert ok is False
    assert repos[0]["pinned"] is True and repos[0]["dirty"] is True and repos[0]["ok"] is False


def test_missing_repo_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-gone", "commit": "0" * 40}])
    ok, repos = check(lock, rt)
    assert ok is False
    gone = next(r for r in repos if r["name"] == "repo-gone")
    assert gone["present"] is False and gone["ok"] is False


def test_unreadable_lock_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    _mk_repo(rt, "repo-a")
    missing_lock = tmp_path / "nope.json"
    rc = main(["--repo-dir", str(tmp_path), "--runtime-root", str(rt),
               "--lock", str(missing_lock)])
    assert rc == 1
