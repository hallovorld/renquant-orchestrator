"""Daily training-to-trading orchestration over pinned RenQuant subrepos."""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from renquant_artifacts import hash_jsonable
from renquant_backtesting import BacktestContext, BacktestPipeline
from renquant_common import Job, Pipeline, PipelineResult, Task
from renquant_execution import BaseBroker, BrokerExecutionPipeline, ExecutionContext
from renquant_model_gbdt import PanelGbdtTrainingPipeline, TrainingContext
from renquant_pipeline import InferenceContext, RuntimeInferencePipeline


DatasetLoader = Callable[[dict[str, Any]], Any]
Trainer = Callable[[Any, dict[str, Any], Path], tuple[dict[str, Any], dict[str, Any]]]
Validator = Callable[[dict[str, Any], Any, dict[str, Any]], dict[str, Any]]
BacktestRunner = Callable[[BacktestContext], dict[str, Any]]


@dataclass
class DailyRunContext:
    """Mutable context for one full subrepo daily run."""

    run_id: str
    run_type: str
    strategy_config: dict[str, Any]
    strategy_manifest: dict[str, Any]
    data_manifest: dict[str, Any]
    model_config: dict[str, Any]
    market_snapshot: dict[str, Any]
    output_dir: Path
    broker: BaseBroker
    runtime_stages: Sequence[Task]
    account_snapshot: dict[str, Any] = field(default_factory=dict)
    price_map: dict[str, float] = field(default_factory=dict)
    dry_run: bool = True

    training_context: TrainingContext | None = None
    inference_context: InferenceContext | None = None
    execution_context: ExecutionContext | None = None
    backtest_context: BacktestContext | None = None
    run_bundle: dict[str, Any] = field(default_factory=dict)
    stage_trace: list[dict[str, Any]] = field(default_factory=list)


class ValidateDailyInputsTask(Task):
    """Fail fast before any training or broker-stage work starts."""

    def run(self, ctx: DailyRunContext) -> bool | None:
        if not ctx.run_id:
            raise ValueError("run_id is required")
        if ctx.run_type not in {"daily_full", "daily_shadow", "manual_full"}:
            raise ValueError(f"unsupported run_type: {ctx.run_type!r}")
        if not ctx.strategy_config.get("watchlist"):
            raise ValueError("strategy_config missing watchlist")
        for name, manifest in (
            ("strategy_manifest", ctx.strategy_manifest),
            ("data_manifest", ctx.data_manifest),
        ):
            if not manifest.get("fingerprint"):
                raise ValueError(f"{name} missing fingerprint")
        if not ctx.market_snapshot.get("as_of"):
            raise ValueError("market_snapshot missing as_of")
        if not ctx.broker.broker_name:
            raise ValueError("broker must expose broker_name")
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        ctx.stage_trace.append({"stage": "validate_daily_inputs", "ok": True})
        return True


class TrainGbdtArtifactTask(Task):
    def __init__(self, loader: DatasetLoader, trainer: Trainer, validator: Validator) -> None:
        self.loader = loader
        self.trainer = trainer
        self.validator = validator

    def run(self, ctx: DailyRunContext) -> bool | None:
        started = time.monotonic()
        model_config = dict(ctx.model_config)
        model_config.setdefault("strategy", ctx.strategy_manifest.get("strategy", "renquant_104"))
        model_config.setdefault("config_fingerprint", ctx.strategy_manifest["fingerprint"])
        training_ctx = TrainingContext(
            dataset_manifest=ctx.data_manifest,
            model_config=model_config,
            output_dir=ctx.output_dir / "training",
        )
        result = PanelGbdtTrainingPipeline(self.loader, self.trainer, self.validator).run(training_ctx)
        if training_ctx.artifact_manifest is None:
            raise ValueError("training did not produce artifact_manifest")
        ctx.training_context = training_ctx
        ctx.stage_trace.append({
            "stage": "train_gbdt",
            "ok": result.ok,
            "elapsed_sec": time.monotonic() - started,
            "pipeline": _pipeline_result(result),
            "artifact_id": training_ctx.artifact_manifest["artifact_id"],
        })
        return True


class RunRuntimeInferenceTask(Task):
    def run(self, ctx: DailyRunContext) -> bool | None:
        if ctx.training_context is None or ctx.training_context.artifact_manifest is None:
            raise ValueError("training_context.artifact_manifest is required before inference")
        started = time.monotonic()
        inference_ctx = InferenceContext(
            strategy_config=ctx.strategy_config,
            data_manifest=ctx.data_manifest,
            artifact_manifest=ctx.training_context.artifact_manifest,
            market_snapshot=ctx.market_snapshot,
            account_snapshot=ctx.account_snapshot,
        )
        result = RuntimeInferencePipeline(list(ctx.runtime_stages)).run(inference_ctx)
        ctx.inference_context = inference_ctx
        ctx.stage_trace.append({
            "stage": "runtime_inference",
            "ok": result.ok,
            "elapsed_sec": time.monotonic() - started,
            "pipeline": _pipeline_result(result),
            "n_order_intents": len(inference_ctx.order_intents),
            "n_decision_trace": len(inference_ctx.decision_trace),
        })
        return True


class ExecuteOrderIntentsTask(Task):
    def run(self, ctx: DailyRunContext) -> bool | None:
        if ctx.inference_context is None:
            raise ValueError("inference_context is required before execution")
        started = time.monotonic()
        ctx.broker.connect()
        try:
            for intent in ctx.inference_context.order_intents:
                symbol = intent.get("symbol") or intent.get("ticker")
                if symbol and hasattr(ctx.broker, "set_price"):
                    if symbol not in ctx.price_map:
                        raise ValueError(f"price_map missing execution price for {symbol}")
                    ctx.broker.set_price(str(symbol), float(ctx.price_map[symbol]))
            execution_ctx = ExecutionContext(
                broker_name=ctx.broker.broker_name,
                order_intents=list(ctx.inference_context.order_intents),
                dry_run=ctx.dry_run,
            )
            result = BrokerExecutionPipeline(ctx.broker).run(execution_ctx)
        finally:
            ctx.broker.disconnect()
        ctx.execution_context = execution_ctx
        ctx.stage_trace.append({
            "stage": "execute_order_intents",
            "ok": result.ok,
            "elapsed_sec": time.monotonic() - started,
            "pipeline": _pipeline_result(result),
            "n_submitted": len(execution_ctx.submitted_orders),
            "dry_run": ctx.dry_run,
        })
        return True


class RunBacktestCheckTask(Task):
    def __init__(self, runner: BacktestRunner | None) -> None:
        self.runner = runner

    def run(self, ctx: DailyRunContext) -> bool | None:
        if self.runner is None:
            ctx.stage_trace.append({"stage": "backtest_check", "skipped": True})
            return True
        if ctx.training_context is None or ctx.training_context.artifact_manifest is None:
            raise ValueError("training artifact manifest is required before backtest")
        started = time.monotonic()
        backtest_ctx = BacktestContext(
            strategy_manifest=ctx.strategy_manifest,
            data_manifest=ctx.data_manifest,
            artifact_manifest=ctx.training_context.artifact_manifest,
            output_dir=ctx.output_dir / "backtest",
        )
        result = BacktestPipeline(self.runner).run(backtest_ctx)
        ctx.backtest_context = backtest_ctx
        ctx.stage_trace.append({
            "stage": "backtest_check",
            "ok": result.ok,
            "elapsed_sec": time.monotonic() - started,
            "pipeline": _pipeline_result(result),
            "report": backtest_ctx.report,
        })
        return True


class PersistDailyRunBundleTask(Task):
    def run(self, ctx: DailyRunContext) -> bool | None:
        if ctx.training_context is None or ctx.training_context.artifact_manifest is None:
            raise ValueError("training artifact manifest is required before bundle persistence")
        if ctx.inference_context is None or ctx.execution_context is None:
            raise ValueError("inference and execution contexts are required before bundle persistence")
        bundle = {
            "schema_version": 1,
            "run_id": ctx.run_id,
            "run_type": ctx.run_type,
            "dry_run": ctx.dry_run,
            "strategy_manifest": ctx.strategy_manifest,
            "strategy_config_hash": hash_jsonable(ctx.strategy_config),
            "data_manifest": ctx.data_manifest,
            "artifact_manifest": ctx.training_context.artifact_manifest,
            "market_snapshot": ctx.market_snapshot,
            "account_snapshot": ctx.account_snapshot,
            "decision_trace": list(ctx.inference_context.decision_trace),
            "order_intents": list(ctx.inference_context.order_intents),
            "submitted_orders": list(ctx.execution_context.submitted_orders),
            "execution_audit": list(ctx.execution_context.audit_rows),
            "backtest_report": (
                dict(ctx.backtest_context.report)
                if ctx.backtest_context is not None
                else None
            ),
            "stage_trace": list(ctx.stage_trace),
        }
        out = ctx.output_dir / "run_bundle.json"
        decisions = ctx.output_dir / "decision_trace.json"
        orders = ctx.output_dir / "submitted_orders.json"
        _write_json(out, bundle)
        _write_json(decisions, bundle["decision_trace"])
        _write_json(orders, bundle["submitted_orders"])
        bundle["output_files"] = {
            "run_bundle": str(out),
            "decision_trace": str(decisions),
            "submitted_orders": str(orders),
        }
        _write_json(out, bundle)
        ctx.run_bundle = bundle
        ctx.stage_trace.append({"stage": "persist_daily_run_bundle", "ok": True})
        return True


class DailyRunJob(Job):
    def __init__(
        self,
        loader: DatasetLoader,
        trainer: Trainer,
        validator: Validator,
        backtest_runner: BacktestRunner | None,
    ) -> None:
        self._tasks = [
            ValidateDailyInputsTask(),
            TrainGbdtArtifactTask(loader, trainer, validator),
            RunRuntimeInferenceTask(),
            ExecuteOrderIntentsTask(),
            RunBacktestCheckTask(backtest_runner),
            PersistDailyRunBundleTask(),
        ]

    @property
    def tasks(self) -> list[Task]:
        return self._tasks


class DailyRunPipeline(Pipeline):
    """Full subrepo flow from model training to broker-facing execution."""

    def __init__(
        self,
        loader: DatasetLoader,
        trainer: Trainer,
        validator: Validator,
        *,
        backtest_runner: BacktestRunner | None = None,
    ) -> None:
        super().__init__(
            [DailyRunJob(loader, trainer, validator, backtest_runner)],
            name="daily-training-to-trading",
        )


def _pipeline_result(result: PipelineResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "ok": result.ok,
        "elapsed_sec": result.elapsed_sec,
        "steps": [
            {
                "job_name": step.job_name,
                "skipped": step.skipped,
                "elapsed_sec": step.elapsed_sec,
            }
            for step in result.steps
        ],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
