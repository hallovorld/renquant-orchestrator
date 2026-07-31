"""One scheduled surface for detectors that were merged and never run.

Measured 2026-07-30: `ops/` carried 24 runnable tools, 7 were referenced by a
launchd job, and the 17 unscheduled included GOAL-5's AC5 silent-refusal sentinel —
absent from the manifest, absent from `launchctl list`, with no `*refusal*` log ever
written. The ledger said "AC5 = #619 merged", true about the merge and silent about
the deployment.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location("oa", REPO / "ops" / "ops_audit.py")
oa = importlib.util.module_from_spec(_S)
_S.loader.exec_module(oa)


def _member(tmp_path, name, body, finding_exits=(1,)):
    p = tmp_path / f"{name}.py"
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return (name, f"{name}.py", [], finding_exits)


def test_a_clean_member_is_ok(tmp_path):
    m = _member(tmp_path, "clean", "print('all clear')\n")
    r = oa.audit(tmp_path, (m,))
    assert r["results"][0]["status"] == oa.STATUS_OK
    assert r["aggregate_exit"] == oa.EXIT_OK


def test_an_IN_CONTRACT_exit_without_a_traceback_is_a_FINDING(tmp_path):
    """A detector's nonzero exit is its delivered signal, not a fault — but ONLY for
    the codes it declares. The unqualified version of this sentence is the bug codex
    found on #650: it made every nonzero a finding, including "I could not check"."""
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
    r = oa.audit(tmp_path, (("ghost", "nope.py", [], (1,)),))
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
    for name, rel, _, _finding_exits in oa.MEMBERS:
        assert (REPO / "ops" / rel).exists(), f"{name} -> {rel}"


def test_no_member_writes(tmp_path):
    """The membership rule. A tool that mutates state does not belong in a
    read-only audit however useful its output."""
    import re
    WRITE = re.compile(r"open\([^)]*['\"][wa]|write_text|json\.dump\(|\.mkdir\(|"
                       r"shutil\.|os\.remove|os\.rename")
    for name, rel, _, _finding_exits in oa.MEMBERS:
        src = (REPO / "ops" / rel).read_text(errors="ignore")
        bad = [l for l in src.splitlines()
               if WRITE.search(l) and not l.strip().startswith("#")]
        assert bad == [], f"{name} writes: {bad[:2]}"


def test_the_manifest_carries_the_job():
    jobs = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
    assert "com.renquant.ops-audit" in jobs


# --- the finding-exit contract (codex #650) ----------------------------------
#
# The aggregator classified ANY nonzero exit without a traceback as a finding. Every
# detector here already separates "I checked and found something" from "I could not
# check", and the second is a HARNESS problem: `blind_notifier_scan` exits 2 when its
# source directory is absent, `umbrella_script_shadow_check` exits 2 for UNVERIFIABLE,
# and argparse exits 2 on a bad flag. All three would have been reported as a healthy
# detector finding something.

def _stub(tmp_path, body: str):
    p = tmp_path / "stub.py"
    p.write_text(body)
    return p


def test_a_non_traceback_exit_2_is_HARNESS_not_findings(tmp_path):
    """The regression codex asked for, and the whole point of the contract."""
    _stub(tmp_path, "import sys; sys.exit(2)")
    r = oa.run_member("stub", "stub.py", [], (1,), tmp_path)
    assert r["status"] == oa.STATUS_UNUSABLE, r
    assert r["status"] != oa.STATUS_FINDINGS


def test_an_exit_inside_the_contract_is_a_finding(tmp_path):
    """Anti-vacuity: if everything nonzero were unusable, the check could not fire."""
    _stub(tmp_path, "import sys; sys.exit(1)")
    r = oa.run_member("stub", "stub.py", [], (1,), tmp_path)
    assert r["status"] == oa.STATUS_FINDINGS, r


def test_zero_is_still_ok(tmp_path):
    _stub(tmp_path, "import sys; sys.exit(0)")
    assert oa.run_member("stub", "stub.py", [], (1,), tmp_path)["status"] == oa.STATUS_OK


def test_a_traceback_is_still_a_crash_even_on_a_contract_exit(tmp_path):
    """A tool that dies mid-verdict must not be laundered into a finding by its code."""
    _stub(tmp_path, "raise SystemExit(__import__('sys').stderr.write("
                    "'Traceback (most recent call last)\\n') and 1 or 1)")
    r = oa.run_member("stub", "stub.py", [], (1,), tmp_path)
    assert r["status"] == oa.STATUS_CRASH, r


def test_argparse_style_bad_flag_is_HARNESS(tmp_path):
    """A typo in a member's argv tail exits 2 with no traceback."""
    _stub(tmp_path, "import argparse;argparse.ArgumentParser().parse_args()")
    r = oa.run_member("stub", "stub.py", ["--nope"], (1,), tmp_path)
    assert r["status"] == oa.STATUS_UNUSABLE, r


def test_unusable_forces_the_harness_aggregate_not_the_findings_one(tmp_path):
    """`unusable` must outrank `findings`: a detector that could not run is not a
    detector that found nothing."""
    (tmp_path / "a.py").write_text("import sys; sys.exit(1)")   # a real finding
    (tmp_path / "b.py").write_text("import sys; sys.exit(2)")   # could not check
    res = oa.audit(ops=tmp_path, members=(("a", "a.py", [], (1,)),
                                          ("b", "b.py", [], (1,))))
    assert res["counts"][oa.STATUS_FINDINGS] == 1
    assert res["counts"][oa.STATUS_UNUSABLE] == 1
    assert res["aggregate_exit"] == oa.EXIT_HARNESS


def test_every_member_declares_a_finding_contract():
    """A member added without one would silently inherit the old fail-open."""
    for name, _rel, _tail, finding_exits in oa.MEMBERS:
        assert finding_exits, f"{name} declares no finding exits"
        assert 0 not in finding_exits, f"{name} lists 0 as a finding exit"


def _returned_ints(src: str) -> set[int]:
    """Every integer the member's module-level `main()` can return, from its own AST.

    These six between them use plain constants (`return 2`), module-level names
    (`return EXIT_FINDINGS`), and conditionals (`return 1 if bad else 0`), so all
    three forms are resolved.
    """
    tree = ast.parse(src)
    consts: dict[str, int] = {}
    for node in tree.body:                       # `EXIT_OK, EXIT_FINDINGS = 0, 1`
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            names = tgt.elts if isinstance(tgt, ast.Tuple) else [tgt]
            vals = (node.value.elts if isinstance(node.value, ast.Tuple)
                    else [node.value])
            if len(names) != len(vals):
                continue
            for n, v in zip(names, vals):
                if (isinstance(n, ast.Name) and isinstance(v, ast.Constant)
                        and isinstance(v.value, int)):
                    consts[n.id] = v.value

    main = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    assert main is not None, "member has no module-level main()"

    def resolve(node) -> set[int]:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return {node.value}
        if isinstance(node, ast.Name):
            return {consts[node.id]} if node.id in consts else set()
        if isinstance(node, ast.IfExp):          # `return 1 if findings else 0`
            return resolve(node.body) | resolve(node.orelse)
        return set()

    out: set[int] = set()
    for node in ast.walk(main):
        if isinstance(node, ast.Return) and node.value is not None:
            out |= resolve(node.value)
    return out


@pytest.mark.parametrize("name,rel,finding_exits",
                         [(n, r, f) for n, r, _t, f in oa.MEMBERS])
def test_declared_contract_matches_each_member_source(name, rel, finding_exits):
    """The per-member citations in MEMBERS are RE-DERIVED here, never trusted.

    "Codes measured, not assumed" is itself only an assertion once the member changes
    underneath the comment. This reads the member's own AST, so a detector that
    switches its findings code fails HERE instead of silently having its real findings
    reclassified as `unusable` (or worse, the reverse).
    """
    returned = _returned_ints((REPO / "ops" / rel).read_text(encoding="utf-8"))
    assert returned, f"{name}: derived no exit codes from {rel} — parser is vacuous"
    assert 0 in returned, f"{name}: {rel} main() has no clean exit"
    missing = set(finding_exits) - returned
    assert not missing, (
        f"{name}: declares {sorted(missing)} as a finding exit but {rel} main() can "
        f"only return {sorted(returned)} — the cited contract has rotted")


def test_the_cited_contract_is_the_one_in_force():
    """Provenance pin. Widening a contract must show up as a diff here: adding 2 to
    any member would turn its "could not check" back into a finding and reintroduce
    #650 for that member alone, which no other test would catch."""
    assert {n: f for n, _r, _t, f in oa.MEMBERS} == {
        "silent-refusal": (1,), "blind-notifiers": (1,),
        "undelivered-alerts": (1,), "import-resolution": (1,),
        "umbrella-script-shadow": (1,), "launchd-liveness": (1,),
    }
