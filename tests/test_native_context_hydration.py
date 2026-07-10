"""Hydration of the pinned pipeline's REAL InferenceContext (GOAL-1 fix).

The e2e test here runs the ACTUAL pinned ``InferencePipeline`` — no fixture
pipeline, no mocked stages — because the 2026-07-10 first real two-arm
session failed precisely where fixture-only tests could not look:
``SimpleNamespace(context_json)`` has no ``ctx.today`` (pp_inference.py:307).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator.native_context_hydration import (
    PANEL_SCORING_ALIAS,
    PANEL_SCORING_TARGET,
    HydrationError,
    hydrate_pipeline_context,
    install_native_panel_scoring_alias,
)
from renquant_orchestrator.native_live_inference import run_native_live_inference

SESSION_DATE = "2026-07-10"
WATCHLIST = ["AAA", "BBB"]


def _write_ohlcv_store(tmp_path: Path, symbols: list[str]) -> Path:
    """A readonly LocalStore layout: {dir}/{SYM}/1d.parquet through SESSION_DATE."""
    store = tmp_path / "ohlcv"
    end = pd.Timestamp(SESSION_DATE)
    index = pd.bdate_range(end=end, periods=250)
    for offset, symbol in enumerate(symbols):
        base = 100.0 + 10.0 * offset
        drift = pd.Series(range(len(index)), index=index) * 0.05
        close = base + drift + (pd.Series(range(len(index)), index=index) % 7) * 0.3
        frame = pd.DataFrame(
            {
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000,
            },
            index=index,
        )
        out = store / symbol / "1d.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out)
    return store


def _config(*, panel_enabled: bool = False) -> dict:
    return {
        "watchlist": list(WATCHLIST),
        "benchmark": "SPY",
        # keep the REAL pipeline deterministic in a synthetic world: the
        # freshness gate is exercised in production; here the synthetic
        # frames end exactly on the session date anyway.
        "data_freshness": {"enabled": False},
        "ranking": {"panel_scoring": {"enabled": panel_enabled}},
    }


def _account_snapshot(*, positions: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "broker_name": "alpaca_shadow_a",
        "cash": 10_000.0,
        "portfolio_value": 10_500.0,
        "positions": positions or {},
        "open_orders": [{"symbol": "BBB"}],
        "source": "test",
    }


def _context_payload(tmp_path: Path, *, positions: dict | None = None) -> Path:
    payload = {
        "schema_version": 1,
        "source": "native_live_context_fixture",
        "config": _config(),
        "market_snapshot": {
            "as_of": f"{SESSION_DATE}T17:20:00Z",
            "session_date": SESSION_DATE,
            "universe": list(WATCHLIST),
        },
        "account_snapshot": _account_snapshot(positions=positions),
        "metadata": {},
    }
    context_json = tmp_path / "native_context.json"
    context_json.write_text(json.dumps(payload), encoding="utf-8")
    return context_json


def test_hydrate_pipeline_context_builds_the_real_dataclass(tmp_path: Path) -> None:
    from renquant_pipeline.context import InferenceContext
    from renquant_pipeline.kernel.regime import RegimeState

    store = _write_ohlcv_store(tmp_path, [*WATCHLIST, "SPY"])
    positions = {
        "AAA": {
            "symbol": "AAA", "quantity": 2.0, "avg_entry_price": 90.0,
            "market_value": 200.0,
        },
    }
    payload = json.loads(_context_payload(tmp_path, positions=positions).read_text())

    ctx, report = hydrate_pipeline_context(
        payload,
        session_date=SESSION_DATE,
        broker_name="alpaca_shadow_a",
        strategy_dir=tmp_path / "configs",
        repo_root=tmp_path,
        ohlcv_dir=store,
    )
    assert isinstance(ctx, InferenceContext)
    assert ctx.today == dt.date.fromisoformat(SESSION_DATE)
    assert isinstance(ctx.regime_state, RegimeState)  # None crashes CUSUMTask
    assert ctx.broker_name == "alpaca_shadow_a"
    assert set(ctx.ohlcv) == {"AAA", "BBB", "SPY"}
    assert len(ctx.spy_returns) > 30
    # holdings from the sealed account snapshot
    assert set(ctx.holdings) == {"AAA"}
    assert ctx.holdings["AAA"].shares == 2.0
    assert ctx.holdings["AAA"].entry_price == 90.0
    # broker mark = market_value / quantity, local close fallback for the rest
    assert ctx.prices["AAA"] == pytest.approx(100.0)
    assert ctx.prices["BBB"] > 0
    assert ctx.cash == 10_000.0
    assert ctx.portfolio_value == 10_500.0
    # runtime-contract compatibility attrs for the snapshot extractor
    assert ctx.strategy_config is ctx.config
    assert ctx.market_snapshot["as_of"] == f"{SESSION_DATE}T17:20:00Z"
    assert ctx.pending_broker_tickers == ["BBB"]
    # the kernel scorer resolves relative artifact refs against this
    assert ctx.config["_strategy_dir"] == str(tmp_path / "configs")
    assert report["ohlcv_loaded"] == 3
    assert report["holdings"] == ["AAA"]


def test_hydrated_context_runs_the_real_pinned_inference_pipeline(tmp_path: Path) -> None:
    """THE e2e: the REAL ``InferencePipeline`` (no fixture pipeline, no mocked
    stages) must run to completion on a hydrated context and produce a
    decision payload — exactly the step that killed the first real session."""
    store = _write_ohlcv_store(tmp_path, [*WATCHLIST, "SPY"])
    context_json = _context_payload(tmp_path)
    output_json = tmp_path / "native_inference.json"

    payload = run_native_live_inference(
        context_json=context_json,
        output_json=output_json,
        hydrate_pipeline_context=True,
        session_date=SESSION_DATE,
        broker_name="alpaca_shadow_a",
        strategy_dir=tmp_path / "configs",
        repo_root=tmp_path,
        ohlcv_dir=store,
    )

    assert output_json.exists()
    # a real decision payload, not a crash: the snapshot contract fields
    for key in ("order_intents", "decision_trace", "scores", "blocked_by", "buy_blocked"):
        assert key in payload, key
    assert isinstance(payload["order_intents"], list)
    assert payload["market_as_of"] == f"{SESSION_DATE}T17:20:00Z"
    hydration = payload["metadata"]["pipeline_context_hydration"]
    assert hydration["ohlcv_loaded"] == 3
    assert f"{PANEL_SCORING_ALIAS}<-{PANEL_SCORING_TARGET}" in (
        hydration["pipeline_module_aliases"]
    )
    # the production alias is installed: Phase-3 resolves to the kernel scorer
    assert sys.modules[PANEL_SCORING_ALIAS].__name__ == PANEL_SCORING_TARGET


def test_hydration_requires_session_date(tmp_path: Path) -> None:
    context_json = _context_payload(tmp_path)
    with pytest.raises(ValueError, match="session-date"):
        run_native_live_inference(
            context_json=context_json,
            output_json=tmp_path / "out.json",
            hydrate_pipeline_context=True,
        )


def test_hydration_fails_closed_without_market_data(tmp_path: Path) -> None:
    payload = json.loads(_context_payload(tmp_path).read_text())
    with pytest.raises(HydrationError, match="no OHLCV"):
        hydrate_pipeline_context(
            payload,
            session_date=SESSION_DATE,
            ohlcv_dir=tmp_path / "empty-store",
        )


def test_hydration_fails_closed_on_bad_inputs(tmp_path: Path) -> None:
    good = json.loads(_context_payload(tmp_path).read_text())
    no_config = dict(good, config={})
    with pytest.raises(HydrationError, match="config"):
        hydrate_pipeline_context(no_config, session_date=SESSION_DATE)
    no_watchlist = dict(good, config={"watchlist": []})
    with pytest.raises(HydrationError, match="watchlist"):
        hydrate_pipeline_context(no_watchlist, session_date=SESSION_DATE)
    with pytest.raises(HydrationError, match="session_date"):
        hydrate_pipeline_context(good, session_date="not-a-date")


def test_panel_scoring_alias_is_pipeline_internal_and_idempotent() -> None:
    before = sys.modules.get(PANEL_SCORING_ALIAS)
    try:
        first = install_native_panel_scoring_alias()
        second = install_native_panel_scoring_alias()
        assert first == second
        target = sys.modules[PANEL_SCORING_ALIAS]
        assert target.__name__ == PANEL_SCORING_TARGET
        # pipeline-internal only: the routed module lives in renquant_pipeline
        assert target.__name__.startswith("renquant_pipeline.")
    finally:
        if before is not None:
            sys.modules[PANEL_SCORING_ALIAS] = before
        else:
            sys.modules.pop(PANEL_SCORING_ALIAS, None)


def test_legacy_namespace_path_is_unchanged(tmp_path: Path) -> None:
    """Without the hydration flag the pre-existing behavior is byte-identical:
    namespace context, caller-owned pipeline, no hydration metadata."""

    class _StubPipeline:
        def run(self, ctx) -> None:
            ctx.order_intents = []
            ctx.decision_trace = []

    context_json = _context_payload(tmp_path)
    output_json = tmp_path / "legacy.json"
    payload = run_native_live_inference(
        context_json=context_json,
        output_json=output_json,
        pipeline=_StubPipeline(),
    )
    assert "pipeline_context_hydration" not in payload["metadata"]
    assert output_json.exists()
