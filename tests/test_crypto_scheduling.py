"""Tests for crypto scheduling coordination (G2 S1-S4)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from renquant_orchestrator.crypto_scheduling import (
    EXCLUDED_PAIRS,
    CompletionMarker,
    CryptoScheduleConfig,
    check_upstream,
    crypto_status,
    load_latest_universe,
    read_completion_marker,
    run_universe_rotation,
    write_completion_marker,
)


@pytest.fixture
def cfg(tmp_path: Path) -> CryptoScheduleConfig:
    return CryptoScheduleConfig(state_dir=tmp_path / "crypto_state")


class TestCompletionMarkers:
    def test_write_and_read(self, cfg: CryptoScheduleConfig) -> None:
        marker = CompletionMarker(
            step="s2_universe",
            session_date="2025-07-13",
            completed_at_utc="2025-07-13T00:10:00+00:00",
            status="ok",
            detail={"n_selected": 5},
        )
        write_completion_marker(cfg, marker)
        read = read_completion_marker(cfg, "s2_universe", "2025-07-13")

        assert read is not None
        assert read.step == "s2_universe"
        assert read.status == "ok"
        assert read.detail["n_selected"] == 5

    def test_missing_marker(self, cfg: CryptoScheduleConfig) -> None:
        assert read_completion_marker(cfg, "s2_universe", "2025-07-13") is None

    def test_check_upstream(self, cfg: CryptoScheduleConfig) -> None:
        assert check_upstream(cfg, "s2_universe", "2025-07-13") is False

        write_completion_marker(cfg, CompletionMarker(
            step="s2_universe", session_date="2025-07-13",
            completed_at_utc="2025-07-13T00:10:00+00:00", status="ok",
        ))
        assert check_upstream(cfg, "s2_universe", "2025-07-13") is True

    def test_failed_marker_not_upstream(self, cfg: CryptoScheduleConfig) -> None:
        write_completion_marker(cfg, CompletionMarker(
            step="s2_universe", session_date="2025-07-13",
            completed_at_utc="2025-07-13T00:10:00+00:00", status="error",
        ))
        assert check_upstream(cfg, "s2_universe", "2025-07-13") is False


class TestUniverseRotation:
    def _make_returns(self, n: int = 90, mean: float = 0.001, std: float = 0.02, seed: int = 42) -> list[float]:
        rng = np.random.default_rng(seed)
        return rng.normal(mean, std, n).tolist()

    def test_basic_rotation(self, cfg: CryptoScheduleConfig) -> None:
        prices = {
            "BTC-USD": self._make_returns(90, mean=0.003, seed=1),
            "ETH-USD": self._make_returns(90, mean=0.002, seed=2),
            "SOL-USD": self._make_returns(90, mean=0.001, seed=3),
            "AVAX-USD": self._make_returns(90, mean=0.004, seed=4),
            "ADA-USD": self._make_returns(90, mean=0.0005, seed=5),
            "NEAR-USD": self._make_returns(90, mean=0.0, seed=6),
        }
        result = run_universe_rotation(cfg, "2025-07-13", prices)

        assert result["n_scored"] >= 4
        assert result["n_selected"] <= 5
        assert len(result["selected"]) == result["n_selected"]
        assert result["session_date"] == "2025-07-13"

    def test_excluded_pairs_filtered(self, cfg: CryptoScheduleConfig) -> None:
        prices = {
            "BTC-USD": self._make_returns(90, mean=0.005, seed=1),
            "XRP-USD": self._make_returns(90, mean=0.010, seed=2),
            "UNI-USD": self._make_returns(90, mean=0.008, seed=3),
        }
        result = run_universe_rotation(cfg, "2025-07-13", prices)

        selected_pairs = result["selected"]
        assert "XRP-USD" not in selected_pairs
        assert "UNI-USD" not in selected_pairs

    def test_negative_sharpe_excluded(self, cfg: CryptoScheduleConfig) -> None:
        prices = {
            "BTC-USD": self._make_returns(90, mean=-0.005, seed=1),
        }
        result = run_universe_rotation(cfg, "2025-07-13", prices)

        assert result["n_selected"] == 0

    def test_completion_marker_written(self, cfg: CryptoScheduleConfig) -> None:
        prices = {"BTC-USD": self._make_returns(90, seed=1)}
        run_universe_rotation(cfg, "2025-07-13", prices)

        assert check_upstream(cfg, "s2_universe", "2025-07-13") is True

    def test_insufficient_data_skipped(self, cfg: CryptoScheduleConfig) -> None:
        prices = {"BTC-USD": self._make_returns(30, seed=1)}
        result = run_universe_rotation(cfg, "2025-07-13", prices)

        assert result["n_scored"] == 0

    def test_top_n_respected(self, cfg: CryptoScheduleConfig) -> None:
        cfg2 = CryptoScheduleConfig(
            state_dir=cfg.state_dir,
            universe_top_n=2,
        )
        prices = {
            f"PAIR{i}-USD": self._make_returns(90, mean=0.001 * (i + 1), seed=i)
            for i in range(10)
        }
        result = run_universe_rotation(cfg2, "2025-07-13", prices)

        assert result["n_selected"] == 2

    def test_no_data_returns_empty(self, cfg: CryptoScheduleConfig) -> None:
        result = run_universe_rotation(cfg, "2025-07-13", None)
        assert result["pairs"] == []


class TestLoadLatestUniverse:
    def test_returns_watchlist_when_empty(self, cfg: CryptoScheduleConfig) -> None:
        result = load_latest_universe(cfg)
        assert result == list(cfg.watchlist)

    def test_returns_latest_selection(self, cfg: CryptoScheduleConfig) -> None:
        prices = {
            "BTC-USD": np.random.default_rng(1).normal(0.003, 0.02, 90).tolist(),
            "ETH-USD": np.random.default_rng(2).normal(0.002, 0.02, 90).tolist(),
        }
        run_universe_rotation(cfg, "2025-07-13", prices)
        result = load_latest_universe(cfg)

        assert isinstance(result, list)
        assert all(isinstance(p, str) for p in result)


class TestCryptoStatus:
    def test_empty_state(self, cfg: CryptoScheduleConfig) -> None:
        status = crypto_status(cfg)

        assert status["mode"] == "paper"
        assert status["universe"]["file"] is None
        assert status["signals"]["file"] is None
        assert status["actions"]["file"] is None

    def test_after_universe_rotation(self, cfg: CryptoScheduleConfig) -> None:
        prices = {
            "BTC-USD": np.random.default_rng(1).normal(0.003, 0.02, 90).tolist(),
        }
        run_universe_rotation(cfg, "2025-07-13", prices)
        status = crypto_status(cfg)

        assert status["universe"]["file"] is not None
        assert status["universe"]["selected"] is not None
