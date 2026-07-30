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


def test_no_two_globs_match_the_same_FILE_on_this_machine():
    """The dynamic half. Prefix uniqueness is a proxy; this is the thing itself.
    Skips nothing -- a glob matching zero files still contributes an empty set, and
    the emptiness is reported separately below rather than silently passing."""
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


def test_a_glob_matching_nothing_is_REPORTED_not_silently_passing():
    """A glob that matches no file cannot make its job look alive -- but it also
    cannot make it look dead correctly, and it is indistinguishable from a typo.
    This test does not fail on it; it fails only if the count grows past what is
    recorded, so a new empty glob has to be looked at."""
    empty = [l for l, g in _globs() if not globmod.glob(g)]
    # Measured 2026-07-30 on this machine. rq104-model-freshness is expected: its
    # plist is not installed yet (#638), so it has never written.
    assert set(empty) <= {"com.renquant.rq104-model-freshness"}, empty
