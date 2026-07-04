"""Tests for the intraday session runner (105 integration layer)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest.mock import MagicMock, patch

import pytest

from renquant_orchestrator.intraday_session_runner import (
    RUNNER_SCHEMA_VERSION,
    SessionResult,
    SessionRunner,
    SessionRunnerConfig,
    _extract_holdings,
    _extract_quotes,
)
from renquant_orchestrator.software_stop import StopConfig

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from renquant_common.market_calendar import SessionBounds

ET = ZoneInfo("America/New_York")


def _trading_day_now(
    hour: int = 10, minute: int = 0
) -> datetime:
    return datetime(2026, 7, 6, hour, minute, 0, tzinfo=ET)


def _mock_strategy_config() -> dict[str, Any]:
    return {
        "watchlist": ["AAPL", "GOOG"],
        "intraday_decisioning": {
            "enabled": True,
            "mode": "shadow",
            "tick_seconds": 1,
        },
    }


def _mock_signal(day: str) -> dict[str, Any]:
    return {
        "signal_version": "test",
        "as_of": "2026-07-03",
        "source_run_id": "test-run",
        "score_content_sha256": "abc123",
        "scores": {"AAPL": {"mu": 0.02, "sigma": 0.15}},
    }


def _mock_session_start(day: str, now: datetime) -> dict[str, Any]:
    return {
        "session_date": day,
        "watchlist": ["AAPL", "GOOG"],
        "positions": {
            "AAPL": {"entry_price": 230.0, "shares": 10},
        },
    }


def _mock_live_state(**kwargs: Any) -> dict[str, Any]:
    return {
        "prices": {"AAPL": 231.0, "GOOG": 185.0},
        "positions": {"AAPL": {"qty": 10}},
    }


def _mock_tick_runner(
    signal: Any, session_start: Any, live_state: Any, **kw: Any
) -> dict[str, Any]:
    return {
        "intents": [],
        "counters": {},
    }


class _FakeCalendar:
    name = "test"

    def session_bounds(self, date):
        return SessionBounds(
            open=datetime(date.year, date.month, date.day, 9, 30, tzinfo=ET),
            close=datetime(date.year, date.month, date.day, 16, 0, tzinfo=ET),
        )


class _NonSessionCalendar:
    name = "test"

    def session_bounds(self, date):
        return None


def _runner_config(tmp_path: Path, **overrides: Any) -> SessionRunnerConfig:
    return SessionRunnerConfig(
        data_root=tmp_path,
        strategy_config=_mock_strategy_config(),
        stop_config=StopConfig(enabled=True, hard_stop_pct=0.05, trailing_stop_pct=0.03),
        **overrides,
    )


def _build_runner(
    tmp_path: Path,
    *,
    calendar=None,
    tick_runner=None,
    port_factory=None,
    config_overrides=None,
    **kw: Any,
) -> SessionRunner:
    cfg = _runner_config(tmp_path, **(config_overrides or {}))
    return SessionRunner(
        runner_config=cfg,
        tick_runner=tick_runner or _mock_tick_runner,
        signal_loader=_mock_signal,
        session_start_provider=_mock_session_start,
        live_state_provider=_mock_live_state,
        calendar=calendar or _FakeCalendar(),
        port_factory=port_factory,
        **kw,
    )


class TestShadowFallback:
    """When the quintuple gate doesn't arm, the runner delegates to shadow."""

    def test_shadow_mode_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
        runner = _build_runner(tmp_path)
        tick_count = [0]
        base_now = _trading_day_now(10, 0)

        def now_fn():
            nonlocal tick_count
            t = base_now + timedelta(seconds=tick_count[0] * 720)
            tick_count[0] += 1
            return t

        result = runner.run_session(
            now_fn=now_fn, sleep_fn=lambda _: None, max_cycles=2
        )
        assert result.mode_effective == "shadow"
        assert result.armed is False
        assert result.status in ("completed", "stopped_max_cycles")

    def test_shadow_result_has_arming_record(self, tmp_path: Path):
        runner = _build_runner(tmp_path)
        result = runner.run_session(
            now_fn=lambda: _trading_day_now(10, 0),
            sleep_fn=lambda _: None,
            max_cycles=1,
        )
        assert "stage2_arming" in result.manifest
        assert result.manifest["stage2_arming"]["armed"] is False

    def test_non_session_day(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RENQUANT_INTRADAY_DECISIONING", "1")
        runner = _build_runner(tmp_path, calendar=_NonSessionCalendar())
        result = runner.run_session(
            now_fn=lambda: _trading_day_now(10, 0),
            sleep_fn=lambda _: None,
        )
        assert result.status == "non_session_day"


class TestSoftwareStopsInShadow:
    """Software stops are evaluated even in shadow mode (observe-only)."""

    def test_stop_evaluator_runs(self, tmp_path: Path):
        runner = _build_runner(tmp_path)
        result = runner.run_session(
            now_fn=lambda: _trading_day_now(10, 0),
            sleep_fn=lambda _: None,
            max_cycles=1,
        )
        assert result.stop_summary is not None

    def test_stop_summary_in_result(self, tmp_path: Path):
        runner = _build_runner(tmp_path)
        result = runner.run_session(
            now_fn=lambda: _trading_day_now(10, 0),
            sleep_fn=lambda _: None,
            max_cycles=1,
        )
        d = result.to_dict()
        assert "software_stops" in d
        assert d["schema_version"] == RUNNER_SCHEMA_VERSION


class TestExtractHelpers:
    def test_extract_holdings_from_positions(self):
        ss = {"positions": {"AAPL": {"entry_price": 230.0}}}
        h = _extract_holdings(ss)
        assert h == {"AAPL": {"entry_price": 230.0}}

    def test_extract_holdings_from_hwm(self):
        ss = {
            "position_hwm": {"AAPL": 230.0, "GOOG": 185.0},
            "entry_dates": {"AAPL": "2026-06-01", "GOOG": "2026-06-15"},
        }
        h = _extract_holdings(ss)
        assert "AAPL" in h
        assert h["AAPL"]["entry_price"] == 230.0
        assert "GOOG" in h

    def test_extract_holdings_empty(self):
        h = _extract_holdings({})
        assert h == {}

    def test_extract_quotes_prices(self):
        ls = {"prices": {"AAPL": 231.0, "GOOG": 185.0}}
        q = _extract_quotes(ls)
        assert q == {"AAPL": 231.0, "GOOG": 185.0}

    def test_extract_quotes_marks(self):
        ls = {"marks": {"AAPL": 231.0}}
        q = _extract_quotes(ls)
        assert q == {"AAPL": 231.0}

    def test_extract_quotes_invalid_skipped(self):
        ls = {"prices": {"AAPL": "bad", "GOOG": -5.0, "MSFT": 100.0}}
        q = _extract_quotes(ls)
        assert q == {"MSFT": 100.0}


class TestSessionResult:
    def test_to_dict(self):
        r = SessionResult(
            mode_effective="shadow",
            armed=False,
            status="completed",
            manifest={"test": True},
            stop_summary={"signals_emitted": 0},
        )
        d = r.to_dict()
        assert d["mode_effective"] == "shadow"
        assert d["armed"] is False
        assert d["software_stops"] == {"signals_emitted": 0}

    def test_to_dict_no_stops(self):
        r = SessionResult(
            mode_effective="shadow",
            armed=False,
            status="completed",
            manifest={},
        )
        d = r.to_dict()
        assert "software_stops" not in d


class TestConfigResolvePaths:
    def test_resolve_sets_defaults(self, tmp_path: Path):
        cfg = _runner_config(tmp_path)
        cfg.resolve_paths()
        assert cfg.authorization_path is not None
        assert cfg.canary_state_path is not None
        assert cfg.order_state_book_path is not None
        assert cfg.shadow_log_path is not None
        assert cfg.live_log_path is not None
        assert cfg.live_actions_path is not None
        assert cfg.stop_log_path is not None

    def test_resolve_preserves_explicit(self, tmp_path: Path):
        custom = tmp_path / "custom_auth.json"
        cfg = _runner_config(tmp_path, authorization_path=custom)
        cfg.resolve_paths()
        assert cfg.authorization_path == custom


class TestLiveFallbackWithoutPortFactory:
    """If the gate somehow arms but no port_factory is provided, fall back."""

    def test_no_port_factory_falls_back_to_shadow(self, tmp_path: Path):
        runner = _build_runner(tmp_path, port_factory=None)
        with patch.object(
            runner, "_evaluate_arming",
            return_value=MagicMock(
                armed=True,
                mode_effective="live",
                downgraded=False,
                authorization=MagicMock(content_sha256="abc123"),
                to_manifest_record=lambda: {"armed": True},
            ),
        ):
            result = runner.run_session(
                now_fn=lambda: _trading_day_now(10, 0),
                sleep_fn=lambda _: None,
                max_cycles=1,
            )
        assert result.mode_effective == "shadow"


class TestKillSwitch:
    def test_kill_switch_path_from_config(self, tmp_path: Path):
        runner = _build_runner(tmp_path)
        ks = runner._build_kill_switch()
        assert not ks.engaged()

    def test_kill_switch_with_custom_file(self, tmp_path: Path):
        kill_file = tmp_path / "data" / "rq105" / "intraday_decisioning.KILL"
        kill_file.parent.mkdir(parents=True, exist_ok=True)
        kill_file.write_text("halt")
        runner = _build_runner(tmp_path)
        ks = runner._build_kill_switch()
        assert ks.engaged()
