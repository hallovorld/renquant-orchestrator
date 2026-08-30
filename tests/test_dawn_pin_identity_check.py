"""Read-only pin-identity check for the dawn preflight monitor (#968 r1; two
verdicts since 2026-08-30).

The monitor must fail closed unless .subrepo_runtime/repos matches
subrepos.lock.json, so its 06:05 preview is bound to the SAME pinned runtime the
13:55 order path aligns to. The order path's predicate is `_is_pinned` alone
(subrepo_assemble._ensure_repo returns on HEAD == lock without consulting
`_is_dirty`), and from 08-19 to 08-27 this check aborted seven sessions over a
dirty auto-generated README while the daily ran. So: PIN_MISMATCH (HEAD != lock,
missing repo, unreadable lock) → exit 1, abort; TREE_DIRTY in docs/README/
generated paths → exit 0 with a WARN, proceed; TREE_DIRTY_BLOCKING (src/,
configs/, code, or anything the allow-list does not name) → exit 2, abort. The
receipt carries pin_mismatch, tree_dirty, tree_dirty_blocking and the files.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

from dawn_pin_identity_check import (  # noqa: E402
    EXIT_PIN_MISMATCH,
    EXIT_PROCEED,
    EXIT_TREE_DIRTY_BLOCKING,
    VERDICT_OK,
    VERDICT_PIN_MISMATCH,
    VERDICT_TREE_DIRTY,
    VERDICT_TREE_DIRTY_BLOCKING,
    check,
    classify_dirty_path,
    main,
    porcelain_paths,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _mk_repo(root: Path, name: str, *, extra_commit: bool = False,
             dirty: str | None = None, untracked: str | None = None,
             files: tuple[str, ...] = ("a.txt", "README.md", "src/pkg/mod.py", "doc/notes.md")) -> str:
    """Create a git repo at root/name with `files` committed; return HEAD.
    `dirty` modifies a tracked path; `untracked` adds a new one."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for f in files:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text("1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c1")
    head = _git(repo, "rev-parse", "HEAD")
    if extra_commit:
        (repo / "a.txt").write_text("2")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "c2")
        head = _git(repo, "rev-parse", "HEAD")
    if dirty:
        (repo / dirty).write_text("dirty-uncommitted")
    if untracked:
        (repo / untracked).parent.mkdir(parents=True, exist_ok=True)
        (repo / untracked).write_text("new")
    return head


def _lock(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "subrepos.lock.json"
    p.write_text(json.dumps({"schema_version": 1, "subrepos": entries}))
    return p


def _run(tmp_path: Path, rt: Path, lock: Path, capsys=None):
    receipt = tmp_path / "r.json"
    rc = main(["--repo-dir", str(tmp_path), "--runtime-root", str(rt),
               "--lock", str(lock), "--receipt-out", str(receipt), "--now", "2026-08-30T00:00:00Z"])
    return rc, json.loads(receipt.read_text())


# --- the four verdicts the wrapper distinguishes ------------------------------

def test_clean_aligned_passes(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    h2 = _mk_repo(rt, "repo-b")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-b", "commit": h2}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_OK
    assert all(r["ok"] and r["pinned"] and not r["dirty"] and r["verdict"] == VERDICT_OK for r in repos)
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_PROCEED == 0
    assert body["ok"] is True and body["verdict"] == VERDICT_OK
    assert body["pin_mismatch"] is False and body["tree_dirty"] is False and body["tree_dirty_blocking"] is False
    assert body["dirty_files"] == {} and body["entrypoint"] == "dawn_funnel_preflight"
    assert {r["name"] for r in body["repos"]} == {"repo-a", "repo-b"}


def test_dirty_readme_only_proceeds_with_a_warn(tmp_path, capsys):
    """The 08-19..08-27 shape: every HEAD equals the lock, one auto-generated
    README is modified. Exit 0, verdict TREE_DIRTY, files named, WARN printed."""
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "renquant-model", dirty="README.md")
    lock = _lock(tmp_path, [{"name": "renquant-model", "commit": h1}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_TREE_DIRTY
    assert repos[0]["pinned"] is True and repos[0]["dirty"] is True and repos[0]["ok"] is True
    assert repos[0]["dirty_files"] == ["README.md"] and repos[0]["blocking_dirty_files"] == []
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_PROCEED
    assert body["ok"] is True and body["verdict"] == VERDICT_TREE_DIRTY
    assert body["pin_mismatch"] is False and body["tree_dirty"] is True and body["tree_dirty_blocking"] is False
    assert body["dirty_files"] == {"renquant-model": ["README.md"]}
    out = capsys.readouterr().out
    assert "WARN: TREE_DIRTY (non-blocking" in out and "renquant-model: README.md" in out
    assert "not aligned" not in out


def test_dirty_src_file_aborts_as_tree_dirty_blocking(tmp_path, capsys):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a", dirty="src/pkg/mod.py")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_TREE_DIRTY_BLOCKING
    assert repos[0]["pinned"] is True and repos[0]["ok"] is False
    assert repos[0]["blocking_dirty_files"] == ["src/pkg/mod.py"]
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_TREE_DIRTY_BLOCKING == 2
    assert body["ok"] is False and body["verdict"] == VERDICT_TREE_DIRTY_BLOCKING
    assert body["pin_mismatch"] is False and body["tree_dirty"] is True and body["tree_dirty_blocking"] is True
    assert body["blocking_dirty_files"] == {"repo-a": ["src/pkg/mod.py"]}
    assert "WARN: TREE_DIRTY (non-blocking" not in capsys.readouterr().out


def test_drifted_head_fails_closed_as_pin_mismatch(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    h2_lock = _mk_repo(rt, "repo-b")
    _git(rt / "repo-b", "commit", "-q", "--allow-empty", "-m", "drift")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-b", "commit": h2_lock}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_PIN_MISMATCH
    b = next(r for r in repos if r["name"] == "repo-b")
    assert b["pinned"] is False and b["ok"] is False and b["verdict"] == VERDICT_PIN_MISMATCH
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_PIN_MISMATCH == 1
    assert body["pin_mismatch"] is True and body["ok"] is False and body["verdict"] == VERDICT_PIN_MISMATCH


def test_mismatch_and_dirty_readme_together_is_a_mismatch_with_the_dirty_files_still_listed(tmp_path):
    """PIN_MISMATCH wins; the receipt still carries both fields."""
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a", dirty="README.md")
    _git(rt / "repo-a", "commit", "-q", "--allow-empty", "-m", "drift")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1}])
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_PIN_MISMATCH
    assert body["verdict"] == VERDICT_PIN_MISMATCH and body["pin_mismatch"] is True
    assert body["tree_dirty"] is True and body["dirty_files"] == {"repo-a": ["README.md"]}


def test_blocking_dirty_in_one_repo_and_docs_dirty_in_another_is_blocking(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a", dirty="README.md")
    h2 = _mk_repo(rt, "repo-b", untracked="src/pkg/new.py")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1}, {"name": "repo-b", "commit": h2}])
    rc, body = _run(tmp_path, rt, lock)
    assert rc == EXIT_TREE_DIRTY_BLOCKING
    assert body["dirty_files"] == {"repo-a": ["README.md"], "repo-b": ["src/pkg/new.py"]}
    assert body["blocking_dirty_files"] == {"repo-b": ["src/pkg/new.py"]}


def test_missing_repo_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    h1 = _mk_repo(rt, "repo-a")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": h1},
                            {"name": "repo-gone", "commit": "0" * 40}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_PIN_MISMATCH
    gone = next(r for r in repos if r["name"] == "repo-gone")
    assert gone["present"] is False and gone["ok"] is False and gone["verdict"] == VERDICT_PIN_MISMATCH


def test_a_directory_that_is_not_a_git_repo_is_a_mismatch_not_dirty(tmp_path):
    rt = tmp_path / "repos"
    (rt / "repo-a").mkdir(parents=True)
    (rt / "repo-a" / "README.md").write_text("x")
    lock = _lock(tmp_path, [{"name": "repo-a", "commit": "0" * 40}])
    verdict, repos = check(lock, rt)
    assert verdict == VERDICT_PIN_MISMATCH and repos[0]["error"] == "not a git repository"


def test_unreadable_lock_fails_closed(tmp_path):
    rt = tmp_path / "repos"
    _mk_repo(rt, "repo-a")
    missing_lock = tmp_path / "nope.json"
    receipt = tmp_path / "r.json"
    rc = main(["--repo-dir", str(tmp_path), "--runtime-root", str(rt),
               "--lock", str(missing_lock), "--receipt-out", str(receipt)])
    assert rc == EXIT_PIN_MISMATCH
    body = json.loads(receipt.read_text())
    assert body["verdict"] == VERDICT_PIN_MISMATCH and body["pin_mismatch"] is True and body["ok"] is False


# --- the allow-list is explicit and closed by default -------------------------

@pytest.mark.parametrize("path,blocking", [
    ("README.md", False), ("readme.rst", False), ("README", False), ("README.txt", False),
    ("doc/anything.txt", False), ("docs/guide/x.md", False), ("CHANGELOG.md", False),
    ("src/pkg/__pycache__/mod.cpython-310.pyc", True),   # under src/: blocks whatever it is
    ("tests/__pycache__/x.pyc", False), ("x.pyc", False),
    ("src/README.md", True), ("src/pkg/mod.py", True), ("configs/strategy_config.json", True),
    ("config/x.yaml", True), ("setup.py", True), ("pyproject.toml", True), ("Makefile", True),
    ("requirements.txt", True), ("a.txt", True), ("data/x.parquet", True), ("scripts/run.sh", True),
    ("doc/notes.py", True),   # code under doc/ is still code
])
def test_classify_dirty_path(path, blocking):
    assert classify_dirty_path(path) is blocking, path


def test_porcelain_paths_handle_status_columns_untracked_and_renames():
    porcelain = " M README.md\n?? src/pkg/new.py\nR  old.md -> doc/new.md\nD  gone.md\n"
    assert porcelain_paths(porcelain) == ["README.md", "src/pkg/new.py", "doc/new.md", "gone.md"]


def test_the_wrapper_maps_the_three_exit_codes_and_never_says_not_aligned_for_dirt():
    wrapper = (Path(__file__).resolve().parent.parent / "ops" / "renquant104"
               / "dawn_funnel_preflight.sh").read_text()
    code = "\n".join(l for l in wrapper.splitlines() if l.strip() and not l.strip().startswith("#"))
    assert "PIN_RC=$?" in code
    assert "1) PIN_ABORT=\"PIN_MISMATCH:" in code
    assert "2) PIN_ABORT=\"TREE_DIRTY_BLOCKING:" in code
    assert "not aligned" not in code
    assert 'rq_notify "rq104 dawn preflight ABORT' in code
