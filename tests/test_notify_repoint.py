"""Campaign B6 re-point tests: every orchestrator sender now routes through the
canonical ``renquant_common.notify`` sender.

The behavior CHANGE this re-point ships (and what these tests pin down):
``RENQUANT_NO_NOTIFY`` is now honored by the orchestrator's monitors — before
B6 no orchestrator sender checked it, so the monitors could not be muted via
the documented env (audit #296 XC-4). Each seam's house priority/tags are
preserved exactly.
"""
from __future__ import annotations

import importlib.util
import sys
import urllib.request
from pathlib import Path

import pytest

from renquant_orchestrator import (
    daily_trading_health,
    execution_reconciler,
    intraday_live_executor,
    state_backup,
    weekly_apy_monitor,
    weekly_promote_monitor,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeResponse:
    def read(self) -> bytes:
        return b"{}"


@pytest.fixture()
def capture(monkeypatch):
    monkeypatch.delenv("RENQUANT_NO_NOTIFY", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("RQ_ROOT", raising=False)
    calls: list[tuple[urllib.request.Request, float]] = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


@pytest.fixture()
def muted(capture, monkeypatch):
    monkeypatch.setenv("RENQUANT_NO_NOTIFY", "1")
    return capture


# --- module senders: house priority/tags preserved through the canonical seam ---
@pytest.mark.parametrize(
    ("poster", "priority", "tags"),
    [
        (weekly_apy_monitor.post_ntfy, None, None),
        (weekly_promote_monitor.post_ntfy, None, None),
        (daily_trading_health.post_ntfy, "4", "warning,chart"),
        (state_backup.post_ntfy, "3", "warning"),
        (execution_reconciler.post_ntfy, "4", "warning"),
    ],
)
def test_sender_shape_preserved(capture, poster, priority, tags):
    poster("title", "body", "some-topic")
    assert len(capture) == 1
    request, timeout = capture[0]
    assert request.full_url == "https://ntfy.sh/some-topic"
    assert request.get_header("Title") == "title"
    assert request.get_header("Priority") == priority
    assert request.get_header("Tags") == tags
    assert request.data == b"body"
    assert timeout == 5.0


@pytest.mark.parametrize(
    "poster",
    [
        weekly_apy_monitor.post_ntfy,
        weekly_promote_monitor.post_ntfy,
        daily_trading_health.post_ntfy,
        state_backup.post_ntfy,
        execution_reconciler.post_ntfy,
    ],
)
def test_no_notify_now_mutes_orchestrator_senders(muted, poster):
    """THE fix: pre-B6, none of these honored RENQUANT_NO_NOTIFY."""
    poster("title", "body", "some-topic")
    assert muted == []


def test_execution_reconciler_poster_returns_bool(capture, monkeypatch):
    assert execution_reconciler.post_ntfy("t", "b", "topic") is True
    monkeypatch.setenv("RENQUANT_NO_NOTIFY", "1")
    assert execution_reconciler.post_ntfy("t", "b", "topic") is False


def test_post_critical_ntfy_shape_and_suppression(capture, monkeypatch):
    intraday_live_executor.post_critical_ntfy("halt", "loss budget tripped")
    request, _ = capture[0]
    assert request.full_url == f"https://ntfy.sh/{intraday_live_executor.NTFY_TOPIC}"
    assert request.get_header("Priority") == "5"
    assert request.get_header("Tags") == "rotating_light"
    monkeypatch.setenv("RENQUANT_NO_NOTIFY", "1")
    intraday_live_executor.post_critical_ntfy("halt", "again")
    assert len(capture) == 1


# --- ops liveness checkers: _alert re-pointed to the canonical sender ---
def _load_script(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("name", "rel_path"),
    [
        ("pit_liveness_check_b6", "ops/pit/pit_liveness_check.py"),
        ("rq105_liveness_check_b6", "ops/renquant105/rq105_liveness_check.py"),
    ],
)
def test_ops_alert_routes_through_canonical_sender(capture, monkeypatch, name, rel_path):
    module = _load_script(name, rel_path)
    monkeypatch.setenv("NTFY_TOPIC", "ops-topic")
    module._alert("liveness title", "liveness body")
    assert len(capture) == 1
    request, timeout = capture[0]
    assert request.full_url == "https://ntfy.sh/ops-topic"
    assert request.get_header("Title") == "liveness title"
    assert timeout == 5.0
    # and the mute works here too
    monkeypatch.setenv("RENQUANT_NO_NOTIFY", "1")
    module._alert("liveness title", "liveness body")
    assert len(capture) == 1
