"""The guard itself must work, or it is decoration.

Incident 2026-08-05: a test run paged the operator. The alert body named a
pytest temp directory, so it was a test's — but the reader could not know that
until they read the path. An operator paged by tests stops trusting the pager.
"""
from __future__ import annotations

import os
import urllib.request

import pytest

from renquant_common import notify


def test_suppression_is_on_for_every_test_without_opting_in():
    assert notify.notifications_suppressed() is True
    assert os.environ["RENQUANT_NO_NOTIFY"] == "1"


def test_the_canonical_sender_does_not_reach_the_network():
    """`send` returns False when suppressed and NEVER raises (its contract)."""
    assert notify.send("TEST-TITLE", "TEST-BODY", "some-topic") is False


def test_a_bypassed_suppression_check_is_LOUD_not_silent(monkeypatch):
    """The backstop: if something reaches the transport anyway, the test fails
    and names itself — the phone does not ring."""
    monkeypatch.setattr(notify, "notifications_suppressed", lambda *a, **k: False)
    with pytest.raises(AssertionError, match="REAL notification POST"):
        urllib.request.urlopen(
            urllib.request.Request("https://ntfy.sh/renquant-test", data=b"x"))


def test_non_ntfy_urls_are_untouched():
    """The guard must not become a blanket network block — that would make
    unrelated failures look like notification failures."""
    req = urllib.request.Request("https://example.invalid/nothing")
    with pytest.raises(Exception) as exc:
        urllib.request.urlopen(req, timeout=0.01)
    assert "REAL notification POST" not in str(exc.value)
