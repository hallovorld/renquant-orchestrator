"""One scheduled surface for detectors that were merged and never run.

Measured 2026-07-30: `ops/` carried 24 runnable tools, 7 were referenced by a
launchd job, and the 17 unscheduled included GOAL-5's AC5 silent-refusal sentinel —
absent from the manifest, absent from `launchctl list`, with no `*refusal*` log ever
written. The ledger said "AC5 = #619 merged", true about the merge and silent about
the deployment.
"""

from __future__ import annotations

import ast
import datetime as dt
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
        "silent-refusal": (1,), "blind-notifiers": (1,), "ack-ledger": (1,),
        "undelivered-alerts": (1,), "import-resolution": (1,),
        "umbrella-script-shadow": (1,), "launchd-liveness": (1,),
        # Added 2026-08-01; each cited to its return line in the MEMBERS comment block.
        "gate-stamp-parity": (1,), "booster-identity": (1,),
        "bundle-producer-keys": (1,),
        # Added 2026-08-01 (#723): shadow_lane_preflight.py `return 1` on any failed
        # precondition; 3 = skipped preconditions -> UNUSABLE by design.
        "shadow-lane-preflight": (1,),
        # Added 2026-08-06. Both are `return 1 if <finding> else 0` in main(), and
        # both `return 2` on a refusal (prod config missing / unparseable) so a
        # refusal lands on HARNESS rather than reading as "the fleet is clean".
        # 2 is deliberately NOT declared as a finding exit for either.
        "shadow-lane-control": (1,),
        "shadow-leg-independence": (1,),
    }


def test_the_2026_08_01_members_are_ARGUMENT_FREE_or_carry_only_portable_args():
    """A member may not take a machine-specific path.

    Baking an absolute path into MEMBERS is the "tests that measure the operator's disk"
    failure, and it is why two detectors merged on 2026-07-31 are recorded in
    `UNSCHEDULABLE_YET` instead of being added with a hardcoded root.
    """
    added = {"gate-stamp-parity", "booster-identity", "bundle-producer-keys"}
    for name, _rel, tail, _f in oa.MEMBERS:
        if name not in added:
            continue
        for arg in tail:
            assert not arg.startswith("/"), (name, arg)
            assert "renhao" not in arg and "Users" not in arg, (name, arg)


def test_the_detectors_that_CANNOT_join_are_recorded_not_silently_omitted():
    """'The audit covers the detectors' must not be readable off a list that quietly
    excludes two of them."""
    assert set(oa.UNSCHEDULABLE_YET) == {
        "renquant104/wf_corpus_coverage.py",
        "strategy_config_primary_parity.py",
    }
    listed = {rel for _n, rel, _t, _f in oa.MEMBERS}
    assert not (set(oa.UNSCHEDULABLE_YET) & listed), "a blocker cannot also be a member"


# ---------------------------------------------------------------------------
# ack-ledger membership, 2026-08-01
# ---------------------------------------------------------------------------
def test_ack_ledger_is_a_member_at_all():
    """It was merged, working, and invoked by nothing but its own test file — the exact
    dark-detector shape the 2026-07-31 sweep was run for, and which it missed."""
    assert "ack-ledger" in {n for n, _r, _a, _f in oa.MEMBERS}


def test_ack_ledger_has_no_write_path_at_all():
    """`test_no_member_writes` rejected this member on the first attempt: it carried a
    `--json-out` flag with no caller whose `open(..., "w")` was its only write.
    Documenting an exception would have weakened a guard that was working, so the flag
    was removed instead. This pins that it stays removed.

    Checked on the AST, not on the text. The first version grepped for `"w"` and matched
    the COMMENT explaining the removal — a check failing on its own documentation.
    """
    import ast
    tree = ast.parse(
        (REPO / "ops" / "renquant104" / "ack_ledger_audit.py").read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        assert name not in ("write_text", "write_bytes"), name
        if name == "open":
            mode = node.args[1] if len(node.args) > 1 else None
            mode = mode.value if isinstance(mode, ast.Constant) else ""
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            assert "w" not in str(mode) and "a" not in str(mode), f"open mode {mode!r}"


def test_ack_ledger_harness_code_is_NOT_declared_a_finding():
    """It returns 3 on an unexpected exception. Declaring 3 a finding would turn a crash
    into a verdict — the failure ops_audit exists to prevent."""
    finding = next(f for n, _r, _a, f in oa.MEMBERS if n == "ack-ledger")
    assert finding == (1,) and 3 not in finding


# --------------------------------------------------------------------------------
# Dispositioning, end to end through `audit()` itself.
#
# `ops/audit_finding_disposition.py` shipped as a standalone tool and nothing called
# it, so every scheduled run still reported the same raw findings and the ledger was
# dead code [codex on #722]. These tests exercise the four outcomes in an ACTUAL
# ops_audit report, not in the classifier in isolation.
# --------------------------------------------------------------------------------

def _emits(line, rc=1):
    """A detector that prints one line and exits `rc`."""
    return f"print({line!r})\nraise SystemExit({rc})\n"


def _ledger_for(tmp_path, rows):
    """Build a ledger keyed by the REAL fingerprints, computed with the shipped
    function rather than hardcoded digests — a pinned hash would pass while the
    fingerprint definition drifted underneath it."""
    import audit_finding_disposition as afd
    led = {afd.fingerprint(member, text): ack for member, text, ack in rows}
    p = tmp_path / "acks.json"
    p.write_text(json.dumps(led, indent=2))
    return p


def test_the_four_dispositions_appear_in_a_real_ops_audit_report(tmp_path):
    texts = {
        "alpha": "alpha has 3 stale rows",
        "bravo": "bravo has 5 stale rows",
        "charlie": "charlie has 9 stale rows",
        "delta": "delta has 7 stale rows",
    }
    members = [_member(tmp_path, n, _emits(t)) for n, t in texts.items()]
    ledger = _ledger_for(tmp_path, [
        # bravo: acked, unexpired, numbers unmoved -> the only quiet one
        # NOTE `acked_at` is MANDATORY, not decoration: `ack_expiry` returns None —
        # which classify() treats as already expired — when it is missing, however far
        # away `expires_at` is. Absence must not buy permanent suppression. My first
        # draft of this ledger omitted it and the "quiet" cases came back EXPIRED.
        ("bravo", texts["bravo"],
         {"reason": "known thin panel", "acked_at": "2026-07-28",
          "numbers_when_acked": ["5"]}),
        # charlie: acked, unexpired, but the magnitude moved 4 -> 9
        ("charlie", texts["charlie"],
         {"reason": "was 4", "acked_at": "2026-07-28",
          "numbers_when_acked": ["4"]}),
        # delta: acked, numbers unmoved, but the ack ran out
        # acked_at + ACK_MAX_AGE_DAYS is already in the past on the as-of date.
        ("delta", texts["delta"],
         {"reason": "temporary", "acked_at": "2026-06-01",
          "numbers_when_acked": ["7"]}),
        # alpha: deliberately absent from the ledger -> NEW
    ])
    before = ledger.read_bytes()

    res = oa.audit(ops=tmp_path, members=members, ledger_path=ledger,
                   today=dt.date(2026, 8, 1))
    by = {r["member"]: r for r in res["results"]}

    assert by["alpha"]["disposition"] == "NEW"
    assert by["bravo"]["disposition"] == "ACKED"
    assert by["charlie"]["disposition"] == "ACKED_BUT_CHANGED"
    assert by["delta"]["disposition"] == "ACK_EXPIRED"

    # Only the acked-and-unchanged one goes quiet.
    assert by["bravo"]["status"] == oa.STATUS_INFO
    for n in ("alpha", "charlie", "delta"):
        assert by[n]["status"] == oa.STATUS_FINDINGS, n

    assert res["counts"][oa.STATUS_INFO] == 1
    assert res["counts"][oa.STATUS_FINDINGS] == 3
    # Three undispositioned findings remain, so the job still exits nonzero.
    assert res["aggregate_exit"] == oa.EXIT_FINDINGS
    # An INFO row keeps its reason so the run can be read without the ledger open.
    assert "known thin panel" in by["bravo"]["ack_reason"]
    # READ-ONLY: dispositioning classifies, it never acks.
    assert ledger.read_bytes() == before


def test_an_all_acked_fleet_is_actually_QUIET(tmp_path):
    """The point of the change: a fully dispositioned run exits 0.

    Without this, `info` would be cosmetic — the job would keep exiting 1 and the
    scheduled surface would be exactly as unreadable as before."""
    t = "solo has 2 stale rows"
    members = [_member(tmp_path, "solo", _emits(t))]
    ledger = _ledger_for(tmp_path, [
        ("solo", t, {"reason": "accepted", "acked_at": "2026-07-28",
                     "numbers_when_acked": ["2"]})])
    res = oa.audit(ops=tmp_path, members=members, ledger_path=ledger,
                   today=dt.date(2026, 8, 1))
    assert res["counts"][oa.STATUS_FINDINGS] == 0
    assert res["counts"][oa.STATUS_INFO] == 1
    assert res["aggregate_exit"] == oa.EXIT_OK


def test_an_ack_can_NEVER_quiet_a_crash_or_an_unusable_exit(tmp_path):
    """The failure this must not introduce.

    A quieting layer that could reach the harness statuses would let a BROKEN detector
    report as an acknowledged one — the crash-vs-alarm confusion the aggregator exists
    to prevent, re-entered through the back door. Both rows below are acked by
    fingerprint and must stay loud anyway.
    """
    crash_line = "boom has 1 problem"
    members = [
        # dies with a traceback on stderr
        _member(tmp_path, "boom",
                f"import sys\nprint({crash_line!r})\nraise ValueError('x')\n"),
        # exits 2, which is NOT in its declared finding contract -> unusable
        _member(tmp_path, "murky", _emits("murky has 1 problem", rc=2)),
    ]
    ledger = _ledger_for(tmp_path, [
        ("boom", crash_line, {"reason": "acked", "acked_at": "2026-07-28"}),
        ("murky", "murky has 1 problem",
         {"reason": "acked", "acked_at": "2026-07-28"}),
    ])
    res = oa.audit(ops=tmp_path, members=members, ledger_path=ledger,
                   today=dt.date(2026, 8, 1))
    by = {r["member"]: r for r in res["results"]}
    assert by["boom"]["status"] == oa.STATUS_CRASH
    assert by["murky"]["status"] == oa.STATUS_UNUSABLE
    # Not merely still-loud: never even dispositioned.
    assert "disposition" not in by["boom"]
    assert "disposition" not in by["murky"]
    assert res["aggregate_exit"] == oa.EXIT_HARNESS


def test_a_missing_or_malformed_ledger_leaves_every_finding_loud(tmp_path):
    members = [_member(tmp_path, "solo", _emits("solo has 2 stale rows"))]
    absent = tmp_path / "nope.json"
    bad = tmp_path / "bad.json"
    bad.write_text("[not an object]")
    for led in (absent, bad):
        res = oa.audit(ops=tmp_path, members=members, ledger_path=led,
                       today=dt.date(2026, 8, 1))
        assert res["counts"][oa.STATUS_FINDINGS] == 1, led.name
        assert res["counts"][oa.STATUS_INFO] == 0, led.name
        assert res["aggregate_exit"] == oa.EXIT_FINDINGS, led.name
