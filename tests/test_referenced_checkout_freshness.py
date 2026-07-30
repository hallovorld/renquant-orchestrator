"""The subject is what the JOBS reference, and the yardstick is a FETCHED reference.

The existing drift scan asks "does the runtime checkout match the lock pin?" — internal
consistency between two copies, which reports clean forever if the pin is itself old.
This measures the checkouts the launchd jobs actually execute from, against origin/main.
"""

from __future__ import annotations

import importlib.util
import json
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
