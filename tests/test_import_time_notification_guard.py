"""[codex on orch#806] The guard must hold during COLLECTION, not just per test.

An autouse fixture does not exist yet while pytest imports test modules. A
module-level call into an alert path would fire before any fixture runs — and
nothing about the mechanism that paged the operator required the send to be
inside a test BODY. This module attempts a send AT IMPORT TIME and records what
happened, so the collection-time window is covered by a test rather than by a
comment.
"""
from __future__ import annotations

import os

from renquant_common import notify

# ── executed during COLLECTION, before any fixture exists ───────────────────
_ENV_AT_IMPORT = os.environ.get("RENQUANT_NO_NOTIFY")
_SUPPRESSED_AT_IMPORT = notify.notifications_suppressed()
_SEND_RESULT_AT_IMPORT = notify.send("IMPORT-TIME-TEST", "must not reach ntfy",
                                     "renquant-import-guard-probe")


def test_suppression_was_already_on_during_collection():
    assert _ENV_AT_IMPORT == "1", (
        "RENQUANT_NO_NOTIFY was not set while test modules were being imported "
        "— an import-time send would have reached the operator's phone")
    assert _SUPPRESSED_AT_IMPORT is True


def test_an_import_time_send_did_not_reach_the_network():
    """`send` returns False when suppressed; True would mean a real POST."""
    assert _SEND_RESULT_AT_IMPORT is False


def test_the_transport_backstop_was_installed_during_collection(monkeypatch):
    """Belt and braces: prove the import-time urlopen swap is the guarded one,
    not merely that the env var happened to be set."""
    import urllib.request

    import pytest

    monkeypatch.setattr(notify, "notifications_suppressed", lambda *a, **k: False)
    with pytest.raises(AssertionError, match="REAL notification POST"):
        urllib.request.urlopen(
            urllib.request.Request("https://ntfy.sh/renquant-import-probe", data=b"x"))
