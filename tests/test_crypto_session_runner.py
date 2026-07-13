"""Tests for the crypto session runner CLI (D-C11)."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crypto_session_runner import (
    _load_config,
    _log_dir,
    main,
    run_one_tick,
)


def _fake_tick_result():
    from renquant_orchestrator.crypto_session import TickResult

    return TickResult(
        session_date=dt.date(2026, 7, 12),
        tick_utc=dt.datetime(2026, 7, 12, 5, 0, 0, tzinfo=dt.timezone.utc),
        entries_allowed=False,
        exits_allowed=True,
        reason="trust anchor not ready",
    )


class TestLoadConfig:
    def test_default_config(self):
        config = _load_config(None)
        assert config.enabled is True
        assert config.mode == "paper"

    def test_from_file(self, tmp_path):
        cfg = {"crypto_trading": {"enabled": True, "mode": "paper", "sleeve_budget_usd": 10000.0}}
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps(cfg))
        config = _load_config(str(cfg_file))
        assert config.enabled is True
        assert config.mode == "paper"
        assert config.sleeve_budget_usd == 10000.0


class TestLogDir:
    def test_creates_dir(self, tmp_path):
        d = tmp_path / "sub" / "logs"
        result = _log_dir(d)
        assert result.exists()
        assert result == d


class TestRunOneTick:
    @patch("scripts.crypto_session_runner.evaluate_tick")
    def test_writes_log_file(self, mock_eval, tmp_path, capsys):
        mock_eval.return_value = _fake_tick_result()
        from renquant_orchestrator.crypto_session import CryptoSessionConfig

        config = CryptoSessionConfig(enabled=True, mode="paper")
        result = run_one_tick(config, tmp_path)
        assert result["entries_allowed"] is False
        assert result["exits_allowed"] is True
        assert result["runner_version"] == "1"

        captured = capsys.readouterr()
        assert "entries_allowed" in captured.out

        log_files = list(tmp_path.glob("session_*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["reason"] == "trust anchor not ready"


class TestMainOnce:
    @patch("scripts.crypto_session_runner.evaluate_tick")
    def test_once_mode(self, mock_eval, tmp_path):
        mock_eval.return_value = _fake_tick_result()
        rc = main(["--once", "--log-dir", str(tmp_path)])
        assert rc == 0
        mock_eval.assert_called_once()

    @patch("scripts.crypto_session_runner.evaluate_tick")
    def test_config_file(self, mock_eval, tmp_path):
        mock_eval.return_value = _fake_tick_result()
        cfg = {"crypto_trading": {"enabled": True, "mode": "shadow"}}
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps(cfg))
        rc = main(["--once", "--config", str(cfg_file), "--log-dir", str(tmp_path)])
        assert rc == 0
        call_kwargs = mock_eval.call_args.kwargs
        assert call_kwargs["config"].mode == "shadow"


class TestMainLoop:
    @patch("scripts.crypto_session_runner.evaluate_tick")
    def test_loop_respects_interval(self, mock_eval, tmp_path):
        mock_eval.return_value = _fake_tick_result()
        call_count = 0

        original_sleep = time.sleep

        def counting_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt
            original_sleep(0.01)

        with patch("scripts.crypto_session_runner.time.sleep", side_effect=counting_sleep):
            with pytest.raises(KeyboardInterrupt):
                main(["--loop", "--interval", "5", "--log-dir", str(tmp_path)])

        assert mock_eval.call_count >= 2
