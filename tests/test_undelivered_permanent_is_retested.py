"""A claim about the FUTURE cannot be derived entirely from the PAST.

`PERMANENT` asserted "this call site can never deliver until the code changes". It
was decided by regexing the error text out of a log line — so it had an expiry and
no way to notice it.

Measured 2026-07-30: the scan reported
`[PERMANENT] 'rq104 blend 假想前10 — 2026-07-28'`. That defect was fixed on
**2026-07-29** by `renquant_common.notify.encode_header` (RFC 2047). The scan would
have kept reporting it every run forever — and orch#650 had just put it into a
scheduled audit, where a permanently-false alarm poisons every other member.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location(
    "ua", REPO / "ops" / "undelivered_alert_scan.py")
ua = importlib.util.module_from_spec(_S)
# MUST be registered before exec: this module defines a @dataclass, and
# dataclasses resolves type hints via sys.modules[cls.__module__]. Without this
# the import dies with "'NoneType' object has no attribute '__dict__'" — a harness
# failure that looks like a code failure.
sys.modules["ua"] = ua
_S.loader.exec_module(ua)

ENC_ERR = "'latin-1' codec can't encode characters in position 12-14"
NET_ERR = "<urlopen error _ssl.c:1000: The handshake operation timed out>"


def _item(title, error):
    return ua.Undelivered(log_path="/x/y.log", title=title, error=error)


def test_a_non_ascii_title_that_NOW_encodes_is_RESOLVED():
    """THE DEFECT. Both real cases — the blend readout's Chinese title and the
    rq105 sentinel's emoji — encode fine since 2026-07-29."""
    assert _item("'rq104 blend 假想前10 — 2026-07-28'", ENC_ERR).status == "RESOLVED"
    assert _item("'🚨 rq105 DOWN'", ENC_ERR).status == "RESOLVED"


def test_a_network_error_stays_TRANSIENT():
    assert _item("'RQ104 dawn preflight'", NET_ERR).status == "TRANSIENT"


def test_PERMANENT_survives_only_if_the_retest_still_fails(monkeypatch):
    """Anti-vacuity. If nothing could ever be PERMANENT the category would be dead
    and a genuine encoding defect would ship as RESOLVED."""
    monkeypatch.setattr(ua, "encoding_defect_still_present", lambda t: True)
    assert _item("'anything'", ENC_ERR).status == "PERMANENT"


def test_an_unimportable_encoder_is_UNTESTABLE_not_RESOLVED(monkeypatch):
    """Fail towards 'unverified'. Reporting RESOLVED because the test could not run
    would silently close a gap that may still be open — the same shape as a guard
    passing because its input was absent."""
    monkeypatch.setattr(ua, "encoding_defect_still_present", lambda t: None)
    assert _item("'x'", ENC_ERR).status == "UNTESTABLE"


def test_the_retest_strips_the_quotes_the_regex_captured():
    """The title arrives wrapped in the quotes the log line carried. Handing those
    to the encoder would test a different string than the one that failed."""
    assert ua.encoding_defect_still_present("'plain ascii'") is False
    assert ua.encoding_defect_still_present('"plain ascii"') is False


def test_RESOLVED_is_reported_not_dropped():
    """A closed historical gap is information: it says the fix landed. Hiding it
    makes the fix invisible; calling it PERMANENT makes the fix a lie."""
    out = ua.findings([_item("'rq104 blend 假想前10'", ENC_ERR)])
    assert len(out) == 1
    assert "[RESOLVED]" in out[0]
    assert "no action needed" in out[0]


def test_PERMANENT_sorts_above_RESOLVED(monkeypatch):
    calls = {"n": 0}
    def fake(t):
        calls["n"] += 1
        return "still" in t
    monkeypatch.setattr(ua, "encoding_defect_still_present", fake)
    out = ua.findings([_item("'fixed one'", ENC_ERR),
                       _item("'still broken'", ENC_ERR)])
    assert "[PERMANENT]" in out[0] and "[RESOLVED]" in out[1]
