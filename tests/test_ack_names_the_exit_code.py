"""An ack acknowledges a DIAGNOSIS, not a job label.

Keyed on the label alone, a job that starts failing a completely different way stays
silenced by a note written about the old failure. Measured on the live ledger
`[VERIFIED — launchctl list, 2026-07-31]`: `com.renquant.shadow-ab-daily` is acked for
an "epoch-3 frozen manifest vs 07-16/17 pin deployments" diagnosis and now exits **3**,
not 1.

REBASED ONTO THE SCHEMA THAT LANDED FIRST. This branch proposed a scalar
`acked_exit_code`; `main` meanwhile shipped `ack_covers_exit` with a LIST,
`acked_exit_codes`, which is strictly better -- a job can legitimately have two acked
failure modes. The list wins and this file tests it. What `main` did NOT do, and what
survives from this branch, is the default: an ack with no declared codes covered EVERY
nonzero code, which is the same shape this programme keeps finding -- a check that
passes because its subject is absent. Nine of the ten committed rows had no declared
code.

So: every row now declares the code its DIAGNOSIS is about (not the code observed
today, which would silence whatever is happening now by construction), and an ack with
no declaration is UNUSABLE rather than universal. Because all ten declare one, the flip
re-dispositions nothing by itself -- it is a floor under the next ack written without
one. The one row whose declared code disagrees with its observed exit is
`shadow-ab-daily`, and it going loud IS the finding.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# Same two-path insert the existing sentinel suite uses: the module imports
# `sentinel_receipt` as a sibling, so loading it by file path alone fails.
sys.path.insert(0, str(REPO / "ops"))
sys.path.insert(0, str(REPO / "ops" / "renquant104"))

import rq104_degradation_sentinel as sent  # noqa: E402

LEDGER = REPO / "ops" / "renquant104" / "sentinel_acks.json"
FRESH = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _acks(monkeypatch, table):
    monkeypatch.setattr(sent, "load_acks", lambda: table)


def _launchctl(monkeypatch, label, status):
    monkeypatch.setattr(sent, "parse_launchctl_failures",
                        lambda *a, **k: [f"{label} (last exit {status})"])
    monkeypatch.setattr(sent.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0})())


# --- the inverse parser must stay in step with the formatter --------------------

@pytest.mark.parametrize("status", [1, 2, 3, 78, -1])
def test_the_code_parser_inverts_the_formatter(status):
    """The pair has to stay in step: `parse_launchctl_failures` writes the line and
    `parse_exit_code` reads it back. If either drifts, every ack silently becomes
    unusable and the ledger stops working -- loudly, but for the wrong reason."""
    formatted = sent.parse_launchctl_failures(f"-\t{status}\tcom.renquant.x")[0]
    assert sent.parse_exit_code(formatted) == status


def test_an_unreadable_code_is_None_not_a_default():
    """A default would let an unreadable code coincidentally equal an ack's."""
    assert sent.parse_exit_code("com.renquant.x (no code here)") is None
    assert sent.parse_exit_code("") is None


# --- the guard itself -----------------------------------------------------------

ACK = {"acked_at": FRESH, "clears_when": "some condition",
       "reason": "a specific diagnosis"}


def test_a_matching_code_still_suppresses(monkeypatch):
    """Anti-vacuity control. If this fails, the ledger has stopped working entirely
    and the tests below would pass for the wrong reason."""
    _acks(monkeypatch, {"com.renquant.x": {**ACK, "acked_exit_codes": [1]}})
    _launchctl(monkeypatch, "com.renquant.x", 1)
    alarm, infos = sent.check_launchd_exits(today=dt.date.today())
    assert alarm is None, alarm
    assert any("acked nonzero exit" in i for i in infos)


def test_a_DIFFERENT_code_stops_suppressing(monkeypatch):
    """THE DEFECT. shadow-ab-daily, exactly: acked for one failure, exits with
    another, silenced regardless."""
    _acks(monkeypatch, {"com.renquant.x": {**ACK, "acked_exit_codes": [1]}})
    _launchctl(monkeypatch, "com.renquant.x", 3)
    alarm, _ = sent.check_launchd_exits(today=dt.date.today())
    assert alarm is not None
    assert "ACK DOES NOT COVER THIS EXIT" in alarm
    assert "job exits 3" in alarm and "ack is for [1]" in alarm


def test_TWO_acked_codes_both_suppress_and_a_third_does_not(monkeypatch):
    """Why the list beat the scalar this branch proposed: a job can legitimately have
    two acked failure modes, and forcing one row per mode would have split a single
    diagnosis across two entries."""
    for code in (1, 2):
        _acks(monkeypatch, {"com.renquant.x": {**ACK, "acked_exit_codes": [1, 2]}})
        _launchctl(monkeypatch, "com.renquant.x", code)
        alarm, _ = sent.check_launchd_exits(today=dt.date.today())
        assert alarm is None, (code, alarm)
    _acks(monkeypatch, {"com.renquant.x": {**ACK, "acked_exit_codes": [1, 2]}})
    _launchctl(monkeypatch, "com.renquant.x", 3)
    alarm, _ = sent.check_launchd_exits(today=dt.date.today())
    assert alarm is not None and "ack is for [1, 2]" in alarm


def test_an_ack_with_no_recorded_code_stops_suppressing(monkeypatch):
    """A provenance gap is never a pass. An ack that does not say WHICH failure it
    acknowledges cannot be checked against the one happening now."""
    _acks(monkeypatch, {"com.renquant.x": dict(ACK)})     # no acked_exit_codes
    _launchctl(monkeypatch, "com.renquant.x", 1)
    alarm, _ = sent.check_launchd_exits(today=dt.date.today())
    assert alarm is not None
    assert "ACK UNUSABLE" in alarm
    assert "no acked_exit_codes" in alarm


def test_the_original_reason_is_quoted_in_every_refusal(monkeypatch):
    """The reader must be able to decide between fixing and re-acking without
    opening the ledger -- the same contract the expiry branch already honours."""
    for code, marker in ((3, "ACK DOES NOT COVER THIS EXIT"), (None, "ACK UNUSABLE")):
        ack = dict(ACK) if code is None else {**ACK, "acked_exit_codes": [1]}
        _acks(monkeypatch, {"com.renquant.x": ack})
        _launchctl(monkeypatch, "com.renquant.x", 3 if code else 1)
        alarm, _ = sent.check_launchd_exits(today=dt.date.today())
        assert marker in alarm and "a specific diagnosis" in alarm


def test_the_code_check_runs_BEFORE_the_expiry_check(monkeypatch):
    """A stale ack for a DIFFERENT failure should report the mismatch, not merely
    that it aged out -- the two send the reader to different places."""
    old = {"acked_at": "2020-01-01", "clears_when": "x", "reason": "r",
           "acked_exit_codes": [1]}
    _acks(monkeypatch, {"com.renquant.x": old})
    _launchctl(monkeypatch, "com.renquant.x", 3)
    alarm, _ = sent.check_launchd_exits(today=dt.date.today())
    assert "ACK DOES NOT COVER THIS EXIT" in alarm
    assert "ACK EXPIRED" not in alarm


# --- the committed ledger must satisfy its own new contract ---------------------

def test_every_committed_ack_records_the_code_it_acknowledges():
    d = json.loads(LEDGER.read_text())
    acks = d.get("acks", d)
    missing = [k for k, v in acks.items()
               if isinstance(v, dict) and "acked_exit_codes" not in v]
    assert missing == [], missing
    assert len(acks) >= 10, acks          # anti-vacuity: an empty ledger passes trivially


def test_no_committed_ack_claims_a_zero_exit():
    """exit 0 is not a failure, so an ack for it can only be dead weight that
    silences a future real one. Four such acks were removed on 2026-07-30."""
    d = json.loads(LEDGER.read_text())
    acks = d.get("acks", d)
    assert [k for k, v in acks.items()
            if isinstance(v, dict) and 0 in (v.get("acked_exit_codes") or [])] == []
