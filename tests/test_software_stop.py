"""Tests for the per-position intraday software stop module."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from renquant_orchestrator.software_stop import (
    DEFAULT_HARD_STOP_PCT,
    DEFAULT_TRAILING_STOP_PCT,
    SoftwareStopEvaluator,
    SoftwareStopShadowLog,
    StopConfig,
    StopSignal,
)


def _ts() -> datetime:
    return datetime(2026, 7, 4, 14, 30, 0, tzinfo=timezone.utc)


def _config(*, enabled: bool = True, hard: float = 0.05, trail: float = 0.03) -> StopConfig:
    return StopConfig(hard_stop_pct=hard, trailing_stop_pct=trail, enabled=enabled)


def _evaluator(**kw: float | bool) -> SoftwareStopEvaluator:
    return SoftwareStopEvaluator(config=_config(**kw))


class TestStopConfig:
    def test_from_payload_defaults(self):
        cfg = StopConfig.from_payload(None)
        assert cfg.hard_stop_pct == DEFAULT_HARD_STOP_PCT
        assert cfg.trailing_stop_pct == DEFAULT_TRAILING_STOP_PCT
        assert cfg.enabled is False

    def test_from_payload_custom(self):
        cfg = StopConfig.from_payload({
            "hard_stop_pct": 0.08,
            "trailing_stop_pct": 0.04,
            "enabled": True,
        })
        assert cfg.hard_stop_pct == 0.08
        assert cfg.trailing_stop_pct == 0.04
        assert cfg.enabled is True


class TestHardStop:
    def test_hard_stop_fires_at_threshold(self):
        ev = _evaluator(hard=0.05)
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals = ev.evaluate_tick({"AAPL": 95.0}, now=_ts())
        assert len(signals) == 1
        assert signals[0].stop_type == "hard_stop"
        assert signals[0].symbol == "AAPL"
        assert signals[0].loss_pct == pytest.approx(0.05)

    def test_hard_stop_does_not_fire_above_threshold(self):
        ev = _evaluator(hard=0.05, trail=0.05)
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals = ev.evaluate_tick({"AAPL": 96.0}, now=_ts())
        assert len(signals) == 0

    def test_hard_stop_fires_once_sticky(self):
        ev = _evaluator(hard=0.05)
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals1 = ev.evaluate_tick({"AAPL": 94.0}, now=_ts())
        assert len(signals1) == 1
        signals2 = ev.evaluate_tick({"AAPL": 93.0}, now=_ts())
        assert len(signals2) == 0


class TestTrailingStop:
    def test_trailing_stop_fires_after_hwm_drop(self):
        ev = _evaluator(trail=0.03, hard=0.10)
        ev.load_positions({"GOOG": {"entry_price": 200.0}})
        ev.evaluate_tick({"GOOG": 210.0}, now=_ts())
        signals = ev.evaluate_tick({"GOOG": 203.5}, now=_ts())
        assert len(signals) == 1
        assert signals[0].stop_type == "trailing_stop"
        assert signals[0].session_hwm == 210.0
        assert signals[0].loss_pct == pytest.approx((210.0 - 203.5) / 210.0)

    def test_trailing_stop_hwm_updates(self):
        ev = _evaluator(trail=0.03, hard=0.10)
        ev.load_positions({"GOOG": {"entry_price": 200.0}})
        ev.evaluate_tick({"GOOG": 205.0}, now=_ts())
        assert ev.positions["GOOG"].session_hwm == 205.0
        ev.evaluate_tick({"GOOG": 210.0}, now=_ts())
        assert ev.positions["GOOG"].session_hwm == 210.0
        ev.evaluate_tick({"GOOG": 208.0}, now=_ts())
        assert ev.positions["GOOG"].session_hwm == 210.0

    def test_trailing_stop_does_not_fire_within_band(self):
        ev = _evaluator(trail=0.03, hard=0.10)
        ev.load_positions({"GOOG": {"entry_price": 200.0}})
        ev.evaluate_tick({"GOOG": 210.0}, now=_ts())
        signals = ev.evaluate_tick({"GOOG": 204.5}, now=_ts())
        assert len(signals) == 0


class TestMultiplePositions:
    def test_independent_tracking(self):
        ev = _evaluator(hard=0.05, trail=0.03)
        ev.load_positions({
            "AAPL": {"entry_price": 100.0},
            "GOOG": {"entry_price": 200.0},
        })
        signals = ev.evaluate_tick({"AAPL": 94.0, "GOOG": 201.0}, now=_ts())
        assert len(signals) == 1
        assert signals[0].symbol == "AAPL"
        assert ev.positions["GOOG"].stopped is False

    def test_both_stop(self):
        ev = _evaluator(hard=0.05, trail=0.03)
        ev.load_positions({
            "AAPL": {"entry_price": 100.0},
            "GOOG": {"entry_price": 200.0},
        })
        signals = ev.evaluate_tick({"AAPL": 94.0, "GOOG": 189.0}, now=_ts())
        assert len(signals) == 2
        syms = {s.symbol for s in signals}
        assert syms == {"AAPL", "GOOG"}


class TestDisabledConfig:
    def test_disabled_returns_empty(self):
        ev = SoftwareStopEvaluator(config=_config(enabled=False))
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals = ev.evaluate_tick({"AAPL": 50.0}, now=_ts())
        assert len(signals) == 0


class TestEdgeCases:
    def test_missing_quote_ignored(self):
        ev = _evaluator()
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals = ev.evaluate_tick({}, now=_ts())
        assert len(signals) == 0

    def test_zero_price_ignored(self):
        ev = _evaluator()
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        signals = ev.evaluate_tick({"AAPL": 0.0}, now=_ts())
        assert len(signals) == 0

    def test_negative_entry_price_skipped(self):
        ev = _evaluator()
        ev.load_positions({"BAD": {"entry_price": -10.0}})
        assert "BAD" not in ev.positions

    def test_no_entry_price_skipped(self):
        ev = _evaluator()
        ev.load_positions({"BAD": {}})
        assert "BAD" not in ev.positions

    def test_to_record_structure(self):
        ev = _evaluator()
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        ev.evaluate_tick({"AAPL": 94.0}, now=_ts())
        rec = ev.to_record()
        assert rec["positions_tracked"] == 1
        assert rec["positions_stopped"] == 1
        assert rec["signals_emitted"] == 1
        assert "AAPL" in rec["positions"]
        assert rec["positions"]["AAPL"]["stopped"] is True


class TestStopSignal:
    def test_to_intent(self):
        sig = StopSignal(
            symbol="AAPL",
            stop_type="hard_stop",
            entry_price=100.0,
            current_price=94.0,
            session_hwm=102.0,
            loss_pct=0.06,
            threshold_pct=0.05,
            timestamp="2026-07-04T14:30:00+00:00",
        )
        intent = sig.to_intent()
        assert intent["symbol"] == "AAPL"
        assert intent["side"] == "SELL"
        assert intent["kind"] == "exit"
        assert intent["reason"] == "hard_stop"
        assert intent["price"] == 94.0


class TestShadowLog:
    def test_append_creates_file(self, tmp_path: Path):
        log_path = tmp_path / "stops.jsonl"
        shadow = SoftwareStopShadowLog(log_path)
        sig = StopSignal(
            symbol="AAPL",
            stop_type="hard_stop",
            entry_price=100.0,
            current_price=94.0,
            session_hwm=102.0,
            loss_pct=0.06,
            threshold_pct=0.05,
            timestamp="2026-07-04T14:30:00+00:00",
        )
        shadow.append(sig, session_date="2026-07-04")
        assert log_path.exists()
        rows = [json.loads(line) for line in log_path.read_text().strip().split("\n")]
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["session_date"] == "2026-07-04"
        assert rows[0]["kind"] == "software_stop_signal"
        assert shadow.records_written == 1

    def test_append_multiple(self, tmp_path: Path):
        log_path = tmp_path / "stops.jsonl"
        shadow = SoftwareStopShadowLog(log_path)
        for sym in ("AAPL", "GOOG"):
            sig = StopSignal(
                symbol=sym,
                stop_type="trailing_stop",
                entry_price=100.0,
                current_price=96.0,
                session_hwm=105.0,
                loss_pct=0.04,
                threshold_pct=0.03,
                timestamp="2026-07-04T15:00:00+00:00",
            )
            shadow.append(sig, session_date="2026-07-04")
        rows = [json.loads(line) for line in log_path.read_text().strip().split("\n")]
        assert len(rows) == 2
        assert shadow.records_written == 2


class TestLoadPositionsAlternateKeys:
    def test_avg_entry_price_key(self):
        ev = _evaluator()
        ev.load_positions({"AAPL": {"avg_entry_price": 150.0}})
        assert "AAPL" in ev.positions
        assert ev.positions["AAPL"].entry_price == 150.0

    def test_hwm_fallback(self):
        """The evaluator doesn't do HWM fallback — that's the runner's job.
        But it should handle the standard entry_price key."""
        ev = _evaluator()
        ev.load_positions({"AAPL": {"entry_price": 100.0}})
        assert ev.positions["AAPL"].entry_price == 100.0
