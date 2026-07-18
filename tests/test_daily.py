"""Unit tests for ``daily.py`` — individual task classes, helpers, and dataclass.

The existing ``test_daily_run_pipeline.py`` covers the integrated pipeline flow.
This file tests each public class and helper in isolation, monkeypatching the
external pipeline runners so no real training/inference/execution/backtest occurs.
"""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from renquant_common import PipelineResult, PipelineStepRecord
from renquant_execution import PaperBroker

from renquant_orchestrator.daily import (
    DailyRunContext,
    DailyRunJob,
    DailyRunPipeline,
    ExecuteOrderIntentsTask,
    PersistDailyRunBundleTask,
    RunBacktestCheckTask,
    RunRuntimeInferenceTask,
    TrainGbdtArtifactTask,
    ValidateDailyInputsTask,
    _json_safe,
    _pipeline_result,
    _write_json,
)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _strategy_config(**extras: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "watchlist": ["AAPL", "MSFT"],
        "ranking": {"panel_scoring": {"enabled": True}},
    }
    base.update(extras)
    return base


def _strategy_manifest() -> dict[str, Any]:
    return {
        "strategy": "renquant_104",
        "fingerprint": "sha256:strategy",
        "watchlist_size": 2,
    }


def _data_manifest() -> dict[str, Any]:
    return {
        "dataset_id": "daily-fixture",
        "fingerprint": "sha256:data",
    }


def _market_snapshot() -> dict[str, Any]:
    return {"as_of": "2026-07-04"}


def _model_config() -> dict[str, Any]:
    return {"objective": "rank:pairwise"}


def _artifact_manifest() -> dict[str, Any]:
    return {
        "artifact_id": "gbdt-fixture",
        "fingerprint": "sha256:model",
    }


def _fake_pipeline_result(name: str = "test", ok: bool = True) -> PipelineResult:
    return PipelineResult(
        name=name,
        ok=ok,
        elapsed_sec=0.001,
        steps=(
            PipelineStepRecord(job_name="FakeJob", skipped=False, elapsed_sec=0.001),
        ),
    )


def _make_ctx(tmp_path: Path, **overrides: Any) -> DailyRunContext:
    """Build a DailyRunContext with sane defaults, overridable by keyword."""
    defaults: dict[str, Any] = dict(
        run_id="test-run-001",
        run_type="daily_full",
        strategy_config=_strategy_config(),
        strategy_manifest=_strategy_manifest(),
        data_manifest=_data_manifest(),
        model_config=_model_config(),
        market_snapshot=_market_snapshot(),
        output_dir=tmp_path / "run",
        broker=PaperBroker(initial_cash=100_000.0),
        runtime_stages=[],
        dry_run=True,
    )
    defaults.update(overrides)
    return DailyRunContext(**defaults)


# ---------------------------------------------------------------------------
# DailyRunContext dataclass
# ---------------------------------------------------------------------------

class TestDailyRunContext:
    def test_defaults(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        assert ctx.dry_run is True
        assert ctx.account_snapshot == {}
        assert ctx.price_map == {}
        assert ctx.training_context is None
        assert ctx.inference_context is None
        assert ctx.execution_context is None
        assert ctx.backtest_context is None
        assert ctx.run_bundle == {}
        assert ctx.stage_trace == []
        assert ctx.resolved_serving_bundle is None

    def test_all_dataclass_fields_exist(self) -> None:
        names = {f.name for f in fields(DailyRunContext)}
        expected = {
            "run_id", "run_type", "strategy_config", "strategy_manifest",
            "data_manifest", "model_config", "market_snapshot", "output_dir",
            "broker", "runtime_stages", "account_snapshot", "price_map",
            "dry_run", "training_context", "inference_context",
            "execution_context", "backtest_context", "run_bundle", "stage_trace",
            "resolved_serving_bundle",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# ValidateDailyInputsTask
# ---------------------------------------------------------------------------

class TestValidateDailyInputsTask:
    def test_success(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        result = ValidateDailyInputsTask().run(ctx)
        assert result is True
        assert any(s["stage"] == "validate_daily_inputs" for s in ctx.stage_trace)

    def test_missing_run_id(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, run_id="")
        with pytest.raises(ValueError, match="run_id is required"):
            ValidateDailyInputsTask().run(ctx)

    def test_unsupported_run_type(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, run_type="invalid_type")
        with pytest.raises(ValueError, match="unsupported run_type"):
            ValidateDailyInputsTask().run(ctx)

    @pytest.mark.parametrize("run_type", ["daily_full", "daily_shadow", "manual_full"])
    def test_accepted_run_types(self, tmp_path: Path, run_type: str) -> None:
        ctx = _make_ctx(tmp_path, run_type=run_type)
        assert ValidateDailyInputsTask().run(ctx) is True

    def test_missing_watchlist(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, strategy_config={})
        with pytest.raises(ValueError, match="missing watchlist"):
            ValidateDailyInputsTask().run(ctx)

    def test_empty_watchlist(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, strategy_config={"watchlist": []})
        with pytest.raises(ValueError, match="missing watchlist"):
            ValidateDailyInputsTask().run(ctx)

    def test_missing_strategy_fingerprint(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, strategy_manifest={"strategy": "x"})
        with pytest.raises(ValueError, match="strategy_manifest missing fingerprint"):
            ValidateDailyInputsTask().run(ctx)

    def test_missing_data_fingerprint(self, tmp_path: Path) -> None:
        ctx = _make_ctx(
            tmp_path,
            data_manifest={"dataset_id": "no-fp"},
        )
        with pytest.raises(ValueError, match="data_manifest missing fingerprint"):
            ValidateDailyInputsTask().run(ctx)

    def test_missing_market_as_of(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, market_snapshot={})
        with pytest.raises(ValueError, match="market_snapshot missing as_of"):
            ValidateDailyInputsTask().run(ctx)

    def test_missing_broker_name(self, tmp_path: Path) -> None:
        broker = MagicMock()
        broker.broker_name = ""
        ctx = _make_ctx(tmp_path, broker=broker)
        with pytest.raises(ValueError, match="broker must expose broker_name"):
            ValidateDailyInputsTask().run(ctx)

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "run"
        ctx = _make_ctx(tmp_path, output_dir=out)
        ValidateDailyInputsTask().run(ctx)
        assert out.exists()

    def test_partial_strategy_config_tolerated(self, tmp_path: Path) -> None:
        """A config missing typed keys is tolerated (partial), not blocked."""
        ctx = _make_ctx(tmp_path)
        ValidateDailyInputsTask().run(ctx)
        config_trace = [s for s in ctx.stage_trace
                        if s.get("stage") == "validate_strategy_config"]
        assert len(config_trace) == 1
        # partial config -> missing keys recorded
        assert "partial_config_missing" in config_trace[0]

    def test_full_typed_config_passes(self, tmp_path: Path) -> None:
        cfg = _strategy_config(
            model_name="renquant_104",
            benchmark="SPY",
            wash_sale_days=31,
            min_hold_days=1,
            max_hold_days=500,
            max_concurrent_positions=8,
            regime={
                "bear_vol_threshold": 0.25,
                "bear_return_threshold": -0.02,
                "bear_vol_threshold_5d": 0.25,
                "bear_return_threshold_5d": -0.025,
                "transition_uncertainty_bars": 3,
                "bear_short_route_require_both": True,
            },
        )
        ctx = _make_ctx(tmp_path, strategy_config=cfg)
        ValidateDailyInputsTask().run(ctx)
        config_trace = [s for s in ctx.stage_trace
                        if s.get("stage") == "validate_strategy_config"]
        assert config_trace[0]["ok"] is True
        # fully typed -> no partial_config_missing, but has untyped_extra_keys
        assert "untyped_extra_keys" in config_trace[0]

    def test_invalid_typed_value_blocked(self, tmp_path: Path) -> None:
        """A positive bear_return_threshold (sign-flip) must be caught."""
        cfg = _strategy_config(
            model_name="renquant_104",
            benchmark="SPY",
            wash_sale_days=31,
            min_hold_days=1,
            max_hold_days=500,
            max_concurrent_positions=8,
            regime={
                "bear_vol_threshold": 0.25,
                "bear_return_threshold": 0.02,  # WRONG sign
                "bear_vol_threshold_5d": 0.25,
                "bear_return_threshold_5d": -0.025,
                "transition_uncertainty_bars": 3,
                "bear_short_route_require_both": True,
            },
        )
        ctx = _make_ctx(tmp_path, strategy_config=cfg)
        with pytest.raises(ValueError, match="invalid typed value"):
            ValidateDailyInputsTask().run(ctx)


# ---------------------------------------------------------------------------
# TrainGbdtArtifactTask
# ---------------------------------------------------------------------------

class TestTrainGbdtArtifactTask:
    def _make_task(self) -> TrainGbdtArtifactTask:
        loader = lambda manifest: {"rows": [1, 2]}
        trainer = lambda ds, cfg, out: (_artifact_manifest(), {"kind": "cal"})
        validator = lambda art, ds, cfg: {"accepted": True}
        return TrainGbdtArtifactTask(loader, trainer, validator)

    def test_success_populates_training_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _make_ctx(tmp_path)
        task = self._make_task()

        # Monkeypatch PanelGbdtTrainingPipeline.run to set artifact_manifest
        # and return a PipelineResult.
        def fake_run(pipeline_self, training_ctx):
            training_ctx.artifact_manifest = _artifact_manifest()
            return _fake_pipeline_result("gbdt-training")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.PanelGbdtTrainingPipeline.run", fake_run
        )

        result = task.run(ctx)
        assert result is True
        assert ctx.training_context is not None
        assert ctx.training_context.artifact_manifest == _artifact_manifest()
        trace = [s for s in ctx.stage_trace if s["stage"] == "train_gbdt"]
        assert len(trace) == 1
        assert trace[0]["ok"] is True
        assert trace[0]["artifact_id"] == "gbdt-fixture"
        assert "elapsed_sec" in trace[0]

    def test_raises_when_no_artifact_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _make_ctx(tmp_path)
        task = self._make_task()

        def fake_run(pipeline_self, training_ctx):
            # Deliberately do NOT set training_ctx.artifact_manifest
            return _fake_pipeline_result("gbdt-training")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.PanelGbdtTrainingPipeline.run", fake_run
        )

        with pytest.raises(ValueError, match="artifact_manifest"):
            task.run(ctx)

    def test_model_config_gets_strategy_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _make_ctx(tmp_path)
        task = self._make_task()
        captured: dict[str, Any] = {}

        def fake_run(pipeline_self, training_ctx):
            captured["model_config"] = dict(training_ctx.model_config)
            training_ctx.artifact_manifest = _artifact_manifest()
            return _fake_pipeline_result("gbdt-training")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.PanelGbdtTrainingPipeline.run", fake_run
        )

        task.run(ctx)
        assert captured["model_config"]["strategy"] == "renquant_104"
        assert captured["model_config"]["config_fingerprint"] == "sha256:strategy"

    def test_model_config_preserves_existing_strategy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _make_ctx(tmp_path, model_config={"strategy": "custom_strat"})
        task = self._make_task()
        captured: dict[str, Any] = {}

        def fake_run(pipeline_self, training_ctx):
            captured["model_config"] = dict(training_ctx.model_config)
            training_ctx.artifact_manifest = _artifact_manifest()
            return _fake_pipeline_result("gbdt-training")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.PanelGbdtTrainingPipeline.run", fake_run
        )

        task.run(ctx)
        # setdefault does not overwrite
        assert captured["model_config"]["strategy"] == "custom_strat"


# ---------------------------------------------------------------------------
# RunRuntimeInferenceTask
# ---------------------------------------------------------------------------

class TestRunRuntimeInferenceTask:
    def test_raises_without_training_context(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ValueError, match="training_context.artifact_manifest"):
            RunRuntimeInferenceTask().run(ctx)

    def test_raises_with_training_context_but_no_manifest(self, tmp_path: Path) -> None:
        from renquant_model_gbdt import TrainingContext
        ctx = _make_ctx(tmp_path)
        ctx.training_context = TrainingContext(
            dataset_manifest=_data_manifest(),
            model_config=_model_config(),
            output_dir=tmp_path / "training",
        )
        # artifact_manifest is None by default
        with pytest.raises(ValueError, match="training_context.artifact_manifest"):
            RunRuntimeInferenceTask().run(ctx)

    def test_success_populates_inference_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from renquant_model_gbdt import TrainingContext
        ctx = _make_ctx(tmp_path)
        ctx.training_context = TrainingContext(
            dataset_manifest=_data_manifest(),
            model_config=_model_config(),
            output_dir=tmp_path / "training",
        )
        ctx.training_context.artifact_manifest = _artifact_manifest()

        def fake_run(pipeline_self, inference_ctx):
            inference_ctx.order_intents.append({"ticker": "AAPL"})
            inference_ctx.decision_trace.append({"stage": "score"})
            return _fake_pipeline_result("runtime-inference")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.RuntimeInferencePipeline.run", fake_run
        )

        result = RunRuntimeInferenceTask().run(ctx)
        assert result is True
        assert ctx.inference_context is not None
        trace = [s for s in ctx.stage_trace if s["stage"] == "runtime_inference"]
        assert len(trace) == 1
        assert trace[0]["n_order_intents"] == 1
        assert trace[0]["n_decision_trace"] == 1


# ---------------------------------------------------------------------------
# ExecuteOrderIntentsTask
# ---------------------------------------------------------------------------

class TestExecuteOrderIntentsTask:
    def test_raises_without_inference_context(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ValueError, match="inference_context is required"):
            ExecuteOrderIntentsTask().run(ctx)

    def test_raises_on_missing_price_for_symbol(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from renquant_pipeline import InferenceContext
        ctx = _make_ctx(tmp_path, price_map={})
        ctx.inference_context = InferenceContext(
            strategy_config=_strategy_config(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            market_snapshot=_market_snapshot(),
        )
        ctx.inference_context.order_intents = [
            {"ticker": "AAPL", "action": "buy", "quantity": 1,
             "attribution": {"version": "v1", "source_job": "J",
                             "source_task": "T", "acceptance_reason": "R",
                             "score_snapshot": {"ticker": "AAPL"}}},
        ]
        # validate_order_attribution must pass before the price check
        monkeypatch.setattr(
            "renquant_orchestrator.daily.validate_order_attribution", lambda o: o
        )
        broker = PaperBroker(initial_cash=100_000.0)
        ctx.broker = broker
        with pytest.raises(ValueError, match="price_map missing.*AAPL"):
            ExecuteOrderIntentsTask().run(ctx)

    def test_broker_connect_disconnect_called(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from renquant_pipeline import InferenceContext
        ctx = _make_ctx(tmp_path)
        ctx.inference_context = InferenceContext(
            strategy_config=_strategy_config(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            market_snapshot=_market_snapshot(),
        )
        ctx.inference_context.order_intents = []  # no orders

        calls: list[str] = []
        broker = PaperBroker(initial_cash=100_000.0)
        original_connect = broker.connect
        original_disconnect = broker.disconnect

        def tracked_connect():
            calls.append("connect")
            return original_connect()

        def tracked_disconnect():
            calls.append("disconnect")
            return original_disconnect()

        broker.connect = tracked_connect  # type: ignore[assignment]
        broker.disconnect = tracked_disconnect  # type: ignore[assignment]
        ctx.broker = broker

        def fake_exec_run(pipeline_self, exec_ctx):
            return _fake_pipeline_result("execution")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.BrokerExecutionPipeline.run", fake_exec_run
        )

        ExecuteOrderIntentsTask().run(ctx)
        assert calls == ["connect", "disconnect"]

    def test_disconnect_called_on_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Broker.disconnect is called even when execution raises."""
        from renquant_pipeline import InferenceContext
        ctx = _make_ctx(tmp_path)
        ctx.inference_context = InferenceContext(
            strategy_config=_strategy_config(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            market_snapshot=_market_snapshot(),
        )
        ctx.inference_context.order_intents = []

        disconnected = []
        broker = PaperBroker(initial_cash=100_000.0)
        original_disconnect = broker.disconnect
        broker.disconnect = lambda: (disconnected.append(True), original_disconnect())[-1]  # type: ignore[assignment]
        ctx.broker = broker

        def bomb_run(pipeline_self, exec_ctx):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.BrokerExecutionPipeline.run", bomb_run
        )

        with pytest.raises(RuntimeError, match="boom"):
            ExecuteOrderIntentsTask().run(ctx)
        assert disconnected == [True]

    def test_success_populates_execution_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from renquant_pipeline import InferenceContext
        ctx = _make_ctx(tmp_path, dry_run=True)
        ctx.inference_context = InferenceContext(
            strategy_config=_strategy_config(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            market_snapshot=_market_snapshot(),
        )
        ctx.inference_context.order_intents = []

        def fake_exec_run(pipeline_self, exec_ctx):
            exec_ctx.submitted_orders.append({"order_id": "PAPER-0001"})
            return _fake_pipeline_result("execution")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.BrokerExecutionPipeline.run", fake_exec_run
        )

        result = ExecuteOrderIntentsTask().run(ctx)
        assert result is True
        assert ctx.execution_context is not None
        trace = [s for s in ctx.stage_trace if s["stage"] == "execute_order_intents"]
        assert len(trace) == 1
        assert trace[0]["n_submitted"] == 1
        assert trace[0]["dry_run"] is True


# ---------------------------------------------------------------------------
# RunBacktestCheckTask
# ---------------------------------------------------------------------------

class TestRunBacktestCheckTask:
    def test_skips_when_no_runner(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        result = RunBacktestCheckTask(runner=None).run(ctx)
        assert result is True
        trace = [s for s in ctx.stage_trace if s["stage"] == "backtest_check"]
        assert len(trace) == 1
        assert trace[0]["skipped"] is True

    def test_raises_without_training_context(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = lambda bctx: {"ok": True}
        with pytest.raises(ValueError, match="training artifact manifest"):
            RunBacktestCheckTask(runner=runner).run(ctx)

    def test_success_populates_backtest_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from renquant_model_gbdt import TrainingContext
        ctx = _make_ctx(tmp_path)
        ctx.training_context = TrainingContext(
            dataset_manifest=_data_manifest(),
            model_config=_model_config(),
            output_dir=tmp_path / "training",
        )
        ctx.training_context.artifact_manifest = _artifact_manifest()

        report = {"ok": True, "sharpe": 1.2}

        def fake_bt_run(pipeline_self, bt_ctx):
            bt_ctx.report = report
            return _fake_pipeline_result("backtest")

        monkeypatch.setattr(
            "renquant_orchestrator.daily.BacktestPipeline.run", fake_bt_run
        )

        runner = lambda bctx: report
        result = RunBacktestCheckTask(runner=runner).run(ctx)
        assert result is True
        assert ctx.backtest_context is not None
        trace = [s for s in ctx.stage_trace if s["stage"] == "backtest_check"]
        assert len(trace) == 1
        assert trace[0]["report"] == report


# ---------------------------------------------------------------------------
# PersistDailyRunBundleTask
# ---------------------------------------------------------------------------

class TestPersistDailyRunBundleTask:
    def _setup_ctx(self, tmp_path: Path) -> DailyRunContext:
        from renquant_execution import ExecutionContext
        from renquant_model_gbdt import TrainingContext
        from renquant_pipeline import InferenceContext

        ctx = _make_ctx(tmp_path)
        ctx.training_context = TrainingContext(
            dataset_manifest=_data_manifest(),
            model_config=_model_config(),
            output_dir=tmp_path / "training",
        )
        ctx.training_context.artifact_manifest = _artifact_manifest()
        ctx.inference_context = InferenceContext(
            strategy_config=_strategy_config(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            market_snapshot=_market_snapshot(),
        )
        ctx.inference_context.decision_trace.append({"stage": "score"})
        ctx.inference_context.order_intents.append({"ticker": "AAPL"})
        ctx.execution_context = ExecutionContext(
            broker_name="paper",
            order_intents=[{"ticker": "AAPL"}],
        )
        ctx.execution_context.submitted_orders.append({"order_id": "P-001"})
        ctx.execution_context.audit_rows.append({"event": "fill"})
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        return ctx

    def test_writes_bundle_and_sidecar_files(self, tmp_path: Path) -> None:
        ctx = self._setup_ctx(tmp_path)
        result = PersistDailyRunBundleTask().run(ctx)
        assert result is True
        assert (ctx.output_dir / "run_bundle.json").exists()
        assert (ctx.output_dir / "decision_trace.json").exists()
        assert (ctx.output_dir / "submitted_orders.json").exists()

    def test_bundle_contents(self, tmp_path: Path) -> None:
        ctx = self._setup_ctx(tmp_path)
        PersistDailyRunBundleTask().run(ctx)
        bundle = json.loads((ctx.output_dir / "run_bundle.json").read_text())
        assert bundle["schema_version"] == 1
        assert bundle["run_id"] == "test-run-001"
        assert bundle["run_type"] == "daily_full"
        assert bundle["dry_run"] is True
        assert bundle["artifact_manifest"]["artifact_id"] == "gbdt-fixture"
        assert bundle["decision_trace"] == [{"stage": "score"}]
        assert bundle["order_intents"] == [{"ticker": "AAPL"}]
        assert bundle["submitted_orders"] == [{"order_id": "P-001"}]
        assert bundle["execution_audit"] == [{"event": "fill"}]
        # RFC RenQuant#492 §2.2 binding block: explicit not-deployed marker
        # while no production bundle store exists (store migration is
        # census-gated; ctx.resolved_serving_bundle defaults to None).
        assert bundle["serving_bundle"] == {"bundle_store": "not_deployed"}
        # output_files added on second write
        assert "output_files" in bundle
        assert "run_bundle" in bundle["output_files"]

    def test_backtest_report_none_when_no_backtest(self, tmp_path: Path) -> None:
        ctx = self._setup_ctx(tmp_path)
        ctx.backtest_context = None
        PersistDailyRunBundleTask().run(ctx)
        bundle = json.loads((ctx.output_dir / "run_bundle.json").read_text())
        assert bundle["backtest_report"] is None

    def test_backtest_report_included_when_present(self, tmp_path: Path) -> None:
        from renquant_backtesting import BacktestContext
        ctx = self._setup_ctx(tmp_path)
        ctx.backtest_context = BacktestContext(
            strategy_manifest=_strategy_manifest(),
            data_manifest=_data_manifest(),
            artifact_manifest=_artifact_manifest(),
            output_dir=tmp_path / "bt",
        )
        ctx.backtest_context.report = {"sharpe": 1.5}
        PersistDailyRunBundleTask().run(ctx)
        bundle = json.loads((ctx.output_dir / "run_bundle.json").read_text())
        assert bundle["backtest_report"] == {"sharpe": 1.5}

    def test_raises_without_training_context(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ValueError, match="training artifact manifest"):
            PersistDailyRunBundleTask().run(ctx)

    def test_raises_without_inference_context(self, tmp_path: Path) -> None:
        from renquant_model_gbdt import TrainingContext
        ctx = _make_ctx(tmp_path)
        ctx.training_context = TrainingContext(
            dataset_manifest=_data_manifest(),
            model_config=_model_config(),
            output_dir=tmp_path / "training",
        )
        ctx.training_context.artifact_manifest = _artifact_manifest()
        with pytest.raises(ValueError, match="inference and execution contexts"):
            PersistDailyRunBundleTask().run(ctx)

    def test_stage_trace_appended(self, tmp_path: Path) -> None:
        ctx = self._setup_ctx(tmp_path)
        PersistDailyRunBundleTask().run(ctx)
        assert any(
            s.get("stage") == "persist_daily_run_bundle" for s in ctx.stage_trace
        )

    def test_run_bundle_set_on_ctx(self, tmp_path: Path) -> None:
        ctx = self._setup_ctx(tmp_path)
        PersistDailyRunBundleTask().run(ctx)
        assert ctx.run_bundle["run_id"] == "test-run-001"


# ---------------------------------------------------------------------------
# DailyRunJob
# ---------------------------------------------------------------------------

class TestDailyRunJob:
    def test_task_order(self) -> None:
        job = DailyRunJob(
            loader=lambda m: None,
            trainer=lambda d, c, o: (None, None),
            validator=lambda a, d, c: {},
            backtest_runner=None,
        )
        expected = [
            "ValidateDailyInputsTask",
            "TrainGbdtArtifactTask",
            "RunRuntimeInferenceTask",
            "ExecuteOrderIntentsTask",
            "RunBacktestCheckTask",
            "PersistDailyRunBundleTask",
        ]
        assert [type(t).__name__ for t in job.tasks] == expected

    def test_task_count(self) -> None:
        job = DailyRunJob(
            loader=lambda m: None,
            trainer=lambda d, c, o: (None, None),
            validator=lambda a, d, c: {},
            backtest_runner=lambda b: {"ok": True},
        )
        assert len(job.tasks) == 6


# ---------------------------------------------------------------------------
# DailyRunPipeline
# ---------------------------------------------------------------------------

class TestDailyRunPipeline:
    def test_name(self) -> None:
        pipeline = DailyRunPipeline(
            loader=lambda m: None,
            trainer=lambda d, c, o: (None, None),
            validator=lambda a, d, c: {},
        )
        assert pipeline.name == "daily-training-to-trading"

    def test_single_job(self) -> None:
        pipeline = DailyRunPipeline(
            loader=lambda m: None,
            trainer=lambda d, c, o: (None, None),
            validator=lambda a, d, c: {},
            backtest_runner=lambda b: {},
        )
        assert len(pipeline.jobs) == 1
        assert isinstance(pipeline.jobs[0], DailyRunJob)


# ---------------------------------------------------------------------------
# _pipeline_result helper
# ---------------------------------------------------------------------------

class TestPipelineResultHelper:
    def test_basic_structure(self) -> None:
        pr = PipelineResult(
            name="test-pipe",
            ok=True,
            elapsed_sec=1.23,
            steps=(
                PipelineStepRecord(job_name="JobA", skipped=False, elapsed_sec=0.5),
                PipelineStepRecord(job_name="JobB", skipped=True, elapsed_sec=0.0),
            ),
        )
        d = _pipeline_result(pr)
        assert d["name"] == "test-pipe"
        assert d["ok"] is True
        assert d["elapsed_sec"] == 1.23
        assert len(d["steps"]) == 2
        assert d["steps"][0] == {"job_name": "JobA", "skipped": False, "elapsed_sec": 0.5}
        assert d["steps"][1] == {"job_name": "JobB", "skipped": True, "elapsed_sec": 0.0}

    def test_empty_steps(self) -> None:
        pr = PipelineResult(name="empty", ok=False, elapsed_sec=0.0, steps=())
        d = _pipeline_result(pr)
        assert d["steps"] == []
        assert d["ok"] is False


# ---------------------------------------------------------------------------
# _write_json helper
# ---------------------------------------------------------------------------

class TestWriteJson:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        _write_json(p, {"key": "value", "n": 42})
        data = json.loads(p.read_text())
        assert data == {"key": "value", "n": 42}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "a" / "b" / "c.json"
        _write_json(p, [1, 2, 3])
        assert p.exists()
        assert json.loads(p.read_text()) == [1, 2, 3]

    def test_ends_with_newline(self, tmp_path: Path) -> None:
        p = tmp_path / "nl.json"
        _write_json(p, {})
        assert p.read_text().endswith("\n")

    def test_sorted_keys(self, tmp_path: Path) -> None:
        p = tmp_path / "sorted.json"
        _write_json(p, {"z": 1, "a": 2})
        text = p.read_text()
        assert text.index('"a"') < text.index('"z"')


# ---------------------------------------------------------------------------
# _json_safe helper
# ---------------------------------------------------------------------------

class TestJsonSafe:
    def test_primitives_passthrough(self) -> None:
        assert _json_safe("hello") == "hello"
        assert _json_safe(42) == 42
        assert _json_safe(3.14) == 3.14
        assert _json_safe(True) is True
        assert _json_safe(None) is None

    def test_path_to_str(self) -> None:
        assert _json_safe(Path("/tmp/x")) == "/tmp/x"

    def test_nested_dict(self) -> None:
        assert _json_safe({"a": {"b": 1}}) == {"a": {"b": 1}}

    def test_dict_keys_stringified(self) -> None:
        assert _json_safe({1: "one", 2: "two"}) == {"1": "one", "2": "two"}

    def test_list(self) -> None:
        assert _json_safe([1, "two", None]) == [1, "two", None]

    def test_tuple_to_list(self) -> None:
        assert _json_safe((1, 2)) == [1, 2]

    def test_nested_path_in_dict(self) -> None:
        assert _json_safe({"p": Path("/a/b")}) == {"p": "/a/b"}

    def test_unknown_type_to_str(self) -> None:
        class Custom:
            def __str__(self) -> str:
                return "custom_value"
        assert _json_safe(Custom()) == "custom_value"

    def test_deeply_nested(self) -> None:
        val = {"a": [{"b": (Path("/x"),)}, None]}
        expected = {"a": [{"b": ["/x"]}, None]}
        assert _json_safe(val) == expected
