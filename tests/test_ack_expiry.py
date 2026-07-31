"""An ack must stop suppressing. CLAUDE.md says the returning alarm IS the reminder.

The ledger implemented `if ack:` — unconditional, permanent suppression — while
`clears_when` sat as prose no code read. That is the guard-that-passes-forever shape,
inside the mechanism whose whole job is to decide what gets surfaced.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS / "renquant104"))
_SPEC = importlib.util.spec_from_file_location(
    "rq104_degradation_sentinel", OPS / "renquant104" / "rq104_degradation_sentinel.py")
sent = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sent)
sys.path.pop(0)

D = dt.date.fromisoformat


# --- ack_expiry: the earliest signal wins ------------------------------------

def test_acked_at_plus_the_window_is_the_default():
    e, why = sent.ack_expiry({"acked_at": "2026-07-17"})
    assert e == D("2026-07-17") + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS)
    assert "acked_at" in why


def test_a_date_embedded_in_clears_when_is_honoured():
    """Several real rows already carry one, e.g. "(2026-07-20)". It was a real expiry
    sitting where nothing could act on it."""
    e, why = sent.ack_expiry({
        "acked_at": "2026-07-17",
        "clears_when": "next NYSE session's 13:55 wrapper run (2026-07-20)"})
    assert e == D("2026-07-20")
    assert "clears_when" in why


def test_an_explicit_expires_at_is_honoured():
    e, why = sent.ack_expiry({"acked_at": "2026-07-17", "expires_at": "2026-07-18"})
    assert e == D("2026-07-18") and why == "expires_at"


def test_the_EARLIEST_signal_wins_so_a_misparse_can_only_expire_sooner():
    """Direction matters: expiring early is noisy and safe; expiring late is silent
    and is the failure this fix exists to remove."""
    e, _ = sent.ack_expiry({
        "acked_at": "2026-07-17", "expires_at": "2026-12-31",
        "clears_when": "review 2026-07-19 then again 2026-08-30"})
    assert e == D("2026-07-19")


def test_a_missing_acked_at_means_ALREADY_EXPIRED():
    """Absence must not buy permanent suppression."""
    e, why = sent.ack_expiry({"reason": "x"})
    assert e is None and "missing or unparseable" in why


@pytest.mark.parametrize("bad", [None, "", "soon", "17-07-2026", 20260717, []])
def test_an_unparseable_acked_at_means_ALREADY_EXPIRED(bad):
    e, _ = sent.ack_expiry({"acked_at": bad})
    assert e is None


def test_a_non_date_that_looks_like_one_does_not_crash():
    e, _ = sent.ack_expiry({"acked_at": "2026-07-17",
                            "clears_when": "2026-13-45 is not a date"})
    assert e == D("2026-07-17") + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS)


# --- the real ledger, on a fixed date ----------------------------------------

def test_the_committed_ledger_has_exactly_three_expired_acks_on_2026_07_30():
    """Positive control against a hand measurement. Issue #622 counted FOUR acks past
    their date by hand and the mechanism reproduced it independently.

    COUNT CHANGED 4 -> 3 on 2026-07-31, and deliberately, not to make a test pass:
    `com.renquant.rq105-batch-scores-export` was re-dispositioned with a MEASURED
    current diagnosis (the export refuses because no contract-clean full-buy run
    exists — a 104 buy-side block, not a 105 defect) and now carries an explicit
    `expires_at: 2026-08-14`. So it is no longer among the expired.

    The property this test exists for is unchanged and still asserted below: every
    remaining expired ack is killed by a date in its OWN clears_when, not by the
    blanket age window. If a future edit drops that count to 0 by renewing acks
    rather than fixing jobs, THAT is what this test should be read against."""
    ledger = json.loads((OPS / "renquant104" / "sentinel_acks.json").read_text())
    on = D("2026-07-30")
    expired = {k: sent.ack_expiry(v) for k, v in ledger.items()}
    dead = {k: (e, w) for k, (e, w) in expired.items() if e is None or e <= on}
    assert len(dead) == 3, sorted(dead)
    assert "com.renquant.rq105-batch-scores-export" not in dead
    for k, (e, w) in dead.items():
        assert "clears_when" in w, f"{k} expired by {w}, expected its own clears_when"
        assert e == D("2026-07-20"), k


def test_the_re_dispositioned_ack_expires_by_its_OWN_explicit_date():
    """An `expires_at` must win over the 14-day age window — otherwise a considered
    review date silently inherits a blanket one."""
    ledger = json.loads((OPS / "renquant104" / "sentinel_acks.json").read_text())
    row = ledger["com.renquant.rq105-batch-scores-export"]
    e, w = sent.ack_expiry(row)
    assert e == D("2026-08-14")
    assert w == "expires_at", w
    assert row["acked_at"] == "2026-07-31"


def test_the_re_dispositioned_ack_names_a_FALSIFIABLE_clearing_condition():
    """An ack whose clears_when cannot be observed to happen is permanent in
    disguise. This one names a merge, a pin, and an observable session outcome —
    and says what to do if the fix lands and the job still fails."""
    row = json.loads((OPS / "renquant104" / "sentinel_acks.json").read_text())[
        "com.renquant.rq105-batch-scores-export"]
    cw = row["clears_when"]
    assert "strategy-104#73" in cw
    assert "full-buy-funnel run" in cw
    assert "must be removed, not renewed" in cw


# --- check_launchd_exits: expired acks go LOUD, valid ones stay INFO ---------

def _wire(monkeypatch, acks, failures):
    monkeypatch.setattr(sent, "load_acks", lambda: acks)
    monkeypatch.setattr(sent, "parse_launchctl_failures", lambda out: failures)
    monkeypatch.setattr(sent.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "x"})())


def test_an_expired_ack_stops_suppressing_and_quotes_its_own_text(monkeypatch):
    _wire(monkeypatch,
          {"com.renquant.j": {"acked_at": "2026-07-01", "reason": "known flake",
                              "clears_when": "next run (2026-07-05)"}},
          ["com.renquant.j"])
    alarm, infos = sent.check_launchd_exits(today=D("2026-07-30"))
    assert alarm is not None and "ACK EXPIRED" in alarm
    assert "known flake" in alarm and "2026-07-05" in alarm
    assert "expired 25d ago" in alarm
    assert infos == []


def test_a_valid_ack_still_suppresses_and_shows_its_expiry(monkeypatch):
    """Negative case: the alarm above comes from expiry, not from the ack being
    ignored altogether."""
    _wire(monkeypatch,
          {"com.renquant.j": {"acked_at": "2026-07-29", "reason": "r",
                              "clears_when": "c"}},
          ["com.renquant.j"])
    alarm, infos = sent.check_launchd_exits(today=D("2026-07-30"))
    assert alarm is None
    assert len(infos) == 1 and "ack expires 2026-08-12" in infos[0]


def test_a_job_with_no_ack_is_loud_as_before(monkeypatch):
    _wire(monkeypatch, {}, ["com.renquant.j"])
    alarm, infos = sent.check_launchd_exits(today=D("2026-07-30"))
    assert alarm and "com.renquant.j" in alarm and infos == []


def test_an_ack_with_no_acked_at_never_suppresses(monkeypatch):
    _wire(monkeypatch,
          {"com.renquant.j": {"reason": "no date recorded"}}, ["com.renquant.j"])
    alarm, _ = sent.check_launchd_exits(today=D("2026-07-30"))
    assert alarm and "never valid" in alarm


def test_no_failures_means_no_alarm_and_no_ack_lookup(monkeypatch):
    _wire(monkeypatch, {}, [])
    assert sent.check_launchd_exits(today=D("2026-07-30")) == (None, [])
