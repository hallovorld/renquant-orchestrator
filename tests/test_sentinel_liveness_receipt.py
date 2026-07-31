"""A crashed sentinel and an alarming sentinel must stop being the same thing.

Issue #622 defect 2: the sentinel exits 1 on alarms (by design, and the ack ledger
acks it on that basis) while an uncaught exception ALSO exits 1. Both were acked, so
the failure of the failure-detector was undetectable. These tests pin the two
mechanisms that separate them, and — more importantly — pin that each mechanism can
actually FAIL, since a liveness check that cannot report death is decoration.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"


def _load(name: str, relpath: str):
    sys.path.insert(0, str(OPS / "renquant104"))
    try:
        spec = importlib.util.spec_from_file_location(name, OPS / relpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.pop(0)


receipt_mod = _load("sentinel_receipt", "renquant104/sentinel_receipt.py")


# --- exit codes: the collision is gone ---------------------------------------

def test_alarm_exit_is_still_1():
    """Renumbering this would silently change what every existing ack means."""
    assert receipt_mod.EXIT_ALARMS == 1
    assert receipt_mod.EXIT_OK == 0


def test_internal_error_has_its_own_code_distinct_from_the_alarm_code():
    assert receipt_mod.EXIT_INTERNAL != receipt_mod.EXIT_ALARMS
    assert receipt_mod.EXIT_INTERNAL != receipt_mod.EXIT_OK


# --- the receipt writer must never be able to break its host ------------------

def test_write_receipt_returns_an_error_string_instead_of_raising(tmp_path):
    """A liveness mechanism that can kill the process it instruments is worse
    than none. Point it at a path that cannot be created."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file")
    err = receipt_mod.write_receipt({"outcome": "ok"}, path=blocker / "sub" / "r.json")
    assert isinstance(err, str) and "could not write" in err


def test_write_receipt_succeeds_and_is_readable(tmp_path):
    """Negative case for the above: the error is caused by the blocked path."""
    target = tmp_path / "deep" / "r.json"
    assert receipt_mod.write_receipt({"outcome": "ok", "written_at": "x"}, path=target) is None
    data, err = receipt_mod.read_receipt(target)
    assert err is None and data["outcome"] == "ok"
    assert data["schema_version"] == 1


def test_no_tmp_file_is_left_behind(tmp_path):
    """Write-then-rename must not leave a partial file a reader could pick up."""
    target = tmp_path / "r.json"
    receipt_mod.write_receipt({"outcome": "ok"}, path=target)
    assert [p.name for p in tmp_path.iterdir()] == ["r.json"]


# --- missing vs malformed are different, and must stay different -------------

def test_absent_receipt_is_not_reported_as_malformed(tmp_path):
    data, err = receipt_mod.read_receipt(tmp_path / "nope.json")
    assert data is None and err is None, "absent must not masquerade as unreadable"


def test_malformed_receipt_reports_an_error(tmp_path):
    bad = tmp_path / "r.json"
    bad.write_text("{truncated")
    data, err = receipt_mod.read_receipt(bad)
    assert data is None and err is not None


def test_non_object_receipt_is_rejected(tmp_path):
    bad = tmp_path / "r.json"
    bad.write_text("[1, 2]")
    data, err = receipt_mod.read_receipt(bad)
    assert data is None and "not an object" in err


# --- the drift scan's check: every branch, including the quiet ones ----------

drift = _load("run_surface_drift_check", "run_surface_drift_check.py")


def _point_at(monkeypatch, tmp_path, payload: dict | None, *, raw: str | None = None):
    target = tmp_path / "receipt.json"
    if raw is not None:
        target.write_text(raw)
    elif payload is not None:
        # schema_version is injected so the older fixtures keep testing what they
        # were written to test; a fixture that passes it EXPLICITLY (including a
        # wrong value) still wins, which is what the version tests rely on.
        target.write_text(json.dumps({"schema_version": 1, **payload}))
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(target))
    return target


def _fresh_iso(offset_s: float = 0.0) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(
        time.time() - offset_s, dt.timezone.utc).isoformat(timespec="seconds")


def test_absent_receipt_is_LOUD(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, None)
    loud, info = drift.check_sentinel_receipt()
    assert len(loud) == 1 and "absent" in loud[0]
    assert info == []


def test_stale_receipt_is_LOUD(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path,
              {"written_at": _fresh_iso(9 * 24 * 3600), "outcome": "ok"})
    loud, _ = drift.check_sentinel_receipt()
    assert len(loud) == 1 and "stopped firing" in loud[0]


def test_a_long_weekend_does_NOT_alarm(monkeypatch, tmp_path):
    """The bound is 4 days precisely so a Friday run plus a Monday holiday is
    quiet. If this starts failing the sentinel will cry wolf every long weekend."""
    _point_at(monkeypatch, tmp_path,
              {"written_at": _fresh_iso(3.5 * 24 * 3600), "outcome": "ok"})
    loud, info = drift.check_sentinel_receipt()
    assert loud == [] and info == []


def test_internal_error_is_LOUD_and_named_as_a_crash(monkeypatch, tmp_path):
    """THE REGRESSION. This case was invisible behind the acked exit 1."""
    _point_at(monkeypatch, tmp_path, {
        "written_at": _fresh_iso(60), "outcome": "internal_error",
        "error": "KeyError: 'runs'", "exit_code": 3})
    loud, info = drift.check_sentinel_receipt()
    assert len(loud) == 1
    assert "crash, not its alarm signal" in loud[0]
    assert "KeyError" in loud[0]


def test_alarming_sentinel_is_INFO_not_a_second_alarm(monkeypatch, tmp_path):
    """It delivers its own alert. Double-alarming trains the reader to ignore both."""
    _point_at(monkeypatch, tmp_path, {
        "written_at": _fresh_iso(60), "outcome": "alarms", "alarm_count": 3,
        "exit_code": 1})
    loud, info = drift.check_sentinel_receipt()
    assert loud == []
    assert len(info) == 1 and "3 alarm(s)" in info[0]


def test_healthy_receipt_is_silent(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, {"written_at": _fresh_iso(60), "outcome": "ok"})
    assert drift.check_sentinel_receipt() == ([], [])


def test_not_a_session_day_is_silent(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path,
              {"written_at": _fresh_iso(60), "outcome": "not_session_day"})
    assert drift.check_sentinel_receipt() == ([], [])


def test_unparseable_timestamp_is_LOUD_not_silently_skipped(monkeypatch, tmp_path):
    """A missing or junk field must not make the check pass — that is the
    guard-passes-on-absent-input shape this repo keeps paying for."""
    _point_at(monkeypatch, tmp_path, {"written_at": "not-a-date", "outcome": "ok"})
    loud, _ = drift.check_sentinel_receipt()
    assert len(loud) == 1 and "unparseable" in loud[0]


def test_receipt_with_no_written_at_is_LOUD(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, {"outcome": "ok"})
    loud, _ = drift.check_sentinel_receipt()
    assert len(loud) == 1


def test_malformed_receipt_is_LOUD(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, None, raw="{nope")
    loud, _ = drift.check_sentinel_receipt()
    assert len(loud) == 1 and "unreadable" in loud[0]


# --- the ack ledger's self-referential row must now point somewhere ----------

def test_the_sentinel_ack_row_references_the_receipt():
    """#622 quoted this row as the reason the sentinel's own failure was
    un-diagnosable. If it still says only 'exit 1 is the alarm signal' with no
    pointer to a liveness surface, the ledger is still a dead end."""
    ledger = json.loads((OPS / "renquant104" / "sentinel_acks.json").read_text())
    row = ledger.get("com.renquant.rq104-degradation-sentinel")
    assert row is not None
    blob = json.dumps(row).lower()
    assert "receipt" in blob, "the self-referential ack must name the liveness surface"
    assert "exit 3" in blob or "internal" in blob, (
        "the ack must state that a crash is now a DIFFERENT exit code, or a reader "
        "still cannot tell which of the two an exit 1 was")


# --- THE core regression: the wrapper's crash path ---------------------------
# Everything above tests the receipt and the reader. This tests the thing #622 was
# actually about: that an exception inside the sentinel no longer exits 1.

def _load_sentinel():
    return _load("rq104_degradation_sentinel",
                 "renquant104/rq104_degradation_sentinel.py")


def test_an_exception_inside_the_sentinel_exits_3_not_1(monkeypatch, tmp_path, capsys):
    """THE REGRESSION. Before this change an uncaught exception exited 1, which the
    ack ledger acks as the alarm signal, so the crash was invisible."""
    sent = _load_sentinel()
    target = tmp_path / "r.json"
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(target))

    def boom(argv, receipt):
        raise KeyError("runs")

    monkeypatch.setattr(sent, "_run", boom)
    code = sent.main([])
    assert code == 3, "a crash must not share the alarm exit code"
    assert code != receipt_mod.EXIT_ALARMS

    data, err = receipt_mod.read_receipt(target)
    assert err is None and data["outcome"] == "internal_error"
    assert "KeyError" in data["error"]
    assert "FAILED INTERNALLY" in capsys.readouterr().err


def test_a_normal_alarm_run_still_exits_1_and_records_it(monkeypatch, tmp_path):
    """Negative case: the new code is reached only by the crash path. A run that
    legitimately has alarms must keep exiting 1 or every existing ack changes
    meaning."""
    sent = _load_sentinel()
    target = tmp_path / "r.json"
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(target))

    def alarming(argv, receipt):
        receipt["outcome"] = "alarms"
        receipt["alarm_count"] = 2
        return receipt_mod.EXIT_ALARMS

    monkeypatch.setattr(sent, "_run", alarming)
    assert sent.main([]) == 1
    data, _ = receipt_mod.read_receipt(target)
    assert data["outcome"] == "alarms" and data["alarm_count"] == 2
    assert data["exit_code"] == 1


def test_a_receipt_that_cannot_be_written_does_not_change_the_verdict(
        monkeypatch, tmp_path, capsys):
    """The verdict must survive an unwritable receipt. Otherwise the liveness
    mechanism can convert a healthy run into a failure."""
    sent = _load_sentinel()
    blocker = tmp_path / "blocked"
    blocker.write_text("file, not a dir")
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(blocker / "sub" / "r.json"))
    monkeypatch.setattr(sent, "_run", lambda argv, receipt: receipt_mod.EXIT_OK)
    assert sent.main([]) == 0
    assert "could not write sentinel receipt" in capsys.readouterr().err


def test_systemexit_propagates_untouched(monkeypatch, tmp_path):
    """argparse --help and explicit exits must not be swallowed into exit 3."""
    sent = _load_sentinel()
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(tmp_path / "r.json"))

    def bail(argv, receipt):
        raise SystemExit(7)

    monkeypatch.setattr(sent, "_run", bail)
    with pytest.raises(SystemExit) as e:
        sent.main([])
    assert e.value.code == 7


# --- codex BLOCKER on #625: a malformed receipt must not read as clean ---------
# The first version of check_sentinel_receipt treated every fresh receipt that was
# not internal_error or alarms as healthy. So a receipt with a missing or misspelled
# `outcome` SUPPRESSED the liveness failure the mechanism exists to surface --- the
# guard-passes-on-absent-input shape, inside the guard I wrote to fix an instance of
# it. These pin that it cannot come back.

def test_a_receipt_with_NO_outcome_is_LOUD(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path,
              {"schema_version": 1, "written_at": _fresh_iso(60)})
    loud, info = drift.check_sentinel_receipt()
    assert len(loud) == 1
    assert "liveness NOT established" in loud[0]
    assert info == []


def test_an_unknown_outcome_is_LOUD(monkeypatch, tmp_path):
    """A typo or a value from a future version. Either way liveness is unestablished."""
    for bad in ("okay", "OK", "alarm", "healthy", "", None, 0):
        _point_at(monkeypatch, tmp_path,
                  {"schema_version": 1, "written_at": _fresh_iso(60), "outcome": bad})
        loud, info = drift.check_sentinel_receipt()
        assert len(loud) == 1, f"outcome={bad!r} produced {loud!r}"
        assert "liveness NOT established" in loud[0]
        assert info == []


def test_every_known_outcome_is_accepted(monkeypatch, tmp_path):
    """Negative case: the refusals above come from the value, not from the check
    having become unconditionally loud."""
    for good in sorted(receipt_mod.KNOWN_OUTCOMES):
        _point_at(monkeypatch, tmp_path, {
            "schema_version": 1, "written_at": _fresh_iso(60), "outcome": good,
            "alarm_count": 1, "error": "x"})
        loud, info = drift.check_sentinel_receipt()
        if good in ("ok", "not_session_day"):
            assert (loud, info) == ([], []), f"{good} should be silent, got {loud}{info}"
        elif good == "alarms":
            assert loud == [] and len(info) == 1, good
        else:
            assert len(loud) == 1 and "crash" in loud[0], good


def test_an_unrecognised_schema_version_is_LOUD(monkeypatch, tmp_path):
    """An unrecognised schema is exactly where field names may have moved, so
    guessing is the one thing the reader must not do."""
    for bad in (2, 0, "1", None):
        _point_at(monkeypatch, tmp_path, {
            "schema_version": bad, "written_at": _fresh_iso(60), "outcome": "ok"})
        loud, _ = drift.check_sentinel_receipt()
        assert len(loud) == 1, f"schema_version={bad!r}"
        assert "unrecognised receipt" in loud[0]


def test_the_writer_stamps_the_version_the_reader_requires(tmp_path):
    """If these two ever disagree the check alarms forever. Pin them together."""
    target = tmp_path / "r.json"
    receipt_mod.write_receipt({"outcome": "ok", "written_at": "x"}, path=target)
    data, _ = receipt_mod.read_receipt(target)
    assert data["schema_version"] == receipt_mod.RECEIPT_SCHEMA_VERSION


# --- a test run must not write the REAL receipt --------------------------------
# This defect was introduced by the first version of this change and caught by
# running the drift check on this machine: the pre-existing sentinel suite calls
# main() at five sites, so every full-suite run stamped a receipt into
# ~/.renquant/ --- writing to the user's home as a side effect AND making a dead
# sentinel look alive, which is the failure the mechanism exists to surface.

def test_default_path_is_refused_under_pytest(monkeypatch):
    monkeypatch.delenv(receipt_mod.RECEIPT_ENV, raising=False)
    err = receipt_mod.write_receipt({"outcome": "ok"})
    assert err and "refusing to write the default receipt path under pytest" in err


def test_an_explicit_path_is_still_honoured_under_pytest(tmp_path, monkeypatch):
    """Negative case: the refusal is about the DEFAULT path, not about writing."""
    monkeypatch.delenv(receipt_mod.RECEIPT_ENV, raising=False)
    target = tmp_path / "r.json"
    assert receipt_mod.write_receipt({"outcome": "ok"}, path=target) is None
    assert target.exists()


def test_the_env_override_is_still_honoured_under_pytest(tmp_path, monkeypatch):
    target = tmp_path / "env.json"
    monkeypatch.setenv(receipt_mod.RECEIPT_ENV, str(target))
    assert receipt_mod.write_receipt({"outcome": "ok"}) is None
    assert target.exists()


def test_the_sentinel_main_does_not_touch_the_real_receipt(monkeypatch, capsys):
    """End to end: calling main() the way the existing suite does must leave the
    real path alone and say so, not silently write it."""
    monkeypatch.delenv(receipt_mod.RECEIPT_ENV, raising=False)
    sent = _load_sentinel()
    monkeypatch.setattr(sent, "_run", lambda argv, receipt: receipt_mod.EXIT_OK)
    assert sent.main([]) == 0
    assert "refusing to write the default receipt path" in capsys.readouterr().err
