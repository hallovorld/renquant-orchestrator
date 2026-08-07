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
    # Field-wise, not dict-equality: the row grows (it gained `newest_log` when
    # the launchctl-staleness fix landed) and an exact-equality assertion turns
    # every additive change into a false failure while testing nothing extra.
    assert len(rows) == 1
    r = rows[0]
    assert r["job"] == "some-new-job"
    assert r["code"] == 7
    assert r["kind"] == "unknown"
    assert r["detail"] == "no documented meaning for this code"


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


# ── launchctl staleness: the code is not the newest run ────────────────────

def test_every_launchd_row_carries_a_newest_log_field(monkeypatch):
    """Even when None. A row without the field lets a reader assume the exit
    code describes the newest run, which is the defect this closes."""
    monkeypatch.setattr(inbox.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "-\t1\tcom.renquant.some-job\n"})())
    assert "newest_log" in inbox.read_launchd_exits()[0]




def test_every_mapped_location_is_real_on_this_machine():
    """`_LOG_LOCATION` is a claim about the filesystem, read out of each job's
    wrapper and confirmed against a file. If a directory disappears the map is
    stale and the inbox silently reports `None` — i.e. "undiscoverable" — for a
    job that does have logs, which is the failure this map exists to remove.

    Off the operator machine (CI: a clean checkout has no `logs/` tree at all)
    there is nothing to verify — skip loudly rather than fail on absent state
    that was never this map's claim to begin with."""
    if not (inbox.RQ / "logs").is_dir():
        pytest.skip("no logs/ tree here — cannot verify the operator-local "
                    "log-directory map (expected off the operator machine, e.g. CI)")
    missing = [f"{job}: logs/{d}" for job, (d, _) in inbox._LOG_LOCATION.items()
               if not (inbox.RQ / "logs" / d).is_dir()]
    assert not missing, "mapped log directories that no longer exist:\n  " + "\n  ".join(missing)


def test_the_flat_basename_form_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    monkeypatch.setitem(inbox._LOG_LOCATION, "x-job", ("shared", "thing"))
    d = tmp_path / "logs" / "shared"; d.mkdir(parents=True)
    (d / "thing_2026-08-01.log").write_text("x")
    (d / "thing_2026-08-06.log").write_text("x")
    (d / "other_2026-08-09.log").write_text("x")   # different basename, ignored
    assert inbox._newest_log_date("x-job") == "2026-08-06"


def test_an_unmapped_job_falls_back_once_then_gives_up(tmp_path, monkeypatch):
    """One convention is tried because it does hold sometimes; a SECOND guess
    would be inventing a pattern, which is how the earlier false verdicts
    happened."""
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    d = tmp_path / "logs" / "some_job"; d.mkdir(parents=True)
    (d / "2026-08-05.log").write_text("x")
    assert inbox._newest_log_date("some-job") == "2026-08-05"
    assert inbox._newest_log_date("no-such-job-at-all") is None

def test_newest_log_reads_the_per_job_directory_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    d = tmp_path / "logs" / "weekly_wf_promote"
    d.mkdir(parents=True)
    for name in ("2026-08-01.log", "2026-08-04.log", "notes.txt"):
        (d / name).write_text("x")
    assert inbox._newest_log_date("weekly-wf-promote") == "2026-08-04"


def test_newest_log_reads_the_flat_directory_layout(tmp_path, monkeypatch):
    # logs/rq104/silent_refusal_YYYY-MM-DD.log — the second measured layout.
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    d = tmp_path / "logs" / "rq104"
    d.mkdir(parents=True)
    (d / "silent_refusal_2026-08-03.log").write_text("x")
    (d / "silent_refusal_2026-08-06.log").write_text("x")
    assert inbox._newest_log_date("rq104-silent-refusal") == "2026-08-06"


def test_undiscoverable_is_None_not_a_guess(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    assert inbox._newest_log_date("no-such-job") is None


def test_non_dated_files_are_not_mistaken_for_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "RQ", tmp_path)
    d = tmp_path / "logs" / "weekly_wf_promote"
    d.mkdir(parents=True)
    (d / "manual_20260601-225243.log").write_text("x")
    (d / "final_test_20260608-082722.log").write_text("x")
    assert inbox._newest_log_date("weekly-wf-promote") is None


def test_render_states_the_launchctl_limitation():
    """The limitation must be VISIBLE, not just handled: a reader who does not
    know that `launchctl` only tracks launchd-started runs will read a stale
    code as current — which is what happened to me."""
    box = {"incidents": [], "audit_findings": [],
           "launchd_unknown": [{"job": "a", "code": 1, "detail": "?",
                                "newest_log": "2026-08-04"}],
           "launchd_designed": [], "launchd_designed_actionable": []}
    text = render(box)
    assert "[newest log 2026-08-04]" in text
    assert "last run LAUNCHD started" in text
    assert "not `no logs`" in text
