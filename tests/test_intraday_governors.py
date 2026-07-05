"""Tests for renquant105 intraday cadence + governor module.

Covers:
  - GovernorConfig loading from strategy config (valid, invalid, absent)
  - Cadence checkpoint resolution and activation
  - All four governor checks (max actions, max turnover, ticker cooldown,
    loss cooldown) independently and in combination
  - Exits-never-blocked invariant for loss cooldown
  - GovernorState accumulation
  - Batch intent evaluation
  - GovernorEvaluator session lifecycle
  - GovernorShadowObserver tick processing
  - Config fingerprint stability
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator.intraday_governors import (
    BLOCK_LOSS_COOLDOWN,
    BLOCK_MAX_ACTIONS,
    BLOCK_MAX_TURNOVER,
    BLOCK_TICKER_COOLDOWN,
    CadenceCheckpoint,
    GovernorConfig,
    GovernorEvaluator,
    GovernorShadowObserver,
    GovernorState,
    GovernorVerdict,
    active_checkpoint,
    evaluate_governor,
    evaluate_tick_intents,
    load_governor_config,
    resolve_checkpoints,
)

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _et(h: int, m: int = 0, s: int = 0) -> datetime:
    """Build an aware ET datetime on a fixed test date."""
    return datetime(2026, 7, 5, h, m, s, tzinfo=ET)


def _make_config(**overrides: object) -> GovernorConfig:
    """Build a GovernorConfig with sane test defaults (enabled=True)."""
    defaults: dict[str, object] = {
        "enabled": True,
        "max_actions_per_session": 10,
        "max_turnover_fraction": 0.20,
        "min_seconds_between_same_ticker": 300,
        "loss_cooldown_seconds": 600,
        "loss_threshold_usd": 50.0,
    }
    defaults.update(overrides)
    return GovernorConfig(**defaults)  # type: ignore[arg-type]


def _make_state(equity: float = 100_000.0) -> GovernorState:
    """Build a fresh GovernorState."""
    return GovernorState(session_equity=equity)


# =========================================================================
# Config loading
# =========================================================================
class TestLoadGovernorConfig:
    def test_absent_section_disabled(self) -> None:
        cfg = load_governor_config({})
        assert not cfg.enabled
        assert cfg.config_errors == ()

    def test_none_config_disabled(self) -> None:
        cfg = load_governor_config(None)  # type: ignore[arg-type]
        assert not cfg.enabled

    def test_non_mapping_section(self) -> None:
        cfg = load_governor_config({"intraday_governors": "bad"})
        assert not cfg.enabled
        assert "is not a mapping" in cfg.config_errors[0]

    def test_valid_config(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {
                "enabled": True,
                "max_actions_per_session": 15,
                "max_turnover_fraction": 0.10,
                "min_seconds_between_same_ticker": 120,
                "loss_cooldown_seconds": 300,
                "loss_threshold_usd": 25.0,
                "checkpoint_names": ["open_plus_30", "power_hour"],
            }
        })
        assert cfg.enabled
        assert cfg.max_actions_per_session == 15
        assert cfg.max_turnover_fraction == 0.10
        assert cfg.min_seconds_between_same_ticker == 120
        assert cfg.loss_cooldown_seconds == 300
        assert cfg.loss_threshold_usd == 25.0
        assert cfg.checkpoint_names == ("open_plus_30", "power_hour")
        assert cfg.config_errors == ()

    def test_malformed_enabled_forces_disabled(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {
                "enabled": "yes",
                "max_actions_per_session": 10,
            }
        })
        assert not cfg.enabled
        assert any("enabled must be a boolean" in e for e in cfg.config_errors)

    def test_negative_value_error(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {
                "enabled": True,
                "max_actions_per_session": -1,
            }
        })
        assert not cfg.enabled
        assert any("must be >= 0" in e for e in cfg.config_errors)

    def test_non_numeric_error(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {
                "enabled": True,
                "max_turnover_fraction": "lots",
            }
        })
        assert not cfg.enabled
        assert any("is not a number" in e for e in cfg.config_errors)

    def test_non_list_checkpoint_names_error(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {
                "enabled": True,
                "checkpoint_names": "open_plus_30",
            }
        })
        assert not cfg.enabled
        assert any("checkpoint_names must be a list" in e for e in cfg.config_errors)

    def test_defaults_when_keys_absent(self) -> None:
        cfg = load_governor_config({
            "intraday_governors": {"enabled": True}
        })
        assert cfg.enabled
        assert cfg.max_actions_per_session == 0
        assert cfg.max_turnover_fraction == 0.0
        assert cfg.min_seconds_between_same_ticker == 0.0
        assert cfg.loss_cooldown_seconds == 0.0


# =========================================================================
# Cadence checkpoints
# =========================================================================
class TestCadenceCheckpoints:
    def test_positive_offset_from_open(self) -> None:
        cp = CadenceCheckpoint("open_plus_30", 30)
        session_open = _et(9, 30)
        session_close = _et(16, 0)
        assert cp.resolve(session_open, session_close) == _et(10, 0)

    def test_negative_offset_from_close(self) -> None:
        cp = CadenceCheckpoint("power_hour", -60)
        session_open = _et(9, 30)
        session_close = _et(16, 0)
        assert cp.resolve(session_open, session_close) == _et(15, 0)

    def test_half_day_scales(self) -> None:
        cp = CadenceCheckpoint("power_hour", -60)
        session_open = _et(9, 30)
        session_close = _et(13, 0)  # early close
        assert cp.resolve(session_open, session_close) == _et(12, 0)

    def test_resolve_checkpoints_sorted(self) -> None:
        cps = [
            CadenceCheckpoint("power_hour", -60),
            CadenceCheckpoint("open_plus_30", 30),
            CadenceCheckpoint("midday", 180),
        ]
        resolved = resolve_checkpoints(cps, _et(9, 30), _et(16, 0))
        names = [n for n, _ in resolved]
        assert names == ["open_plus_30", "midday", "power_hour"]

    def test_resolve_excludes_out_of_session(self) -> None:
        """A very short session might exclude some checkpoints."""
        cps = [
            CadenceCheckpoint("open_plus_30", 30),
            CadenceCheckpoint("midday", 180),  # 12:30 > 13:00 close
        ]
        resolved = resolve_checkpoints(cps, _et(9, 30), _et(11, 0))
        names = [n for n, _ in resolved]
        assert "open_plus_30" in names
        assert "midday" not in names

    def test_active_checkpoint(self) -> None:
        resolved = [
            ("open_plus_30", _et(10, 0)),
            ("midday", _et(12, 30)),
        ]
        assert active_checkpoint(resolved, _et(10, 0, 30)) == "open_plus_30"
        assert active_checkpoint(resolved, _et(12, 30, 0)) == "midday"
        assert active_checkpoint(resolved, _et(11, 0)) is None

    def test_active_checkpoint_window(self) -> None:
        resolved = [("cp", _et(10, 0))]
        # Inside window
        assert active_checkpoint(resolved, _et(10, 0, 59), window_seconds=60) == "cp"
        # Outside window
        assert active_checkpoint(resolved, _et(10, 1, 1), window_seconds=60) is None


# =========================================================================
# Governor evaluation — individual checks
# =========================================================================
class TestGovernorMaxActions:
    def test_under_limit_allowed(self) -> None:
        config = _make_config(max_actions_per_session=5)
        state = _make_state()
        state.action_count = 3
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5000.0, now=_et(10, 0),
        )
        assert v.allowed

    def test_at_limit_blocked(self) -> None:
        config = _make_config(max_actions_per_session=5)
        state = _make_state()
        state.action_count = 5
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5000.0, now=_et(10, 0),
        )
        assert not v.allowed
        assert BLOCK_MAX_ACTIONS in v.blocked_reasons

    def test_zero_limit_means_unlimited(self) -> None:
        config = _make_config(max_actions_per_session=0)
        state = _make_state()
        state.action_count = 9999
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5000.0, now=_et(10, 0),
        )
        assert v.allowed


class TestGovernorMaxTurnover:
    def test_under_turnover_allowed(self) -> None:
        config = _make_config(max_turnover_fraction=0.20)
        state = _make_state(equity=100_000.0)
        state.cumulative_turnover_notional = 10_000.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # projected = 15k / 100k = 0.15 < 0.20

    def test_over_turnover_blocked(self) -> None:
        config = _make_config(max_turnover_fraction=0.20)
        state = _make_state(equity=100_000.0)
        state.cumulative_turnover_notional = 18_000.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert not v.allowed  # projected = 23k / 100k = 0.23 > 0.20
        assert BLOCK_MAX_TURNOVER in v.blocked_reasons

    def test_zero_turnover_means_unlimited(self) -> None:
        config = _make_config(max_turnover_fraction=0.0)
        state = _make_state(equity=100_000.0)
        state.cumulative_turnover_notional = 999_999.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed

    def test_zero_equity_does_not_crash(self) -> None:
        config = _make_config(max_turnover_fraction=0.20)
        state = _make_state(equity=0.0)
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # can't compute fraction with zero equity


class TestGovernorTickerCooldown:
    def test_no_prior_action_allowed(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=300)
        state = _make_state()
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed

    def test_within_cooldown_blocked(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=300)
        state = _make_state()
        state.last_action_by_ticker["AAPL"] = _et(9, 58)
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert not v.allowed  # 120s < 300s
        assert BLOCK_TICKER_COOLDOWN in v.blocked_reasons

    def test_past_cooldown_allowed(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=300)
        state = _make_state()
        state.last_action_by_ticker["AAPL"] = _et(9, 50)
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # 600s > 300s

    def test_different_ticker_not_affected(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=300)
        state = _make_state()
        state.last_action_by_ticker["AAPL"] = _et(9, 59)
        v = evaluate_governor(
            config=config, state=state, ticker="MSFT",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # MSFT has no prior action

    def test_zero_cooldown_means_no_limit(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=0)
        state = _make_state()
        state.last_action_by_ticker["AAPL"] = _et(10, 0)
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed


class TestGovernorLossCooldown:
    def test_no_loss_allowed(self) -> None:
        config = _make_config(loss_cooldown_seconds=600)
        state = _make_state()
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed

    def test_recent_loss_blocks_entry(self) -> None:
        config = _make_config(loss_cooldown_seconds=600, loss_threshold_usd=50.0)
        state = _make_state()
        state.last_loss_at = _et(9, 55)
        state.last_loss_usd = -100.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert not v.allowed  # 300s < 600s
        assert BLOCK_LOSS_COOLDOWN in v.blocked_reasons

    def test_exits_never_blocked_by_loss_cooldown(self) -> None:
        """§10 exits-always-allowed: loss cooldown NEVER blocks exits."""
        config = _make_config(loss_cooldown_seconds=600)
        state = _make_state()
        state.last_loss_at = _et(9, 59)
        state.last_loss_usd = -1000.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="SELL", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # exits never blocked

    def test_loss_past_cooldown_allowed(self) -> None:
        config = _make_config(loss_cooldown_seconds=600)
        state = _make_state()
        state.last_loss_at = _et(9, 40)
        state.last_loss_usd = -200.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed  # 1200s > 600s

    def test_zero_cooldown_means_no_pause(self) -> None:
        config = _make_config(loss_cooldown_seconds=0)
        state = _make_state()
        state.last_loss_at = _et(9, 59, 59)
        state.last_loss_usd = -500.0
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v.allowed


class TestGovernorDisabled:
    def test_disabled_config_always_allows(self) -> None:
        config = GovernorConfig(enabled=False, max_actions_per_session=1)
        state = _make_state()
        state.action_count = 999
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=9999999.0, now=_et(10, 0),
        )
        assert v.allowed

    def test_absent_config_always_allows(self) -> None:
        config = load_governor_config({})
        state = _make_state()
        state.action_count = 999
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=9999999.0, now=_et(10, 0),
        )
        assert v.allowed


class TestGovernorMultipleBlocks:
    def test_multiple_governors_trip_simultaneously(self) -> None:
        """All tripped governors are reported, not just the first."""
        config = _make_config(
            max_actions_per_session=2,
            min_seconds_between_same_ticker=600,
        )
        state = _make_state()
        state.action_count = 3
        state.last_action_by_ticker["AAPL"] = _et(9, 55)
        v = evaluate_governor(
            config=config, state=state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert not v.allowed
        assert BLOCK_MAX_ACTIONS in v.blocked_reasons
        assert BLOCK_TICKER_COOLDOWN in v.blocked_reasons
        assert len(v.blocked_reasons) >= 2


# =========================================================================
# GovernorState
# =========================================================================
class TestGovernorState:
    def test_record_action_increments(self) -> None:
        state = _make_state(equity=100_000.0)
        state.record_action(
            ticker="AAPL", notional=5_000.0, at=_et(10, 0),
        )
        assert state.action_count == 1
        assert state.cumulative_turnover_notional == 5_000.0
        assert state.last_action_by_ticker["AAPL"] == _et(10, 0)

    def test_record_action_loss_tracking(self) -> None:
        state = _make_state()
        # Small loss below threshold: no trigger
        state.record_action(
            ticker="AAPL", notional=5_000.0, at=_et(10, 0),
            realized_pnl=-10.0, loss_threshold_usd=50.0,
        )
        assert state.last_loss_at is None  # below threshold

        # Loss above threshold: triggers
        state.record_action(
            ticker="MSFT", notional=8_000.0, at=_et(10, 30),
            realized_pnl=-100.0, loss_threshold_usd=50.0,
        )
        assert state.last_loss_at == _et(10, 30)
        assert state.last_loss_usd == -100.0

    def test_turnover_fraction(self) -> None:
        state = _make_state(equity=100_000.0)
        state.cumulative_turnover_notional = 15_000.0
        assert state.turnover_fraction() == pytest.approx(0.15)

    def test_turnover_fraction_zero_equity(self) -> None:
        state = _make_state(equity=0.0)
        state.cumulative_turnover_notional = 15_000.0
        assert state.turnover_fraction() == 0.0

    def test_to_record_serializable(self) -> None:
        state = _make_state(equity=50_000.0)
        state.record_action(ticker="AAPL", notional=3_000.0, at=_et(10, 0))
        record = state.to_record()
        assert record["action_count"] == 1
        assert "AAPL" in record["last_action_by_ticker"]
        assert isinstance(record["last_action_by_ticker"]["AAPL"], str)


# =========================================================================
# Batch intent evaluation
# =========================================================================
class TestEvaluateTickIntents:
    def test_all_allowed(self) -> None:
        config = _make_config(max_actions_per_session=10)
        state = _make_state()
        intents = [
            {"symbol": "AAPL", "side": "BUY", "notional": 5_000.0},
            {"symbol": "MSFT", "side": "SELL", "notional": 3_000.0},
        ]
        annotated = evaluate_tick_intents(
            config=config, state=state, intents=intents, now=_et(10, 0),
        )
        assert len(annotated) == 2
        assert all(not a["governor_blocked"] for a in annotated)

    def test_some_blocked(self) -> None:
        config = _make_config(min_seconds_between_same_ticker=600)
        state = _make_state()
        state.last_action_by_ticker["AAPL"] = _et(9, 55)
        intents = [
            {"symbol": "AAPL", "side": "BUY", "notional": 5_000.0},
            {"symbol": "MSFT", "side": "BUY", "notional": 3_000.0},
        ]
        annotated = evaluate_tick_intents(
            config=config, state=state, intents=intents, now=_et(10, 0),
        )
        assert annotated[0]["governor_blocked"]  # AAPL blocked
        assert not annotated[1]["governor_blocked"]  # MSFT allowed

    def test_does_not_modify_state(self) -> None:
        """evaluate_tick_intents is read-only on state."""
        config = _make_config(max_actions_per_session=10)
        state = _make_state()
        intents = [{"symbol": "AAPL", "side": "BUY", "notional": 5_000.0}]
        evaluate_tick_intents(
            config=config, state=state, intents=intents, now=_et(10, 0),
        )
        assert state.action_count == 0  # unchanged

    def test_empty_intents(self) -> None:
        config = _make_config()
        state = _make_state()
        annotated = evaluate_tick_intents(
            config=config, state=state, intents=[], now=_et(10, 0),
        )
        assert annotated == []


# =========================================================================
# GovernorEvaluator
# =========================================================================
class TestGovernorEvaluator:
    def test_evaluate_and_record(self) -> None:
        config = _make_config(max_actions_per_session=3)
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)

        intents = [{"symbol": "AAPL", "side": "BUY", "notional": 5_000.0}]
        result = evaluator.evaluate(intents, now=_et(10, 0))
        assert len(result) == 1
        assert not result[0]["governor_blocked"]

        # Record the action
        evaluator.record_action(ticker="AAPL", notional=5_000.0, at=_et(10, 0))
        assert evaluator.state.action_count == 1

    def test_summary(self) -> None:
        config = _make_config()
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)
        evaluator.evaluate(
            [{"symbol": "AAPL", "side": "BUY", "notional": 5_000.0}],
            now=_et(10, 0),
        )
        summary = evaluator.summary()
        assert summary["governor_enabled"]
        assert summary["ticks_evaluated"] == 1
        assert "state" in summary
        assert "config" in summary


# =========================================================================
# GovernorShadowObserver
# =========================================================================
class TestGovernorShadowObserver:
    def _make_tick_record(
        self,
        tick_index: int = 0,
        intents: list[dict[str, Any]] | None = None,
        tick_at: str = "2026-07-05T10:00:00-04:00",
    ) -> dict[str, Any]:
        from typing import Any
        return {
            "schema_version": "rq105-intraday-shadow-v1",
            "kind": "intraday_decision_shadow_tick",
            "session_date": "2026-07-05",
            "tick_index": tick_index,
            "tick_at": tick_at,
            "decisions": {
                "intents": intents or [],
                "skipped": [],
                "blocked_by": {},
                "counters": {"entries_count": 0},
            },
        }

    def test_observer_processes_tick(self) -> None:
        config = _make_config(max_actions_per_session=5)
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)
        observer = GovernorShadowObserver(evaluator)

        record = self._make_tick_record(intents=[
            {"symbol": "AAPL", "side": "BUY", "notional": 5_000.0},
        ])
        observer.on_tick(record)

        assert len(observer.evaluations) == 1
        assert observer.evaluations[0]["n_intents"] == 1
        assert observer.evaluations[0]["n_blocked"] == 0
        # State should be accumulated
        assert evaluator.state.action_count == 1

    def test_observer_accumulates_state_across_ticks(self) -> None:
        config = _make_config(max_actions_per_session=2)
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)
        observer = GovernorShadowObserver(evaluator)

        # First tick: allowed
        observer.on_tick(self._make_tick_record(
            tick_index=0,
            intents=[{"symbol": "AAPL", "side": "BUY", "notional": 5_000.0}],
            tick_at="2026-07-05T10:00:00-04:00",
        ))
        # Second tick: allowed (action_count=1, limit=2)
        observer.on_tick(self._make_tick_record(
            tick_index=1,
            intents=[{"symbol": "MSFT", "side": "BUY", "notional": 3_000.0}],
            tick_at="2026-07-05T10:12:00-04:00",
        ))
        # Third tick: should be blocked (action_count=2, limit=2)
        observer.on_tick(self._make_tick_record(
            tick_index=2,
            intents=[{"symbol": "GOOG", "side": "BUY", "notional": 4_000.0}],
            tick_at="2026-07-05T10:24:00-04:00",
        ))

        assert len(observer.evaluations) == 3
        assert observer.evaluations[0]["n_blocked"] == 0
        assert observer.evaluations[1]["n_blocked"] == 0
        assert observer.evaluations[2]["n_blocked"] == 1

    def test_observer_handles_missing_tick_at(self) -> None:
        config = _make_config()
        evaluator = GovernorEvaluator(config)
        observer = GovernorShadowObserver(evaluator)
        record = {"decisions": {"intents": []}}
        observer.on_tick(record)  # should not crash
        assert len(observer.evaluations) == 0

    def test_observer_handles_empty_decisions(self) -> None:
        config = _make_config()
        evaluator = GovernorEvaluator(config)
        observer = GovernorShadowObserver(evaluator)
        observer.on_tick(self._make_tick_record(intents=[]))
        assert len(observer.evaluations) == 1
        assert observer.evaluations[0]["n_intents"] == 0

    def test_blocked_intent_does_not_advance_turnover_state(self) -> None:
        """A shadow-blocked intent must not feed into governor state — it
        never executes in the world being modeled. Regression for a bug
        where on_tick() called record_action() for every intent regardless
        of its governor verdict, self-contaminating later ticks."""
        config = _make_config(
            max_actions_per_session=0,
            max_turnover_fraction=0.05,  # $5,000 cap on $100,000 equity
            min_seconds_between_same_ticker=0,
            loss_cooldown_seconds=0,
        )
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)
        observer = GovernorShadowObserver(evaluator)

        # Tick 1: $4,000 — within cap (0.04 <= 0.05). Allowed.
        observer.on_tick(self._make_tick_record(
            tick_index=0,
            intents=[{"symbol": "AAPL", "side": "BUY", "notional": 4_000.0}],
            tick_at="2026-07-05T10:00:00-04:00",
        ))
        assert observer.evaluations[0]["n_blocked"] == 0
        assert evaluator.state.cumulative_turnover_notional == 4_000.0

        # Tick 2: $4,000 more — projected (4000+4000)/100000=0.08 > 0.05.
        # Blocked. Must NOT advance cumulative_turnover_notional.
        observer.on_tick(self._make_tick_record(
            tick_index=1,
            intents=[{"symbol": "MSFT", "side": "BUY", "notional": 4_000.0}],
            tick_at="2026-07-05T10:12:00-04:00",
        ))
        assert observer.evaluations[1]["n_blocked"] == 1
        assert evaluator.state.cumulative_turnover_notional == 4_000.0, (
            "a shadow-blocked intent must not advance cumulative turnover — "
            "it never executed in the world being modeled"
        )

        # Tick 3: a small $500 intent that easily fits under the cap on its
        # own (4000+500=4500 -> 0.045 <= 0.05). Pre-fix, tick 2's blocked
        # $4,000 would have phantom-fed forward (cumulative=8000), pushing
        # this tick's projection to 0.085 > 0.05 and incorrectly blocking
        # it too — a cascading, self-contaminated false block.
        observer.on_tick(self._make_tick_record(
            tick_index=2,
            intents=[{"symbol": "GOOG", "side": "BUY", "notional": 500.0}],
            tick_at="2026-07-05T10:24:00-04:00",
        ))
        assert observer.evaluations[2]["n_blocked"] == 0, (
            "tick 3 should be allowed on its own merits — a prior "
            "shadow-blocked intent must not cascade into blocking it"
        )
        assert evaluator.state.cumulative_turnover_notional == 4_500.0

    def test_blocked_intent_does_not_advance_ticker_cooldown_state(self) -> None:
        """Same contamination bug, via the per-ticker cooldown timestamp:
        a blocked intent must not set last_action_by_ticker, or a later
        genuinely-first action on that ticker could be wrongly cooled down
        against a phantom prior timestamp."""
        config = _make_config(
            max_actions_per_session=1,  # tick 1 allowed, tick 2 blocked
            max_turnover_fraction=0.0,
            min_seconds_between_same_ticker=300,
            loss_cooldown_seconds=0,
        )
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)
        observer = GovernorShadowObserver(evaluator)

        observer.on_tick(self._make_tick_record(
            tick_index=0,
            intents=[{"symbol": "AAPL", "side": "BUY", "notional": 1_000.0}],
            tick_at="2026-07-05T10:00:00-04:00",
        ))
        assert observer.evaluations[0]["n_blocked"] == 0

        # Tick 2: MSFT — blocked by max_actions_per_session (action_count=1
        # already). Must NOT record a last_action_by_ticker timestamp for
        # MSFT, since it never actually acted.
        observer.on_tick(self._make_tick_record(
            tick_index=1,
            intents=[{"symbol": "MSFT", "side": "BUY", "notional": 1_000.0}],
            tick_at="2026-07-05T10:01:00-04:00",
        ))
        assert observer.evaluations[1]["n_blocked"] == 1
        assert "MSFT" not in evaluator.state.last_action_by_ticker, (
            "a shadow-blocked intent must not stamp a ticker cooldown "
            "timestamp — it never actually acted on that ticker"
        )


# =========================================================================
# Config fingerprint
# =========================================================================
class TestConfigFingerprint:
    def test_fingerprint_stable(self) -> None:
        c1 = _make_config()
        c2 = _make_config()
        assert c1.fingerprint() == c2.fingerprint()

    def test_fingerprint_changes_with_config(self) -> None:
        c1 = _make_config(max_actions_per_session=10)
        c2 = _make_config(max_actions_per_session=20)
        assert c1.fingerprint() != c2.fingerprint()

    def test_fingerprint_is_hex(self) -> None:
        fp = _make_config().fingerprint()
        assert len(fp) == 16
        int(fp, 16)  # should not raise


# =========================================================================
# GovernorVerdict
# =========================================================================
class TestGovernorVerdict:
    def test_allowed_verdict(self) -> None:
        v = GovernorVerdict(allowed=True)
        record = v.to_record()
        assert record["allowed"]
        assert record["blocked_reasons"] == []

    def test_blocked_verdict(self) -> None:
        v = GovernorVerdict(
            allowed=False,
            blocked_reasons=(BLOCK_MAX_ACTIONS, BLOCK_TICKER_COOLDOWN),
            details={BLOCK_MAX_ACTIONS: "at limit"},
        )
        record = v.to_record()
        assert not record["allowed"]
        assert len(record["blocked_reasons"]) == 2
        assert BLOCK_MAX_ACTIONS in record["details"]


# =========================================================================
# Integration: end-to-end session scenario
# =========================================================================
class TestEndToEndSession:
    def test_full_session_governor_lifecycle(self) -> None:
        """Simulate a session with governor evaluation across multiple ticks."""
        config = _make_config(
            max_actions_per_session=3,
            max_turnover_fraction=0.15,
            min_seconds_between_same_ticker=600,  # 10 min
            loss_cooldown_seconds=900,  # 15 min
            loss_threshold_usd=50.0,
        )
        evaluator = GovernorEvaluator(config, session_equity=100_000.0)

        # Tick 1 (10:00): BUY AAPL — allowed
        v1 = evaluate_governor(
            config=config, state=evaluator.state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 0),
        )
        assert v1.allowed
        evaluator.record_action(ticker="AAPL", notional=5_000.0, at=_et(10, 0))

        # Tick 2 (10:05): BUY AAPL again — blocked by ticker cooldown
        v2 = evaluate_governor(
            config=config, state=evaluator.state, ticker="AAPL",
            side="BUY", notional=5_000.0, now=_et(10, 5),
        )
        assert not v2.allowed
        assert BLOCK_TICKER_COOLDOWN in v2.blocked_reasons

        # Tick 3 (10:12): BUY MSFT — allowed (different ticker)
        v3 = evaluate_governor(
            config=config, state=evaluator.state, ticker="MSFT",
            side="BUY", notional=5_000.0, now=_et(10, 12),
        )
        assert v3.allowed
        evaluator.record_action(ticker="MSFT", notional=5_000.0, at=_et(10, 12))

        # Tick 4 (10:20): SELL AAPL at a loss — allowed (exit)
        v4 = evaluate_governor(
            config=config, state=evaluator.state, ticker="AAPL",
            side="SELL", notional=4_800.0, now=_et(10, 20),
        )
        assert v4.allowed
        evaluator.record_action(
            ticker="AAPL", notional=4_800.0, at=_et(10, 20),
            realized_pnl=-100.0,
        )

        # Tick 5 (10:25): BUY GOOG — blocked by loss cooldown
        v5 = evaluate_governor(
            config=config, state=evaluator.state, ticker="GOOG",
            side="BUY", notional=5_000.0, now=_et(10, 25),
        )
        assert not v5.allowed
        assert BLOCK_LOSS_COOLDOWN in v5.blocked_reasons

        # Tick 6 (10:40): BUY GOOG — loss cooldown expired? No, 20 min < 15 min = expired
        # Wait, 10:25 - 10:20 = 5 min which is < 15 min so still blocked
        # At 10:36 = 16 min past loss, should be allowed BUT max_actions = 3 and we have 3
        v6 = evaluate_governor(
            config=config, state=evaluator.state, ticker="GOOG",
            side="BUY", notional=5_000.0, now=_et(10, 36),
        )
        assert not v6.allowed
        assert BLOCK_MAX_ACTIONS in v6.blocked_reasons  # already at 3 actions

        # Summary should reflect the session
        summary = evaluator.summary()
        assert summary["state"]["action_count"] == 3
        assert summary["ticks_evaluated"] == 0  # we used evaluate_governor directly
