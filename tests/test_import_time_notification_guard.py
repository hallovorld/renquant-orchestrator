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


# ── [codex on orch#806] the two reported escapes: one closed, one recorded ──

def test_a_SUBPROCESS_inherits_suppression_for_senders_that_honour_it(tmp_path):
    """`os.environ[...] = "1"` (not just an in-process patch) means a child
    inherits suppression for anything going through `notify.send`. A child does
    NOT inherit the transport backstop — see the residual test below."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c",
         "from renquant_common import notify; "
         "print('suppressed', notify.notifications_suppressed()); "
         "print('sent', notify.send('CHILD', 'must not send', 'probe'))"],
        capture_output=True, text=True, check=True).stdout
    assert "suppressed True" in out, out
    assert "sent False" in out, out


def test_the_ROOT_conftest_installs_the_same_guard():
    """A ROOT conftest is imported before any conftest under testpaths — the
    earliest hook a REPOSITORY can install. This asserts the root file exists
    and DELEGATES rather than duplicating; two copies would drift."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "conftest.py"
    assert root.exists(), "the root conftest is the earliest in-process hook"
    text = root.read_text()
    assert "install_notification_guard" in text
    assert "def _guarded_urlopen" not in text, (
        "the root conftest must DELEGATE, not carry a second copy of the guard")


def test_installing_twice_is_a_no_op_not_a_double_wrap():
    """Root + tests conftest both call it. A second wrap would make the guard
    recursive and the error message useless."""
    import urllib.request

    from tests.conftest import _guarded_urlopen, install_notification_guard

    install_notification_guard()
    install_notification_guard()
    assert urllib.request.urlopen is _guarded_urlopen



def test_the_KNOWN_RESIDUAL_is_stated_where_the_claim_is_made():
    """[codex on orch#806] A `-p` plugin is imported before ANY conftest, so
    nothing committed here can guard its import time. Codex reproduced it. That
    is a residual, and the way a residual stops being quietly re-claimed is that
    a test fails if the documents stop naming it.

    This test does not close the gap. It makes the gap un-forgettable.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    conftest = (root / "conftest.py").read_text()
    assert "-p" in conftest and "residual" in conftest.lower(), (
        "the root conftest must name the `-p` plugin residual where it makes "
        "its ordering claim")
    assert "from conftest import onward" in conftest, (
        "the scoped claim must be stated next to the code that implements it")

    doc = (root / "doc" / "progress"
           / "2026-08-05-tests-must-not-page-the-operator.md").read_text()
    assert "-p" in doc and "NOT CLOSED" in doc



def test_the_CHILD_TRANSPORT_residual_is_stated_where_the_claim_is_made():
    """[codex on orch#806] A child is a separate interpreter: it inherits the
    ENV VAR but not the in-process urlopen backstop, so a child that calls the
    ntfy transport DIRECTLY can still page even with suppression set. Codex
    reproduced it (`env 1`, `suppressed True`, `urlopen urlopen`).

    Not closeable from inside the parent. Pinned here so the prose cannot
    silently widen back to "every subprocess is covered".
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    # Prose is line-wrapped, so compare on collapsed whitespace — a guard that
    # depends on where a sentence happens to break is a guard that will red for
    # the wrong reason later.
    def flat(s: str) -> str:
        return " ".join(s.split())

    conftest = flat((root / "conftest.py").read_text())
    assert "does NOT inherit the transport backstop" in conftest
    assert "for senders that honour it" in conftest, (
        "the subprocess claim must say WHICH senders inherit suppression")

    doc = flat((root / "doc" / "progress"
                / "2026-08-05-tests-must-not-page-the-operator.md").read_text())
    assert "DIRECTLY rather than through" in doc and "NOT CLOSED" in doc
