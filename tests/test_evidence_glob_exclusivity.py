"""No two manifested jobs may be able to read each other's evidence.

Codex on #635 asked for a deterministic source-of-truth mapping AND that each glob
"cannot overlap another manifested writer". Those are two separate demands and only
the second is mechanically decidable from what exists today:

  * OWNERSHIP -- "these files were written by THIS job" -- is NOT derivable. Measured
    2026-07-30: a static parse of every wrapper for its dated-log assignment resolves
    only 4 of 31 wrappers, because the construction varies (different variable names,
    `tee`, `exec >` redirection, per-module loops). Shipping a 4/31 parser as a
    "source of truth" would be a guard that validates the wrong object for 27 jobs.
    The design options for closing it are recorded in the progress doc; none is a
    test.
  * NON-OVERLAP -- "no two manifested globs can match the same file" -- IS decidable,
    both statically and against this machine. That is what this file enforces. It
    does not prove a glob reads its own job's files; it proves it cannot read a
    SIBLING JOB'S, which is the specific confusion that makes a dead job look alive.
"""

from __future__ import annotations

import glob as globmod
import pathlib
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "ops" / "launchd_manifest.json"


def _globs() -> list[tuple[str, str]]:
    jobs = json.loads(MANIFEST.read_text())["jobs"]
    return [(l, v["evidence_glob"]) for l, v in jobs.items() if v.get("evidence_glob")]


def test_the_manifest_actually_carries_globs():
    """Anti-vacuity. Every assertion below is trivially true over an empty list."""
    assert len(_globs()) >= 15, len(_globs())


def test_no_two_globs_share_a_directory_AND_prefix():
    """The static half. Two jobs writing `logs/rq105/` are separated only by their
    filename prefix; if two globs share both, either can match the other's files
    whatever the dates are."""
    seen: dict[tuple[str, str], str] = {}
    for label, g in _globs():
        key = (os.path.dirname(g), os.path.basename(g).split("[")[0])
        assert key not in seen, f"{label} collides with {seen[key]} on {key}"
        seen[key] = label


def _log_roots_present() -> bool:
    """Do the evidence directories exist here at all?

    The inventory assertion below globs the real filesystem, so it is a statement
    about THIS machine's disk. On a runner none of the log directories exist, every
    glob matches nothing, and it reports all 19 jobs as empty -- a red build whose
    real cause is that there was nothing to look at. Same shape as the umbrella and
    checkout-freshness checks fixed on #634 and #637.
    """
    return any(os.path.isdir(os.path.dirname(g)) for _, g in _globs())


@pytest.mark.skipif(
    not _log_roots_present(),
    reason="no evidence directories on this machine — every glob would match zero "
           "files and this assertion would pass VACUOUSLY; the static half "
           "(test_no_two_globs_share_a_directory_AND_prefix) is what runs in CI")
def test_no_two_globs_match_the_same_FILE_on_this_machine():
    """The dynamic half. Prefix uniqueness is a proxy; this is the thing itself.

    **Marked machine-local after sweeping this file rather than only the test that
    went red.** Where the log directories do not exist, `glob()` returns nothing, the
    loop body never executes, and this passes while checking *nothing* — which is
    worse than the red build next door, because a vacuous pass is never investigated.
    The static half covers CI; this one is only meaningful where the evidence lives.
    """
    owned: dict[str, str] = {}
    for label, g in _globs():
        for path in globmod.glob(g):
            prev = owned.get(path)
            assert prev is None, f"{path} matched by BOTH {prev} and {label}"
            owned[path] = label


def test_every_glob_is_absolute():
    """A relative glob resolves against the scan's cwd, which launchd does not pin."""
    for label, g in _globs():
        assert g.startswith("/"), (label, g)


needs_logs = pytest.mark.skipif(
    not _log_roots_present(),
    reason="no evidence directories on this machine — the inventory below measures a "
           "disk, not the code; see test_an_empty_glob_is_detected for the logic")


def test_an_empty_glob_is_detected(tmp_path):
    """The LOGIC of the inventory assertion, hermetically — this runs everywhere.

    Separated out because the inventory test can only run where the logs live, and a
    machine-local test cannot promise the detection works anywhere else.
    """
    populated = tmp_path / "has_files"
    populated.mkdir()
    (populated / "2026-07-30.log").write_text("x")
    empty_dir = tmp_path / "no_files"
    empty_dir.mkdir()

    pairs = [("job.populated", str(populated / "20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].log")),
             ("job.empty", str(empty_dir / "20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].log"))]
    empty = [l for l, g in pairs if not globmod.glob(g)]
    assert empty == ["job.empty"], empty


@needs_logs
def test_an_empty_glob_is_allowed_ONLY_when_its_job_is_not_installed():
    """A glob matching no file cannot make its job look alive — but it also cannot
    make it look dead correctly, and it is indistinguishable from a typo.

    THE PREVIOUS VERSION HARDCODED THE ANSWER: `set(empty) <=
    {"com.renquant.rq104-model-freshness"}`, an inventory of what one disk held on
    2026-07-30. It went red the moment two more manifested-but-uninstalled jobs
    appeared (`ops-audit`, `rq104-silent-refusal`) — the
    tests-that-measure-the-operator's-disk shape. Extending the literal set would
    have been the enumerate-and-hope repair.

    The rule is DERIVABLE instead: a manifested job that is NOT installed has never
    run, so an empty glob is expected. A manifested job that IS installed and still
    matches nothing is the case worth failing on — and this holds on any machine
    rather than on this one.
    """
    la = pathlib.Path.home() / "Library" / "LaunchAgents"
    unexplained = [label for label, g in _globs()
                   if not globmod.glob(g) and (la / f"{label}.plist").exists()]
    assert unexplained == [], unexplained
