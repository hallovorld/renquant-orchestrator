"""Repo-wide test safety rails.

WHY THIS FILE EXISTS (incident 2026-08-05): a test run sent a REAL ntfy
notification to the operator's phone. The body named a pytest temp directory —
`/private/var/.../pytest-of-renhao/pytest-2550/test_a_later_corpus_edit_is_de0/
RenQuant/data/alpha158_291_fundamental_dataset.parquet` — so the alert was
unambiguously a test's, but nothing about it looked like a test to the reader.
An operator paged by a test learns to distrust the pager, which is how a real
alert gets ignored.

The sender already supports suppression (`RENQUANT_NO_NOTIFY`,
`renquant_common.notify.notifications_suppressed`). Nothing set it under
pytest. It is set here, for every test, plus a hard block at the transport so
that a test which unsets the variable, constructs its own environment, or calls
a pre-bound `post_ntfy` reference still cannot reach the network — and fails
loudly instead of silently paging a human.

Same family as the 2026-07-13 decision-ledger incident, where a test fix wrote
to the real production database: a test must not be able to reach a production
surface by accident, and the guard belongs at the surface, not in each test.
"""
from __future__ import annotations

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _no_real_notifications(monkeypatch):
    """Suppress ntfy for every test, and make an escape LOUD rather than silent.

    Two layers on purpose. `RENQUANT_NO_NOTIFY` is the sender's own documented
    switch and covers the ordinary path including callers that captured
    `post_ntfy` at import time. The urlopen block is the backstop for anything
    that bypasses that check — it raises, so the test fails and names itself
    instead of a human's phone ringing.
    """
    monkeypatch.setenv("RENQUANT_NO_NOTIFY", "1")

    real_urlopen = urllib.request.urlopen

    def guarded_urlopen(request, *args, **kwargs):
        url = getattr(request, "full_url", None) or str(request)
        if "ntfy" in str(url).lower():
            raise AssertionError(
                f"a test attempted a REAL notification POST to {url!r}. "
                "Notifications are suppressed under pytest (RENQUANT_NO_NOTIFY=1); "
                "reaching the transport means something bypassed that check. "
                "Inject or monkeypatch the sender in the test instead."
            )
        return real_urlopen(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)
