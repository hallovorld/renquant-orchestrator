"""One scheduled surface for detectors that were merged and never run.

Measured 2026-07-30: `ops/` carried 24 runnable tools, 7 were referenced by a
launchd job, and the 17 unscheduled included GOAL-5's AC5 silent-refusal sentinel —
absent from the manifest, absent from `launchctl list`, with no `*refusal*` log ever
written. The ledger said "AC5 = #619 merged", true about the merge and silent about
the deployment.
"""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location("oa", REPO / "ops" / "ops_audit.py")
oa = importlib.util.module_from_spec(_S)
_S.loader.exec_module(oa)


def _member(tmp_path, name, body):
    p = tmp_path / f"{name}.py"
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return (name, f"{name}.py", [])


def test_a_clean_member_is_ok(tmp_path):
    m = _member(tmp_path, "clean", "print('all clear')\n")
    r = oa.audit(tmp_path, (m,))
    assert r["results"][0]["status"] == oa.STATUS_OK
    assert r["aggregate_exit"] == oa.EXIT_OK


def test_a_nonzero_exit_WITHOUT_a_traceback_is_a_FINDING(tmp_path):
    """A detector's nonzero exit is its delivered signal, not a fault."""
    m = _member(tmp_path, "found", "print('2 problems'); raise SystemExit(1)\n")
    r = oa.audit(tmp_path, (m,))
    assert r["results"][0]["status"] == oa.STATUS_FINDINGS
    assert r["aggregate_exit"] == oa.EXIT_FINDINGS


def test_a_TRACEBACK_is_a_CRASH_not_a_finding(tmp_path):
    """THE #622 DISTINCTION. An uncaught exception also exits 1. Collapsing the two
    is how a dead detector reads as a working one."""
    m = _member(tmp_path, "boom", "raise ValueError('bang')\n")
    r = oa.audit(tmp_path, (m,))
    assert r["results"][0]["status"] == oa.STATUS_CRASH
    assert r["aggregate_exit"] == oa.EXIT_HARNESS


def test_a_harness_problem_OUTRANKS_a_finding(tmp_path):
    """A detector that could not run is not a detector that found nothing, so one
    crash must not be masked by five clean members."""
    ms = (_member(tmp_path, "ok1", "print('fine')\n"),
          _member(tmp_path, "found1", "raise SystemExit(1)\n"),
          _member(tmp_path, "boom1", "raise ValueError('x')\n"))
    r = oa.audit(tmp_path, ms)
    assert r["aggregate_exit"] == oa.EXIT_HARNESS


def test_a_missing_member_is_reported_not_skipped(tmp_path):
    r = oa.audit(tmp_path, (("ghost", "nope.py", []),))
    assert r["results"][0]["status"] == oa.STATUS_MISSING
    assert r["aggregate_exit"] == oa.EXIT_HARNESS


def test_one_member_cannot_hang_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "PER_MEMBER_TIMEOUT_S", 1)
    m = _member(tmp_path, "slow", "import time; time.sleep(30)\n")
    r = oa.audit(tmp_path, (m,))
    assert r["results"][0]["status"] == oa.STATUS_TIMEOUT
    assert r["aggregate_exit"] == oa.EXIT_HARNESS


def test_every_member_exists_in_this_checkout():
    """Anti-vacuity, and the thing most likely to rot: a renamed detector would
    otherwise be silently reported MISSING forever and the audit would look busy."""
    for name, rel, _ in oa.MEMBERS:
        assert (REPO / "ops" / rel).exists(), f"{name} -> {rel}"


def test_no_member_writes(tmp_path):
    """The membership rule. A tool that mutates state does not belong in a
    read-only audit however useful its output."""
    import re
    WRITE = re.compile(r"open\([^)]*['\"][wa]|write_text|json\.dump\(|\.mkdir\(|"
                       r"shutil\.|os\.remove|os\.rename")
    for name, rel, _ in oa.MEMBERS:
        src = (REPO / "ops" / rel).read_text(errors="ignore")
        bad = [l for l in src.splitlines()
               if WRITE.search(l) and not l.strip().startswith("#")]
        assert bad == [], f"{name} writes: {bad[:2]}"


def test_the_manifest_carries_the_job():
    jobs = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
    assert "com.renquant.ops-audit" in jobs
