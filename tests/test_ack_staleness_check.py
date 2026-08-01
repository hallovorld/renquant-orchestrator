"""Has a suppression outlived its own stated clearing condition?

The subject is a ledger that SUPPRESSES alarms, so every failure mode here is one where a
suppression keeps working when it should have been reviewed. The tests are mostly about
the two ways this check could be wrong in opposite directions: missing an overdue ack, and
manufacturing an alarm out of a deliberately open-ended one.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "ack_staleness_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("asc", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


A = _load()
TODAY = dt.date(2026, 7, 31)


def _ledger(tmp_path, rows, name="acks.json"):
    p = tmp_path / name
    p.write_text(json.dumps(rows), encoding="utf-8")
    return str(p)


# --- overdue detection ------------------------------------------------------

def test_a_PAST_clearing_date_is_OVERDUE(tmp_path):
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2026-07-17",
        "clears_when": "next NYSE session (2026-07-20)"}}), TODAY)
    assert r["n_overdue"] == 1
    assert r["acks"][0]["days_since_earliest_past_date"] == 11


def test_a_FUTURE_clearing_date_is_not_overdue(tmp_path):
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2026-07-30", "clears_when": "next run (2026-08-15)"}}), TODAY)
    assert r["n_overdue"] == 0 and r["acks"][0]["kind"] == "date_bearing"


def test_TODAY_is_not_yet_past(tmp_path):
    """An off-by-one here alarms a day early on every dated ack in the ledger."""
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2026-07-17", "clears_when": "runs 2026-07-31"}}), TODAY)
    assert r["n_overdue"] == 0


def test_the_EARLIEST_past_date_drives_the_age(tmp_path):
    """A condition naming two dates is as overdue as its oldest one."""
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2026-07-01",
        "clears_when": "either 2026-07-05 or 2026-07-25"}}), TODAY)
    assert r["acks"][0]["days_since_earliest_past_date"] == 26


# --- the opposite error: manufacturing an alarm -----------------------------

def test_an_EVENT_ONLY_condition_is_NOT_overdue(tmp_path):
    """Counting an open-ended condition as stale would manufacture an alarm out of a
    deliberate design choice — one ledger row literally says 'open-ended; gate is
    correct'."""
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2026-01-01",
        "clears_when": "a staged model passes the WF gate"}}), TODAY)
    assert r["n_overdue"] == 0 and r["acks"][0]["kind"] == "event_only"
    assert r["n_event_only"] == 1


def test_a_VERY_OLD_event_only_ack_is_still_not_overdue(tmp_path):
    """Age alone must not promote an event condition to overdue: this check measures the
    CONDITION, not how long it has been waiting."""
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "2020-01-01", "clears_when": "next VIX-anomaly trigger"}}), TODAY)
    assert r["n_overdue"] == 0 and r["acks"][0]["age_days"] > 2000


# --- ledger integrity -------------------------------------------------------

def test_an_ack_with_NO_clearing_condition_is_MALFORMED(tmp_path):
    """The worst row possible: a suppression that can never be shown to have outlived
    anything. It is a defect, not a date-less event condition."""
    r = A.audit(_ledger(tmp_path, {"j": {"acked_at": "2026-07-17"}}), TODAY)
    assert r["malformed"] and "never be shown" in r["malformed"][0]["why"]
    assert r["n_acks"] == 0


def test_an_EMPTY_clearing_condition_is_malformed_too(tmp_path):
    r = A.audit(_ledger(tmp_path, {"j": {"acked_at": "x", "clears_when": "   "}}), TODAY)
    assert r["malformed"]


def test_a_NON_OBJECT_entry_is_malformed_not_skipped(tmp_path):
    r = A.audit(_ledger(tmp_path, {"j": "acked"}), TODAY)
    assert r["malformed"] and "not an object" in r["malformed"][0]["why"]


def test_an_UNPARSEABLE_acked_at_does_not_crash(tmp_path):
    r = A.audit(_ledger(tmp_path, {"j": {
        "acked_at": "whenever", "clears_when": "next run (2026-07-20)"}}), TODAY)
    assert r["acks"][0]["age_days"] is None and r["n_overdue"] == 1


def test_a_MISSING_ledger_exits_2_not_0(tmp_path, capsys):
    """'No ledger' must never read as 'no stale suppressions'."""
    assert A.main(["--ledger", str(tmp_path / "gone.json")]) == 2


def test_a_NON_OBJECT_ledger_root_is_unreadable(tmp_path):
    p = tmp_path / "l.json"
    p.write_text("[]", encoding="utf-8")
    assert A.audit(str(p), TODAY)["status"] == "ledger_unreadable"


# --- CLI --------------------------------------------------------------------

def test_main_EXITS_NONZERO_on_an_overdue_ack(tmp_path, capsys):
    lg = _ledger(tmp_path, {"j": {"acked_at": "2026-07-17",
                                  "clears_when": "run (2026-07-20)"}})
    assert A.main(["--ledger", lg, "--as-of", "2026-07-31"]) == 1
    assert "OVERDUE" in capsys.readouterr().out


def test_ANTI_VACUITY_a_clean_ledger_exits_zero(tmp_path, capsys):
    lg = _ledger(tmp_path, {"j": {"acked_at": "2026-07-30",
                                  "clears_when": "a staged model passes the gate"}})
    assert A.main(["--ledger", lg, "--as-of", "2026-07-31"]) == 0
    assert "no ack has a clearing date in the past" in capsys.readouterr().out


def test_the_report_REFUSES_to_say_the_condition_was_MET(tmp_path, capsys):
    """'review if still failing 2026-07-20+' makes the date a TRIGGER, not a verdict.
    Reading OVERDUE as 'the fault is fixed, remove the ack' inverts the meaning."""
    lg = _ledger(tmp_path, {"j": {"acked_at": "2026-07-17",
                                  "clears_when": "review if still failing 2026-07-20+"}})
    A.main(["--ledger", lg, "--as-of", "2026-07-31"])
    out = capsys.readouterr().out
    assert "does NOT mean the condition was met" in out
    assert "never edits the ledger" in out


def test_the_REAL_ledger_reproduces_the_documented_counts():
    """The docstring's numbers must stay derivable, or they become assertions with a
    citation attached."""
    real = ROOT / "ops" / "renquant104" / "sentinel_acks.json"
    if not real.exists():
        import pytest
        pytest.skip("ledger not present")
    r = A.audit(str(real), TODAY)
    assert r["n_acks"] == 10
    assert r["n_date_bearing"] == 3 and r["n_event_only"] == 7
    assert sorted(r["overdue_jobs"]) == [
        "com.renquant.daily104", "com.renquant.shadow-ab-daily",
        "com.renquant.weekly-retrain-patchtst"]
    assert all(a["days_since_earliest_past_date"] == 11
               for a in r["acks"] if a["overdue"])
