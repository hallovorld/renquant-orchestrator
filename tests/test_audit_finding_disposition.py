"""The audit fleet reports 10 of 10 every run, so a new finding cannot stand out.

Measured 2026-08-01 on origin/main: `ops_audit` runs 10 detectors, `ok=0 findings=10`, and
has NO ack/known/suppress concept — the only `ack` in the file is the *name* of the
`ack-ledger` member. Its plist is not installed either, so it has never run on schedule.

This layer gives a run a quiet state. The fingerprint is the whole problem and both failure
modes are real:

  * fingerprint the raw text -> every ack dies when a count ticks, so the ledger is
    write-only;
  * normalise the digits away -> `4` and `40` fingerprint identically and an escalation is
    silently covered.

So digits are normalised AND recorded: a moved magnitude reports ACKED_BUT_CHANGED.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS))

import audit_finding_disposition as D  # noqa: E402

TODAY = dt.date(2026, 8, 1)
TXT = "job 'weekly-retrain-patchtst' has not acted on 4 non-acting runs"


def _ledger(text=TXT, member="silent-refusal", **over):
    ack = {"acked_at": "2026-07-30", "reason": "known: gate refuses correctly",
           "expires_at": "2026-09-01", "numbers_when_acked": D.numbers(text)}
    ack.update(over)
    return {D.fingerprint(member, text): ack}


# ----------------------------------------------------- the two fingerprint traps --
def test_a_TICKING_COUNT_does_not_break_the_ack():
    """Trap 1: a raw-text fingerprint makes every ack die on the next run."""
    later = TXT.replace("on 4 non-acting", "on 5 non-acting")
    assert D.fingerprint("silent-refusal", TXT) == D.fingerprint("silent-refusal", later)


def test_but_a_MOVED_MAGNITUDE_is_reported_not_covered():
    """Trap 2: normalising digits away would silently cover an escalation 4 -> 40."""
    worse = TXT.replace("on 4 non-acting", "on 40 non-acting")
    r = D.classify("silent-refusal", worse, _ledger(), TODAY)
    assert r["state"] == D.CHANGED
    assert r["numbers_when_acked"] == ["4"] and r["numbers"] == ["40"]
    assert "not a magnitude" in r["why"]


def test_an_unchanged_finding_is_ACKED_and_quiet():
    r = D.classify("silent-refusal", TXT, _ledger(), TODAY)
    assert r["state"] == D.ACKED and r["reason"]


def test_a_DIFFERENT_SUBJECT_is_NEW_not_covered_by_the_ack():
    other = TXT.replace("weekly-retrain-patchtst", "weekly-wf-promote")
    assert D.classify("silent-refusal", other, _ledger(), TODAY)["state"] == D.NEW


def test_the_SAME_text_from_a_DIFFERENT_MEMBER_is_NEW():
    """The member is part of the identity — two detectors saying the same words are two
    findings."""
    assert D.classify("launchd-liveness", TXT, _ledger(), TODAY)["state"] == D.NEW


# ---------------------------------------------------------------- expiry + noise --
def test_an_EXPIRED_ack_goes_loud_again():
    r = D.classify("silent-refusal", TXT, _ledger(expires_at="2026-07-31"), TODAY)
    assert r["state"] == D.EXPIRED


def test_expiry_uses_the_SENTINELS_rule_not_a_local_copy():
    """`ack_expiry` is imported. A second implementation would drift exactly when it
    mattered."""
    src = (OPS / "audit_finding_disposition.py").read_text()
    assert "from rq104_degradation_sentinel import ack_expiry" in src
    assert "def ack_expiry" not in src


def test_TIMESTAMPS_and_HOME_PATHS_do_not_break_an_ack():
    """Both drift without the situation changing; both are normalised for the fingerprint
    only."""
    a = "scan at 2026-08-01T05:07:59 found /Users/renhao/x missing"
    b = "scan at 2026-08-02T06:11:02 found /Users/someone/x missing"
    assert D.fingerprint("m", a) == D.fingerprint("m", b)


def test_normalisation_is_for_the_FINGERPRINT_only_the_text_is_kept_verbatim():
    r = D.classify("m", TXT, {}, TODAY)
    assert r["text"] == TXT and "<N>" not in r["text"]


# --------------------------------------------------------------------- plumbing --
def test_nothing_is_suppressed_SILENTLY(tmp_path, capsys):
    f = tmp_path / "f.json"
    f.write_text(json.dumps([{"member": "silent-refusal", "text": TXT}]))
    lg = tmp_path / "l.json"
    lg.write_text(json.dumps(_ledger()))
    assert D.main(["--findings", str(f), "--ledger", str(lg), "--as-of", "2026-08-01"]) == 0
    out = capsys.readouterr().out
    assert "ACKED" in out and "weekly-retrain-patchtst" in out
    assert "acked because" in out


def test_this_tool_NEVER_writes_the_ledger():
    """Acking is a human decision and a reviewed diff."""
    src = (OPS / "audit_finding_disposition.py").read_text()
    assert "write_text" not in src and '"w"' not in src


def test_a_MISSING_ledger_makes_everything_NEW_not_everything_acked(tmp_path):
    f = tmp_path / "f.json"
    f.write_text(json.dumps([{"member": "m", "text": "x"}]))
    assert D.main(["--findings", str(f), "--ledger", str(tmp_path / "nope.json")]) == 1


def test_a_MALFORMED_ledger_is_a_usage_error_not_an_empty_one(tmp_path):
    f = tmp_path / "f.json"
    f.write_text(json.dumps([]))
    lg = tmp_path / "l.json"
    lg.write_text("[]")
    assert D.main(["--findings", str(f), "--ledger", str(lg)]) == 2
