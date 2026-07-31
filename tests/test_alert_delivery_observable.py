"""GOAL-5 — an alarm nobody received must not look like one that was received.

Two measured gaps, 2026-07-31:

  * `liveness_common.alert()` returned `None`. `renquant_common.notify.send` is
    deliberately built never to raise into a monitor -- it swallows the failure and
    returns `False` -- so that bool was the ONLY in-process evidence of delivery,
    and `alert` discarded it. **0 of 12 call sites** could observe delivery.
  * `undelivered_alert_scan` matched only `ntfy send failed`. `send` returns False
    from TWO places: an exception (that text) and `RENQUANT_NO_NOTIFY` (which logs
    `[ntfy suppressed]` at INFO). A fleet muted by one environment variable would
    drop every alarm while the scan reported clean.
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    path = os.path.join(ROOT, rel)
    d = os.path.dirname(path)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


LC = _load("lc_delivery", "ops/liveness_common.py")
SCAN = _load("undeliv_scan", "ops/undelivered_alert_scan.py")


# ------------------------------------------------------------ alert() ------
def test_alert_reports_a_successful_delivery(monkeypatch):
    import renquant_common.notify as notify

    monkeypatch.setattr(notify, "send", lambda *a, **k: True)
    assert LC.alert("t", "b") is True


def test_alert_reports_a_FAILED_delivery(monkeypatch):
    """THE defect. `send` never raises, so without this the caller cannot tell."""
    import renquant_common.notify as notify

    monkeypatch.setattr(notify, "send", lambda *a, **k: False)
    assert LC.alert("t", "b") is False


def test_alert_reports_False_when_the_sender_is_not_importable(monkeypatch):
    """Sender unavailable is not sender succeeded."""
    real = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def boom(name, *a, **k):
        if name == "renquant_common.notify":
            raise ImportError("simulated")
        return real(name, *a, **k)

    import builtins

    monkeypatch.setattr(builtins, "__import__", boom)
    assert LC.alert("t", "b") is False


def test_alert_is_annotated_as_returning_bool():
    import inspect

    # `from __future__ import annotations` makes annotations STRINGS. Asserting
    # `is bool` compares against the object and fails on a correct signature --
    # the test was wrong, not the code.
    assert inspect.signature(LC.alert).return_annotation == "bool"


# ------------------------------------------------------------- the scan ----
def test_the_scan_now_sees_a_SUPPRESSED_alarm(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("INFO [ntfy suppressed] rq104 DEGRADED: 3 issue(s)\n",
                   encoding="utf-8")
    found = SCAN.scan_log(log)
    assert len(found) == 1
    assert "rq104 DEGRADED" in found[0].title
    assert "RENQUANT_NO_NOTIFY" in found[0].error


def test_the_scan_still_sees_the_original_failure_class(tmp_path):
    """CONTROL: widening must not lose what it already caught."""
    log = tmp_path / "y.log"
    log.write_text(
        "WARNING ntfy send failed (failure #1, title='a b'): timed out\n",
        encoding="utf-8")
    found = SCAN.scan_log(log)
    assert len(found) == 1 and "timed out" in found[0].error


def test_a_clean_log_yields_nothing(tmp_path):
    """Anti-vacuity: a scan that flags everything would pass both tests above."""
    log = tmp_path / "z.log"
    log.write_text("INFO all good\nINFO nothing to see\n", encoding="utf-8")
    assert SCAN.scan_log(log) == []


def test_suppression_is_not_classified_as_a_permanent_encoding_defect():
    """It is a policy, not a codec bug — the reader must be able to tell."""
    # the property is `looked_permanent` ("what the LOG said at the time"), not
    # `is_permanent` -- verified by reading the dataclass rather than guessing.
    u = SCAN.Undelivered(log_path="p", title="t",
                         error="RENQUANT_NO_NOTIFY suppressed this alarm "
                               "before any send")
    assert u.looked_permanent is False
    assert u.status != "PERMANENT"
