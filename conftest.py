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
also means every subprocess a test spawns INHERITS suppression, which was the
other reported escape. A child that deliberately scrubs `RENQUANT_NO_NOTIFY` is
outside anything an in-process guard can reach; that is recorded, not papered
over.
"""
from __future__ import annotations

from tests.conftest import install_notification_guard  # noqa: F401

install_notification_guard()
