"""The subject is what the JOBS reference, and the yardstick is a FETCHED reference.

The existing drift scan asks "does the runtime checkout match the lock pin?" — internal
consistency between two copies, which reports clean forever if the pin is itself old.
This measures the checkouts the launchd jobs actually execute from, against origin/main.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "referenced_checkout_freshness", OPS / "referenced_checkout_freshness.py")
fr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fr)


# --- THE regression: never measure a checkout against its own remote ref ------

def test_a_run_checkout_is_measured_against_its_DEV_sibling():
    """A deployment copy that has not fetched carries a stale origin/main and, asked to
    compare itself to it, reports 0 behind. The first version of this tool did exactly
    that: it called renquant-orchestrator-run 0 behind while a fetched reference put it
    at 110."""
    assert fr.reference_repo_for("renquant-orchestrator-run") == "renquant-orchestrator"
    assert fr.reference_repo_for("renquant-model-run") == "renquant-model"


def test_a_non_run_checkout_is_its_own_reference():
    assert fr.reference_repo_for("renquant-orchestrator") == "renquant-orchestrator"


def test_the_distance_is_counted_in_the_reference_not_the_subject():
    """Source-level, because the behavioural version needs two real checkouts."""
    src = (OPS / "referenced_checkout_freshness.py").read_text()
    i = src.index('"rev-list", "--count"')
    window = src[max(0, i - 300):i]
    assert "str(ref_repo)" in window, (
        "rev-list must run in the reference checkout; running it in the subject "
        "compares a copy to its own outdated idea of the truth")


# --- safety: never git inside the umbrella -----------------------------------

def test_the_umbrella_is_skipped_and_never_gitted():
    r = fr.measure("RenQuant")
    assert r["status"] == "SKIPPED_UMBRELLA"
    src = (OPS / "referenced_checkout_freshness.py").read_text()
    assert "UMBRELLA_NAME" in src
    for line in src.splitlines():
        if '"git"' in line and '-C' in line:
            assert "UMBRELLA" not in line, f"git -C against the umbrella: {line.strip()}"


def test_the_umbrella_skip_is_reported_not_silently_dropped():
    """30 jobs run from the umbrella. Omitting it from the output would read as
    'everything measured is fine'."""
    r = fr.measure("RenQuant")
    assert "different mechanism" in r["detail"]


# --- the subject set comes from the manifest ---------------------------------

def test_referenced_checkouts_reads_program_args(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"jobs": {
        "com.renquant.a": {"program_args": [f"{fr.GITHUB}/renquant-orchestrator-run/ops/x.py"]},
        "com.renquant.b": {"program_args": [f"{fr.GITHUB}/RenQuant/scripts/y.sh"]},
        "com.renquant.c": {"program_args": ["/usr/bin/true"]},
    }}))
    refs = fr.referenced_checkouts(m)
    assert refs == {"renquant-orchestrator-run": ["com.renquant.a"],
                    "RenQuant": ["com.renquant.b"]}
    assert "/usr/bin/true" not in json.dumps(refs)


def test_a_manifest_with_no_absolute_paths_exits_2(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"jobs": {"com.renquant.a": {"program_args": ["/usr/bin/true"]}}}))
    assert fr.main(["--manifest", str(m)]) == 2


def test_a_missing_manifest_exits_2(tmp_path):
    assert fr.main(["--manifest", str(tmp_path / "nope.json")]) == 2


# --- classification -----------------------------------------------------------

def test_a_path_that_is_not_a_checkout_is_reported():
    r = fr.measure("definitely-not-a-repo-xyz")
    assert r["status"] == "NOT_A_CHECKOUT"


def test_the_bound_is_a_stated_constant_not_scattered():
    src = (OPS / "referenced_checkout_freshness.py").read_text()
    assert "MAX_COMMITS_BEHIND = 20" in src
    assert "CHOSEN, not derived" in src, (
        "the one number here that is not a measurement must say so")


def test_the_real_run_checkout_is_referenced_by_more_jobs_than_the_dev_one():
    """Pins the fact that made this worth building: the jobs run from the deployment
    copy, which is not the copy anyone edits or the drift scan checks."""
    refs = fr.referenced_checkouts(OPS / "launchd_manifest.json")
    assert len(refs.get("renquant-orchestrator-run", [])) > \
        len(refs.get("renquant-orchestrator", []))


# --- a failed fetch must NEVER produce a freshness verdict --------------------
# The fetch return code used to be discarded, so a network or auth failure left the
# reference checkout's own origin/main stale and rev-list reported a confident FRESH
# against an old ref --- the exact stale-reference failure this tool detects, recreated
# one layer deeper on the fetch path.

def _fail_fetch(monkeypatch, rc=128, stderr="fatal: could not read from remote"):
    real = fr.subprocess.run
    def fake(argv, *a, **k):
        if len(argv) > 3 and argv[3] == "fetch":
            class R:
                returncode = rc
                stdout = ""
            R.stderr = stderr
            return R()
        return real(argv, *a, **k)
    monkeypatch.setattr(fr.subprocess, "run", fake)


def test_a_failed_fetch_yields_UNMEASURABLE_not_FRESH(monkeypatch, github_root):
    _fail_fetch(monkeypatch)
    r = fr.measure("renquant-orchestrator")
    assert r["status"] == "UNMEASURABLE", r
    assert "fetch failed" in r["detail"]


@pytest.mark.parametrize("rc", [1, 128, 130])
def test_no_fetch_failure_code_can_produce_a_verdict(monkeypatch, rc, github_root):
    """Any non-zero, not just the common one."""
    _fail_fetch(monkeypatch, rc=rc)
    r = fr.measure("renquant-orchestrator")
    assert r["status"] not in ("FRESH", "STALE")
    assert "commits_behind" not in r


def test_a_failed_fetch_makes_the_run_exit_nonzero(monkeypatch):
    _fail_fetch(monkeypatch)
    assert fr.main([]) == 1


def test_origin_main_missing_after_a_SUCCESSFUL_fetch_is_also_UNMEASURABLE(monkeypatch, github_root):
    """A fetch can succeed against a remote with no main; rev-list would then compare
    against nothing."""
    real = fr.subprocess.run
    def fake(argv, *a, **k):
        if len(argv) > 4 and argv[3] == "rev-parse" and "origin/main" in argv:
            class R:
                returncode = 1
                stdout = ""
                stderr = ""
            return R()
        return real(argv, *a, **k)
    monkeypatch.setattr(fr.subprocess, "run", fake)
    r = fr.measure("renquant-orchestrator")
    assert r["status"] == "UNMEASURABLE"
    assert "does not resolve" in r["detail"]


def test_the_unmocked_path_still_measures(github_root):
    """Anti-vacuity: the refusals above come from the mocks, not from measure() having
    become unconditionally UNMEASURABLE."""
    r = fr.measure("renquant-orchestrator")
    assert r["status"] in ("FRESH", "STALE"), r
    assert isinstance(r.get("commits_behind"), int)


# --- a REAL git world, so these tests do not depend on the operator's disk ------
#
# The first version called `fr.measure("renquant-orchestrator")` directly, which
# resolves under `GITHUB` = /Users/renhao/git/github. In CI that path is not a
# checkout, so every assertion below returned NOT_A_CHECKOUT and three tests failed
# — including the anti-vacuity one, whose whole job is to prove `measure()` can still
# reach a verdict. A test that only measures on one machine cannot make that promise.
#
# `GITHUB` is monkeypatchable, so the fixture builds a genuine clone with a real
# `origin/main`. No mocking of git itself: the paths under test are exactly the ones
# that run in production.


def _git(*argv, cwd=None):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *argv],
        cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def github_root(tmp_path, monkeypatch):
    """`<root>/renquant-orchestrator` — a real clone whose origin/main resolves."""
    upstream = tmp_path / "upstream.git"
    _git("init", "--bare", "-b", "main", str(upstream))

    seed = tmp_path / "seed"
    _git("clone", str(upstream), str(seed))
    (seed / "README.md").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", "main", cwd=seed)

    root = tmp_path / "gh"
    root.mkdir()
    _git("clone", str(upstream), str(root / "renquant-orchestrator"))
    monkeypatch.setattr(fr, "GITHUB", root)
    return root


def test_the_fixture_really_is_a_measurable_checkout(github_root):
    """If the fixture stopped producing a measurable repo, every test using it would
    silently degrade to asserting NOT_A_CHECKOUT."""
    r = fr.measure("renquant-orchestrator")
    assert r["status"] in ("FRESH", "STALE"), r
