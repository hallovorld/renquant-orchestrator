"""Root conftest — the notification guard, installed as EARLY as pytest allows.

`tests/conftest.py` runs late enough that a plugin loaded with `-p` beats it
(codex on orch#806, reproduced: a minimal plugin printed `plugin_send True` and
attempted a real POST). A ROOT conftest is imported before any conftest under
`testpaths`, so it closes the ordinary ordering gap. It is not a complete
answer — see the residual list in
`doc/progress/2026-08-05-tests-must-not-page-the-operator.md` — and the claim in
this repo is scoped accordingly: **tests do not page the operator on any path
pytest controls in-process.**

Setting the environment variable here (rather than only patching in-process)
also means every subprocess a test spawns INHERITS suppression, which was the
other reported escape. A child that deliberately scrubs `RENQUANT_NO_NOTIFY` is
outside anything an in-process guard can reach; that is recorded, not papered
over.
"""
from __future__ import annotations

from tests.conftest import install_notification_guard  # noqa: F401

install_notification_guard()
