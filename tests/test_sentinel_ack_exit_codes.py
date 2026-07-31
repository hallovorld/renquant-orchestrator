"""GOAL-1 #622 — an ack must not cover an exit code nobody dispositioned.

The self-referential row's text has said, verbatim, *"this ack now covers ONLY
exit 1"* since `EXIT_INTERNAL = 3` was introduced so a crash would stop looking
like an alarm. **Nothing in the code read that sentence.** `check_launchd_exits`
matched on job name alone, so a crash at exit 3 was demoted to INFO by the very
row that claimed not to hide it.

The load-bearing tests are the controls: the nine rows WITHOUT the key must keep
behaving exactly as they were reviewed, and an unreadable exit code must not pass.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "ops", "renquant104", "rq104_degradation_sentinel.py")
LEDGER = os.path.join(ROOT, "ops", "renquant104", "sentinel_acks.json")
SELF_ROW = "com.renquant.rq104-degradation-sentinel"


def _load():
    # the sentinel imports its siblings by bare name (`sentinel_receipt`)
    d = os.path.dirname(MOD)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("rq104_sentinel_ackcodes", MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load()


def test_parse_exit_code_reads_the_launchctl_shape():
    assert S.parse_exit_code("com.renquant.x (last exit 3)") == 3
    assert S.parse_exit_code("com.renquant.x (last exit -9)") == -9
    assert S.parse_exit_code("com.renquant.x") is None


def test_an_unreadable_exit_code_is_NOT_covered():
    """Not-parseable is not a pass. An ack that cannot be matched to a code is an
    ack of something unknown."""
    assert S.ack_covers_exit({"acked_exit_codes": [1]}, "com.renquant.x") is False


def test_an_ack_without_the_key_still_covers_everything():
    """CONTROL. Nine of ten rows have no `acked_exit_codes`; this fix must not
    silently re-disposition any of them."""
    for code in (1, 2, 3, 127, -9):
        assert S.ack_covers_exit({}, f"j (last exit {code})") is True


def test_the_self_row_covers_exit_1_and_NOT_exit_3():
    """THE defect: exit 3 exists so a crash stops looking like an alarm, and the
    ack was silencing it anyway."""
    ack = json.load(open(LEDGER, encoding="utf-8"))[SELF_ROW]
    assert ack["acked_exit_codes"] == [1]
    assert S.ack_covers_exit(ack, f"{SELF_ROW} (last exit 1)") is True
    assert S.ack_covers_exit(ack, f"{SELF_ROW} (last exit 3)") is False
    assert S.ack_covers_exit(ack, f"{SELF_ROW} (last exit 3)") is not None


def test_the_rows_prose_and_its_machinery_now_agree():
    """Anti-rot. The row asserts a restriction; this pins that something enforces
    it. Deleting the key makes the sentence false again and fails here."""
    ack = json.load(open(LEDGER, encoding="utf-8"))[SELF_ROW]
    assert "covers ONLY exit 1" in ack["reason"]
    assert ack.get("acked_exit_codes") == [1]


def test_a_crashed_sentinel_reaches_the_LOUD_list(monkeypatch):
    """End to end through check_launchd_exits: exit 3 must alarm, not INFO."""
    monkeypatch.setattr(
        S, "parse_launchctl_failures", lambda *_a, **_k: [f"{SELF_ROW} (last exit 3)"])

    class _R:
        stdout = ""
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: _R())
    monkeypatch.setattr(S, "load_acks", lambda *a, **k: {
        SELF_ROW: {"acked_at": "2999-01-01", "acked_exit_codes": [1],
                   "reason": "r", "clears_when": "c"}})
    alarm, infos = S.check_launchd_exits()
    assert alarm is not None and "ACK DOES NOT COVER THIS EXIT" in alarm
    assert infos == []


def test_an_alarming_sentinel_is_still_quiet(monkeypatch):
    """The mirror. Without this, 'exit 3 is loud' could be achieved by making
    everything loud, which would be a worse mechanism than the one it replaced."""
    monkeypatch.setattr(
        S, "parse_launchctl_failures", lambda *_a, **_k: [f"{SELF_ROW} (last exit 1)"])

    class _R:
        stdout = ""
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: _R())
    monkeypatch.setattr(S, "load_acks", lambda *a, **k: {
        SELF_ROW: {"acked_at": "2999-01-01", "acked_exit_codes": [1],
                   "reason": "r", "clears_when": "c"}})
    alarm, infos = S.check_launchd_exits()
    assert alarm is None
    assert len(infos) == 1 and "acked nonzero exit" in infos[0]
