"""What a repo-wide walk sees, minus what the repo contains.

Measured 2026-08-01: `rglob('*.py')` in `renquant-orchestrator` returns 5 238 files, of
which 2 329 (44.5%) sit inside one of six nested checkouts under `.claude/worktrees/` —
stale copies of this repo on branches that stopped moving weeks ago. 414 tracked basenames
have at least one stale twin.

The load-bearing test is the one that keeps `.venv` out of the signal: a first version
reported "90.6% untracked" and 2 419 of those were a virtualenv. A guard that fires on
every Python repo forever says nothing.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS))

import search_surface_audit as S  # noqa: E402


def _repo(tmp_path, name="r"):
    r = tmp_path / name
    (r / "src").mkdir(parents=True)
    (r / "src" / "real.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    return r


# ------------------------------------------------------- the distinction that matters --
def test_a_VENV_is_untracked_but_is_NOT_the_signal(tmp_path):
    """The correction. 2 419 `.venv` files made the first version fire on every repo."""
    r = _repo(tmp_path)
    v = r / ".venv" / "lib"
    v.mkdir(parents=True)
    for i in range(30):
        (v / f"m{i}.py").write_text("y = 2\n")
    rep = S.audit(r)
    assert rep["n_untracked"] == 30
    assert rep["n_untracked_environment"] == 30
    assert rep["n_in_nested_checkout"] == 0
    assert rep["over_threshold"] is False


def test_a_NESTED_CHECKOUT_is_the_signal(tmp_path):
    r = _repo(tmp_path)
    inner = r / "anywhere" / "copy"
    inner.mkdir(parents=True)
    (inner / "real.py").write_text("x = 999\n")
    subprocess.run(["git", "init", "-q", str(inner)], check=True)
    rep = S.audit(r)
    assert rep["n_in_nested_checkout"] >= 1
    assert rep["nested_checkout_roots"] == ["anywhere/copy"]
    assert rep["over_threshold"] is True


def test_nested_checkouts_are_found_STRUCTURALLY_not_by_NAME(tmp_path):
    """`.claude/worktrees` is where they happen to live today. A name list is the
    fail-open version: the next tool to park a checkout elsewhere is invisible to it."""
    r = _repo(tmp_path)
    odd = r / "some" / "unforeseen" / "place"
    odd.mkdir(parents=True)
    (odd / "real.py").write_text("x = 2\n")
    subprocess.run(["git", "init", "-q", str(odd)], check=True)
    assert S.audit(r)["nested_checkout_roots"] == ["some/unforeseen/place"]


def test_a_WORKTREE_whose_dot_git_is_a_FILE_counts_too(tmp_path):
    """Git worktrees carry a `.git` FILE, not a directory. Accepting only directories
    would miss exactly the six that prompted this."""
    r = _repo(tmp_path)
    wt = r / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /somewhere/else\n")
    (wt / "real.py").write_text("x = 3\n")
    assert S.audit(r)["nested_checkout_roots"] == ["wt"]


def test_a_checkout_INSIDE_a_checkout_is_not_double_counted(tmp_path):
    r = _repo(tmp_path)
    outer = r / "o"
    (outer / "i").mkdir(parents=True)
    (outer / "real.py").write_text("a = 1\n")
    (outer / "i" / "real.py").write_text("b = 2\n")
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    subprocess.run(["git", "init", "-q", str(outer / "i")], check=True)
    assert S.audit(r)["nested_checkout_roots"] == ["o"]


def test_shadowed_basenames_are_reported(tmp_path):
    r = _repo(tmp_path)
    inner = r / "copy"
    inner.mkdir()
    (inner / "real.py").write_text("x = 999\n")
    subprocess.run(["git", "init", "-q", str(inner)], check=True)
    rep = S.audit(r)
    assert "real.py" in rep["example_shadowed_basenames"]
    assert rep["n_tracked_basenames_with_a_stale_twin"] == 1


# ------------------------------------------------------------------------- plumbing --
def test_a_NON_REPO_root_SKIPS_rather_than_alarming(tmp_path):
    """An empty tracked set would make every file look untracked and turn a plain
    directory into a maximal alarm — a detector reporting a catastrophe it never
    measured."""
    d = tmp_path / "plain"
    (d / "x").mkdir(parents=True)
    (d / "x" / "a.py").write_text("z = 1\n")
    assert S.tracked_files(d) is None
    assert S.audit(d)["status"] == "not_a_git_repo"
    assert S.main(["--root", str(d)]) == 3


def test_a_CLEAN_repo_exits_0(tmp_path):
    assert S.main(["--root", str(_repo(tmp_path))]) == 0


def test_a_CONTAMINATED_repo_exits_1(tmp_path):
    r = _repo(tmp_path)
    inner = r / "copy"
    inner.mkdir()
    (inner / "real.py").write_text("x = 9\n")
    subprocess.run(["git", "init", "-q", str(inner)], check=True)
    assert S.main(["--root", str(r)]) == 1


def test_json_mode_separates_the_two_untracked_populations(tmp_path, capsys):
    r = _repo(tmp_path)
    (r / ".venv").mkdir()
    (r / ".venv" / "v.py").write_text("v = 1\n")
    inner = r / "copy"
    inner.mkdir()
    (inner / "real.py").write_text("x = 9\n")
    subprocess.run(["git", "init", "-q", str(inner)], check=True)
    S.main(["--root", str(r), "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["n_untracked"] == rep["n_untracked_environment"] + rep["n_in_nested_checkout"]
    assert rep["n_untracked_environment"] == 1 and rep["n_in_nested_checkout"] == 1
