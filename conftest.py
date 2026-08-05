"""Root conftest — the notification guard, installed as EARLY as pytest allows.

A ROOT conftest is imported before any conftest under `testpaths`, which is the
earliest hook a REPOSITORY can install. It is NOT the earliest hook that exists:
a plugin named on the command line with `-p` is imported before any conftest at
all, and codex reproduced exactly that against this file
(`PLUGIN_IMPORT env None`, `PLUGIN_IMPORT guarded urlopen` printed before
collection). **Nothing committed to this repo can run before a `-p` plugin the
invoker chooses to load**, so that is a residual, recorded in
`doc/progress/2026-08-05-tests-must-not-page-the-operator.md` and pinned by a
test — not a gap this docstring will pretend is closed.

The honest claim is therefore narrow: **from conftest import onward, tests do
not page the operator.** Every test module, fixture, and subprocess is covered;
a `-p` plugin's own import time is not.

Setting the environment variable here (rather than only patching in-process)
means a subprocess a test spawns inherits suppression **for senders that honour
it** — i.e. anything going through `renquant_common.notify.send`. A child does
NOT inherit the transport backstop: it is a separate interpreter, so a child
calling `urllib.request.urlopen` at an ntfy URL directly, or scrubbing
`RENQUANT_NO_NOTIFY`, is outside anything an in-process guard can reach. Both
are recorded as residuals, not papered over.
"""
from __future__ import annotations

from tests.conftest import install_notification_guard  # noqa: F401

install_notification_guard()
