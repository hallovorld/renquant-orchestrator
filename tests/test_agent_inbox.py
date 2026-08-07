"""Tests for the agent inbox.

Two of these carry the module's own weight rather than checking plumbing:

* ``test_designed_exit_codes_are_still_true_of_their_sources`` re-greps every
  file ``DESIGNED_EXIT_CODES`` makes a claim about. That map says "exit 4 from
  rq105-shadow-serving means NOT WIRED" — a claim about a shell script in
  another directory, exactly the kind of assertion that rots silently. Asserted
  in the module, MEASURED here.

* ``test_an_unlisted_code_is_unknown_not_assumed_fine`` pins the default
  direction. The whole point of the launchd split is that a code nobody
  documented is work; a map that fails open would restate the defect it exists
  to fix.

Context (measured 2026-08-06): a daily alert listed ~14 jobs "with nonzero last
exit" and read as fourteen failures. Most were jobs REPORTING — `EXIT_NOT_WIRED`,
`EXIT_ALARM`, "drift found", "findings present". Meanwhile `alert_incidents`
held 17 unacked rows, the oldest from 2026-06-22, that had reached neither the
operator nor the agent.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ops.agent_inbox import (
    DESIGNED_EXIT_CODES,
    REPO,
    collect,
    read_audit_findings,
    read_incidents,
    render,
)
import ops.agent_inbox as inbox


# ── the map is a claim about other files ───────────────────────────────────

def test_designed_exit_codes_are_still_true_of_their_sources():
    missing = []
    for job, codes in DESIGNED_EXIT_CODES.items():
        for code, (_label, src, probe, _actionable) in codes.items():
            path = REPO / src
            if not path.exists():
                missing.append(f"{job}/{code}: {src} does not exist")
                continue
            if probe not in path.read_text(errors="replace"):
                missing.append(f"{job}/{code}: {src} no longer contains {probe!r}")
    assert not missing, (
        "DESIGNED_EXIT_CODES has drifted from the sources it cites:\n  "
        + "\n  ".join(missing)
    )


def test_every_designed_entry_names_a_source_and_a_probe():
    for job, codes in DESIGNED_EXIT_CODES.items():
        for code, entry in codes.items():
            assert len(entry) == 4, (
                f"{job}/{code}: expected (label, source, probe, actionable)")
            label, src, probe, actionable = entry
            assert label and src and probe, f"{job}/{code}: blank field"
            assert isinstance(actionable, bool), (
                f"{job}/{code}: actionable must be a bool")


# ── the default direction ──────────────────────────────────────────────────

def test_an_unlisted_code_is_unknown_not_assumed_fine(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t7\tcom.renquant.some-new-job\n"})())
    rows = inbox.read_launchd_exits()
    assert rows == [{"job": "some-new-job", "code": 7, "kind": "unknown",
                     "detail": "no documented meaning for this code"}]


def test_a_listed_code_is_designed(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t4\tcom.renquant.rq105-shadow-serving\n"})())
    rows = inbox.read_launchd_exits()
    assert rows[0]["kind"] == "designed"
    assert "not wired" in rows[0]["detail"]


def test_the_same_job_with_an_undocumented_code_is_still_unknown(monkeypatch):
    """Designation is per (job, code), not per job — `rq105-shadow-serving`
    exiting 9 is not covered by its documented 4."""
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t9\tcom.renquant.rq105-shadow-serving\n"})())
    assert inbox.read_launchd_exits()[0]["kind"] == "unknown"


def test_zero_exits_are_not_reported(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "1234\t0\tcom.renquant.daily104\n"})())
    assert inbox.read_launchd_exits() == []


def test_non_renquant_jobs_are_ignored(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t1\tcom.apple.something\n"})())
    assert inbox.read_launchd_exits() == []


# ── designed ≠ non-actionable (Codex P1, orch#887) ─────────────────────────
# "Known exit semantics are not the same as non-actionable." A genuine BREACH
# or CRITICAL/WARN reported through a documented exit code is still real work,
# even though the code itself is not a mystery.

def test_model_freshness_breach_is_designed_and_actionable(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t3\tcom.renquant.rq104-model-freshness\n"})())
    rows = inbox.read_launchd_exits()
    assert rows[0]["kind"] == "designed"
    assert rows[0]["actionable"] is True


def test_risk_budget_critical_is_designed_and_actionable(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t1\tcom.renquant.rq104-risk-budget\n"})())
    rows = inbox.read_launchd_exits()
    assert rows[0]["kind"] == "designed"
    assert rows[0]["actionable"] is True


def test_risk_budget_warn_is_designed_and_actionable(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t2\tcom.renquant.rq104-risk-budget\n"})())
    rows = inbox.read_launchd_exits()
    assert rows[0]["kind"] == "designed"
    assert rows[0]["actionable"] is True


def test_not_wired_yet_is_designed_but_not_actionable(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t4\tcom.renquant.rq105-shadow-serving\n"})())
    rows = inbox.read_launchd_exits()
    assert rows[0]["kind"] == "designed"
    assert rows[0]["actionable"] is False


def test_collect_splits_designed_into_actionable_and_informational(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": (
            "-\t3\tcom.renquant.rq104-model-freshness\n"
            "-\t4\tcom.renquant.rq105-shadow-serving\n")})())
    monkeypatch.setattr(inbox, "read_incidents", lambda: [])
    monkeypatch.setattr(inbox, "read_audit_findings", lambda: [])
    box = inbox.collect()
    assert [r["job"] for r in box["launchd_designed_actionable"]] == [
        "rq104-model-freshness"]
    assert [r["job"] for r in box["launchd_designed"]] == ["rq105-shadow-serving"]


def test_designed_actionable_exit_still_pages(monkeypatch):
    """A designed exit that IS a genuine BREACH must page — 'designed' means
    the code's meaning is known, not that nothing is wrong (Codex P1)."""
    monkeypatch.setattr(inbox, "collect", lambda: {
        "incidents": [], "audit_findings": [], "launchd_unknown": [],
        "launchd_designed": [],
        "launchd_designed_actionable": [
            {"job": "rq104-model-freshness", "code": 3,
             "detail": "genuine BREACH"}],
    })
    assert inbox.main([]) == 1


# ── ops-audit schema: measured, and loud when it moves ─────────────────────

def _fake_audit(payload, monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": json.dumps(payload)})())


def test_reads_the_results_list(monkeypatch):
    _fake_audit({"members": 12, "results": [
        {"member": "silent-refusal", "status": "findings", "exit_code": 1,
         "detail": "job X has not acted"},
        {"member": "import-resolution", "status": "ok", "exit_code": 0,
         "detail": "fine"},
    ]}, monkeypatch)
    out = read_audit_findings()
    assert [r["name"] for r in out] == ["silent-refusal"]


def test_info_is_dispositioned_not_new_work(monkeypatch):
    # `info` means the ack ledger already ruled on it — someone's decision, not
    # a fresh item. Surfacing it would re-page on every acked finding.
    _fake_audit({"results": [{"member": "gate-stamp-parity", "status": "info",
                              "exit_code": 1, "detail": "ACKED"}]}, monkeypatch)
    assert read_audit_findings() == []


def test_a_changed_schema_is_reported_not_swallowed(monkeypatch):
    """`members` was an int and a first cut crashed on it. A silent [] here
    would make a broken aggregator look like a clean system."""
    _fake_audit({"members": 12, "counts": {}}, monkeypatch)
    out = read_audit_findings()
    assert len(out) == 1
    assert "schema changed" in out[0]["name"]
    assert "members" in out[0]["summary"]


def test_unparseable_audit_output_does_not_raise(monkeypatch):
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "not json"})())
    out = read_audit_findings()
    assert out and "unreadable" in out[0]["name"]


# ── the incident ledger ────────────────────────────────────────────────────

def _ledger(tmp_path, rows):
    db = tmp_path / "runs.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE alert_incidents (audit TEXT, scope TEXT, "
                "cause_hash TEXT, first_seen TEXT, last_seen TEXT, state TEXT, "
                "acked INT, notifications INT)")
    con.executemany("INSERT INTO alert_incidents VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit(); con.close()
    return db


def test_acked_rows_are_excluded(tmp_path):
    db = _ledger(tmp_path, [
        ("score_drift", "panel", "CRITICAL:psi~5.9", "2026-08-06", "2026-08-06", "WARN", 0, 1),
        ("score_drift", "panel", "CRITICAL:psi~1.1", "2026-08-01", "2026-08-01", "WARN", 1, 1),
    ])
    rows = read_incidents(db)
    assert len(rows) == 1
    assert rows[0]["cause_hash"] == "CRITICAL:psi~5.9"


def test_resolved_but_unacked_rows_are_excluded(tmp_path):
    """The source ledger persists `state` independently of `acked`
    (RenQuant `persistence.py`'s `alert_incidents` comment: `state TEXT --
    WARN | CRITICAL | RESOLVED`) — a resolved incident nobody ever acked
    must not render as active work forever (Codex MED, orch#887)."""
    db = _ledger(tmp_path, [
        ("score_drift", "panel", "CRITICAL:psi~1.1", "2026-08-01", "2026-08-01",
         "RESOLVED", 0, 1),
    ])
    assert read_incidents(db) == []


def test_a_missing_db_is_empty_not_an_error(tmp_path):
    assert read_incidents(tmp_path / "nope.db") == []


def test_an_unreadable_ledger_is_surfaced(tmp_path):
    bad = tmp_path / "runs.db"
    bad.write_text("i am not sqlite")
    rows = read_incidents(bad)
    assert rows and "unreadable" in rows[0]["audit"]


# ── rendering + exit contract ──────────────────────────────────────────────

def test_designed_exits_are_rendered_separately_from_work():
    box = {"incidents": [], "audit_findings": [],
           "launchd_unknown": [{"job": "a", "code": 2, "detail": "?"}],
           "launchd_designed": [{"job": "b", "code": 4, "detail": "by design"}]}
    text = render(box)
    assert "NEEDING EXPLANATION (1)" in text
    assert "BY DESIGN (1)" in text
    assert "not work" in text


def test_exit_1_only_when_there_is_real_work(monkeypatch):
    monkeypatch.setattr(inbox, "collect", lambda: {
        "incidents": [], "audit_findings": [], "launchd_unknown": [],
        "launchd_designed": [{"job": "b", "code": 4, "detail": "by design"}]})
    assert inbox.main([]) == 0, (
        "a run whose only nonzero exits are DESIGNED must not page — "
        "reproducing that conflation here would be the joke writing itself")


@pytest.mark.parametrize("key", ["incidents", "audit_findings", "launchd_unknown"])
def test_any_real_work_pages(monkeypatch, key):
    box = {"incidents": [], "audit_findings": [], "launchd_unknown": [],
           "launchd_designed": []}
    box[key] = [{"job": "x", "code": 1, "detail": "d", "name": "n",
                 "status": "findings", "summary": "s", "state": "WARN"}]
    monkeypatch.setattr(inbox, "collect", lambda: box)
    assert inbox.main([]) == 1


def test_module_never_writes(monkeypatch):
    """Read-only is a contract, not an intention: the inbox must never ack,
    mutate a job, or touch the ledger."""
    src = Path(inbox.__file__).read_text()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "launchctl unload",
                      "launchctl stop", "open(", "write_text"):
        assert forbidden not in src, f"inbox must stay read-only: found {forbidden!r}"
