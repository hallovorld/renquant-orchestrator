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


def _write_ohlcv_store(
    tmp_path: Path, symbols: list[str], *, end_date: str = SESSION_DATE,
) -> Path:
    """A readonly LocalStore layout: {dir}/{SYM}/1d.parquet through end_date."""
    store = tmp_path / "ohlcv"
    end = pd.Timestamp(end_date)
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
    # r2: every consumed bar is sealed with its timestamp + the session
    # window that admitted it
    validity = hydration["bar_validity"]
    assert validity["decision_cutoff"] == SESSION_DATE
    assert validity["required_closed_session"] <= SESSION_DATE
    assert validity["session_close_watermark"].startswith(SESSION_DATE)
    assert set(validity["bar_timestamps"]) == {"AAA", "BBB", "SPY"}
    for ts in validity["bar_timestamps"].values():
        assert ts.startswith(SESSION_DATE)
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


# --- market-bar validity (Codex r2 on #460) -----------------------------------------------


def test_e2e_stale_bar_rejected(tmp_path: Path) -> None:
    """Named e2e (r2): a store whose last bar predates the required closed
    NYSE session for SESSION_DATE must be rejected — the arm exits nonzero
    instead of silently scoring a stale world."""
    store = _write_ohlcv_store(
        tmp_path, [*WATCHLIST, "SPY"], end_date="2026-07-08",  # Wed < Fri session
    )
    context_json = _context_payload(tmp_path)
    with pytest.raises(HydrationError, match="stale"):
        run_native_live_inference(
            context_json=context_json,
            output_json=tmp_path / "out.json",
            hydrate_pipeline_context=True,
            session_date=SESSION_DATE,
            strategy_dir=tmp_path / "configs",
            repo_root=tmp_path,
            ohlcv_dir=store,
        )
    assert not (tmp_path / "out.json").exists()


def test_e2e_future_bar_rejected(tmp_path: Path) -> None:
    """Named e2e (r2): a bar AFTER the decision cutoff (rerun lookahead —
    e.g. replaying 2026-07-10 against a store already refreshed with Monday
    bars) must be rejected, not silently consumed."""
    store = _write_ohlcv_store(
        tmp_path, [*WATCHLIST, "SPY"], end_date="2026-07-13",  # Mon > Fri session
    )
    context_json = _context_payload(tmp_path)
    with pytest.raises(HydrationError, match="future"):
        run_native_live_inference(
            context_json=context_json,
            output_json=tmp_path / "out.json",
            hydrate_pipeline_context=True,
            session_date=SESSION_DATE,
            strategy_dir=tmp_path / "configs",
            repo_root=tmp_path,
            ohlcv_dir=store,
        )
    assert not (tmp_path / "out.json").exists()


def test_validate_market_bars_seals_window_and_timestamps(tmp_path: Path) -> None:
    import datetime as dt

    from renquant_orchestrator.native_context_hydration import validate_market_bars

    store = _write_ohlcv_store(tmp_path, ["AAA"])
    frame = pd.read_parquet(store / "AAA" / "1d.parquet")
    block = validate_market_bars(
        {"AAA": frame}, session_date=dt.date.fromisoformat(SESSION_DATE),
    )
    assert block["bar_timestamps"]["AAA"].startswith(SESSION_DATE)
    assert block["decision_cutoff"] == SESSION_DATE
    assert "session_close_watermark" in block


# --- store-addressed config artifact-ref rewrite (Codex on #464) ---------------


def test_rewrite_config_artifact_refs_resolves_against_declared_store(tmp_path):
    from renquant_orchestrator.native_context_hydration import (
        rewrite_config_artifact_refs,
    )

    store = tmp_path / "store"
    (store / "panel").mkdir(parents=True)
    model = store / "panel" / "model.pt"
    model.write_bytes(b"m")
    calibrator = store / "panel" / "cal.json"
    calibrator.write_bytes(b"c")
    config = {
        "ranking": {"panel_scoring": {
            "artifact_path": "../../artifacts/panel/model.pt",
            "global_calibration": {
                "enabled": True,
                "artifact_path": "../../artifacts/panel/cal.json",
            },
        }},
    }
    pinned = tmp_path / "runtime" / "repos" / "renquant-strategy-104"
    pinned.mkdir(parents=True)
    rewritten = rewrite_config_artifact_refs(
        config,
        strategy_dir=pinned,
        repo_root=tmp_path / "runtime",
        artifact_store=store,
    )
    panel = config["ranking"]["panel_scoring"]
    # the kernel's LoadScorerTask uses absolute paths as-is — no umbrella
    # geometry needed downstream.
    assert panel["artifact_path"] == str(model.resolve())
    assert panel["global_calibration"]["artifact_path"] == str(calibrator.resolve())
    assert rewritten == {
        "../../artifacts/panel/model.pt": str(model.resolve()),
        "../../artifacts/panel/cal.json": str(calibrator.resolve()),
    }


def test_rewrite_config_artifact_refs_fails_closed_on_unresolvable(tmp_path):
    from renquant_orchestrator.native_context_hydration import (
        HydrationError,
        rewrite_config_artifact_refs,
    )

    store = tmp_path / "store"
    store.mkdir()
    config = {"ranking": {"panel_scoring": {
        "artifact_path": "../../artifacts/panel/missing.pt",
    }}}
    pinned = tmp_path / "runtime" / "repos" / "renquant-strategy-104"
    pinned.mkdir(parents=True)
    with pytest.raises(HydrationError, match="fail-closed"):
        rewrite_config_artifact_refs(
            config,
            strategy_dir=pinned,
            repo_root=tmp_path / "runtime",
            artifact_store=store,
        )


# --- write containment (2026-07-11 self-poisoning, r1 review) -----------------


def test_rewrite_config_log_containment_redirects_known_writers_only(tmp_path):
    """Hydration-level proof (Codex r1 review on #470): the in-memory
    containment rewrite reaches the actual admission-shadow and sleeve
    writer config, and touches NOTHING else — no field that could change a
    trading decision or output (sizing, scoring, gating, order generation)
    is read or modified by this rewrite."""
    import copy

    from renquant_orchestrator.native_context_hydration import (
        rewrite_config_log_containment,
    )

    config = {
        "benchmark": "SPY",
        "watchlist": ["AAPL", "MSFT"],
        "ranking": {"panel_scoring": {"enabled": True, "artifact_path": "x"}},
        "regime_params": {"BULL_CALM": {"max_position_pct": 0.12}},
        "sizing": {"one_share_floor_enabled": True},
        "admission_shadow": {"enabled": True, "some_other_key": "unchanged"},
        "sleeve": {
            "enabled": True,
            "log_path": "logs/parking_sleeve_shadow.jsonl",
            "beta_pos": 1.0,
        },
    }
    before = copy.deepcopy(config)

    contained = rewrite_config_log_containment(
        config, log_containment_dir=tmp_path / "arm_a",
    )

    # the actual admission-shadow and sleeve writer config DID get redirected
    assert config["admission_shadow"]["path"] == str(
        tmp_path / "arm_a" / "admission_shadow.jsonl"
    )
    assert config["sleeve"]["log_path"] == str(
        tmp_path / "arm_a" / "parking_sleeve_shadow.jsonl"
    )
    assert contained == {
        "admission_shadow": str(tmp_path / "arm_a" / "admission_shadow.jsonl"),
        "sleeve": str(tmp_path / "arm_a" / "parking_sleeve_shadow.jsonl"),
    }

    # every OTHER field, including sibling keys inside the two touched
    # blocks, is byte-identical to before the rewrite — no decision/output
    # field was read or changed as a side effect.
    assert config["benchmark"] == before["benchmark"]
    assert config["watchlist"] == before["watchlist"]
    assert config["ranking"] == before["ranking"]
    assert config["regime_params"] == before["regime_params"]
    assert config["sizing"] == before["sizing"]
    assert config["admission_shadow"]["enabled"] == before["admission_shadow"]["enabled"]
    assert (
        config["admission_shadow"]["some_other_key"]
        == before["admission_shadow"]["some_other_key"]
    )
    assert config["sleeve"]["enabled"] == before["sleeve"]["enabled"]
    assert config["sleeve"]["beta_pos"] == before["sleeve"]["beta_pos"]
    # only the two known path keys differ between before/after
    diff_keys_admission_shadow = {
        k for k in config["admission_shadow"]
        if config["admission_shadow"][k] != before["admission_shadow"].get(k)
    }
    assert diff_keys_admission_shadow == {"path"}
    diff_keys_sleeve = {
        k for k in config["sleeve"]
        if config["sleeve"][k] != before["sleeve"].get(k)
    }
    assert diff_keys_sleeve == {"log_path"}


def test_rewrite_config_log_containment_no_sleeve_log_path_is_a_no_op_for_sleeve(tmp_path):
    """A config with no sleeve block (or no log_path in it) must not gain
    one — the rewrite only redirects a writer that's actually configured,
    it never fabricates config the pipeline didn't already have."""
    from renquant_orchestrator.native_context_hydration import (
        rewrite_config_log_containment,
    )

    config = {"admission_shadow": {"enabled": True}}
    contained = rewrite_config_log_containment(
        config, log_containment_dir=tmp_path / "arm_b",
    )
    assert "sleeve" not in config
    assert contained == {
        "admission_shadow": str(tmp_path / "arm_b" / "admission_shadow.jsonl"),
    }


def test_hydrate_pipeline_context_threads_log_containment_into_admission_shadow_and_sleeve(
    tmp_path: Path,
) -> None:
    """Hydration-level test (Codex r1 review on #470) — not just the
    unit-level rewrite function above, but hydrate_pipeline_context's OWN
    call site, exercised through the REAL pinned pipeline exactly like
    test_hydrate_pipeline_context_builds_the_real_dataclass above. Proves
    (a) the resulting ctx.config's admission_shadow/sleeve writer paths are
    genuinely redirected into the arm's containment directory, and (b)
    every decision/output-relevant field (prices, holdings, cash,
    portfolio_value, today, regime_state) is IDENTICAL to a hydration run
    with containment disabled — the rewrite is proven side-effect-free
    outside the two writer-path keys, at the same fidelity as the existing
    artifact-ref-rewrite dataclass test."""
    from renquant_pipeline.context import InferenceContext

    store = _write_ohlcv_store(tmp_path, [*WATCHLIST, "SPY"])
    positions = {
        "AAA": {
            "symbol": "AAA", "quantity": 2.0, "avg_entry_price": 90.0,
            "market_value": 200.0,
        },
    }

    def _payload_with_writers() -> dict:
        payload = json.loads(
            _context_payload(tmp_path, positions=positions).read_text()
        )
        payload["config"]["admission_shadow"] = {
            "enabled": True,
            "path": "logs/admission_shadow.jsonl",
        }
        payload["config"]["sleeve"] = {
            "enabled": True,
            "log_path": "logs/parking_sleeve_shadow.jsonl",
            "beta_pos": 1.0,
        }
        return payload

    containment_dir = tmp_path / "arm_a"

    ctx_contained, report_contained = hydrate_pipeline_context(
        _payload_with_writers(),
        session_date=SESSION_DATE,
        broker_name="alpaca_shadow_a",
        strategy_dir=tmp_path / "configs",
        repo_root=tmp_path,
        ohlcv_dir=store,
        log_containment_dir=containment_dir,
    )
    ctx_uncontained, _report_uncontained = hydrate_pipeline_context(
        _payload_with_writers(),
        session_date=SESSION_DATE,
        broker_name="alpaca_shadow_a",
        strategy_dir=tmp_path / "configs",
        repo_root=tmp_path,
        ohlcv_dir=store,
    )
    assert isinstance(ctx_contained, InferenceContext)

    # the ACTUAL admission-shadow and sleeve writer config reaching the
    # real pipeline context is redirected — not left at the pinned-checkout
    # relative path.
    assert ctx_contained.config["admission_shadow"]["path"] == str(
        containment_dir / "admission_shadow.jsonl"
    )
    assert ctx_contained.config["sleeve"]["log_path"] == str(
        containment_dir / "parking_sleeve_shadow.jsonl"
    )
    assert report_contained["log_containment"] == {
        "admission_shadow": str(containment_dir / "admission_shadow.jsonl"),
        "sleeve": str(containment_dir / "parking_sleeve_shadow.jsonl"),
    }

    # nothing that could change a trading DECISION or OUTPUT differs
    # between the contained and uncontained hydration of the SAME payload.
    assert ctx_contained.today == ctx_uncontained.today
    assert ctx_contained.prices == ctx_uncontained.prices
    assert set(ctx_contained.holdings) == set(ctx_uncontained.holdings)
    assert (
        ctx_contained.holdings["AAA"].shares
        == ctx_uncontained.holdings["AAA"].shares
    )
    assert ctx_contained.cash == ctx_uncontained.cash
    assert ctx_contained.portfolio_value == ctx_uncontained.portfolio_value
    assert set(ctx_contained.ohlcv) == set(ctx_uncontained.ohlcv)
    # the enabled flags and non-path fields of the two touched blocks are
    # unchanged by containment — only the two writer-path keys differ.
    assert (
        ctx_contained.config["admission_shadow"]["enabled"]
        == ctx_uncontained.config["admission_shadow"]["enabled"]
    )
    assert (
        ctx_contained.config["sleeve"]["enabled"]
        == ctx_uncontained.config["sleeve"]["enabled"]
    )
    assert (
        ctx_contained.config["sleeve"]["beta_pos"]
        == ctx_uncontained.config["sleeve"]["beta_pos"]
    )
    assert ctx_uncontained.config["admission_shadow"]["path"] == "logs/admission_shadow.jsonl"
    assert ctx_uncontained.config["sleeve"]["log_path"] == "logs/parking_sleeve_shadow.jsonl"
