"""What the machine is missing, not just that its HEAD differs.

`run_surface_drift_check` already alarms on a commit mismatch. A commit id does not say
what the drift costs: measured 2026-08-01 with the deployed checkout 158 commits behind,
**20 of 80** `ops/` files were absent from the machine entirely — including `ops_audit.py`,
the aggregator itself — and 11 more differed.

These tests use a synthetic pair of repos. Asserting against the real deployed checkout
would make them pass or fail by how recently someone synced a machine.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS))

import deployed_ops_surface_gap as G  # noqa: E402


def _run(*a, cwd):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def pair(tmp_path):
    """An 'upstream' and a 'deployed' clone that has fallen behind it."""
    up = tmp_path / "up"
    (up / "ops").mkdir(parents=True)
    _run("git", "init", "-q", ".", cwd=up)
    for n in ("a.py", "b.py"):
        (up / "ops" / n).write_text("x = 1\n")
    _run("git", "add", "-A", cwd=up)
    _run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one", cwd=up)

    dep = tmp_path / "dep"
    _run("git", "clone", "-q", str(up), str(dep), cwd=tmp_path)

    # upstream moves: adds a file, edits another
    (up / "ops" / "c.py").write_text("y = 2\n")
    (up / "ops" / "b.py").write_text("x = 999\n")
    _run("git", "add", "-A", cwd=up)
    _run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "two", cwd=up)
    _run("git", "fetch", "-q", "origin", cwd=dep)
    return dep


def test_an_ABSENT_file_is_reported_by_name(pair):
    rep = G.survey(pair, "origin/main", "ops")
    if rep["status"] != "checked":                       # older git default branch name
        rep = G.survey(pair, "origin/master", "ops")
    assert rep["status"] == "checked"
    assert rep["absent_from_machine"] == ["ops/c.py"]


def test_a_DIVERGENT_file_is_separate_from_an_absent_one(pair):
    rep = G.survey(pair, "origin/main", "ops")
    if rep["status"] != "checked":
        rep = G.survey(pair, "origin/master", "ops")
    assert rep["divergent_on_machine"] == ["ops/b.py"]
    assert "ops/b.py" not in rep["absent_from_machine"]
    assert rep["n_gap"] == 2


def test_an_UNCHANGED_file_is_in_neither_list(pair):
    rep = G.survey(pair, "origin/main", "ops")
    if rep["status"] != "checked":
        rep = G.survey(pair, "origin/master", "ops")
    assert "ops/a.py" not in rep["absent_from_machine"]
    assert "ops/a.py" not in rep["divergent_on_machine"]


def test_a_file_only_on_the_MACHINE_is_its_own_condition(pair):
    """A retired tool still installed, or a local edit — neither is 'absent', and folding
    them together would report a sync as removing something it does not."""
    (pair / "ops" / "local_only.py").write_text("z = 3\n")
    _run("git", "add", "-A", cwd=pair)
    _run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "local",
         cwd=pair)
    rep = G.survey(pair, "origin/main", "ops")
    if rep["status"] != "checked":
        rep = G.survey(pair, "origin/master", "ops")
    assert rep["present_only_on_machine"] == ["ops/local_only.py"]
    assert "ops/local_only.py" not in rep["absent_from_machine"]


def test_commits_behind_and_ahead_are_both_reported(pair):
    rep = G.survey(pair, "origin/main", "ops")
    if rep["status"] != "checked":
        rep = G.survey(pair, "origin/master", "ops")
    assert rep["commits_behind"] == 1
    assert rep["commits_ahead"] == 0


# ------------------------------------------------------------------- fail-closed --
def test_a_NON_CHECKOUT_skips_rather_than_reporting_a_clean_machine(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert G.survey(d, "origin/main", "ops")["status"] == "not_a_checkout"
    assert G.main(["--run-repo", str(d)]) == 3


def test_an_UNRESOLVABLE_ref_skips_rather_than_reporting_no_gap(pair):
    assert G.survey(pair, "origin/nope", "ops")["status"] == "ref_unresolvable"
    assert G.main(["--run-repo", str(pair), "--ref", "origin/nope"]) == 3


def test_exit_0_when_the_machine_is_current(tmp_path):
    up = tmp_path / "u2"
    (up / "ops").mkdir(parents=True)
    _run("git", "init", "-q", ".", cwd=up)
    (up / "ops" / "a.py").write_text("x = 1\n")
    _run("git", "add", "-A", cwd=up)
    _run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one", cwd=up)
    dep = tmp_path / "d2"
    _run("git", "clone", "-q", str(up), str(dep), cwd=tmp_path)
    for ref in ("origin/main", "origin/master"):
        rc = G.main(["--run-repo", str(dep), "--ref", ref])
        if rc != 3:
            assert rc == 0
            return
    pytest.fail("neither origin/main nor origin/master resolved")


def test_the_tool_never_syncs_anything():
    """It reports a machine landing; it does not perform one. A `git pull`/`checkout`/
    `reset` in here would be exactly the class of action that has clobbered uncommitted
    operational fixes before."""
    src = (OPS / "deployed_ops_surface_gap.py").read_text()
    for forbidden in ("pull", "checkout", "reset", "fetch", "merge", "clean"):
        assert f'"{forbidden}"' not in src, forbidden
