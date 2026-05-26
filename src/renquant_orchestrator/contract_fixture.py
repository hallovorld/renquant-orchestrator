"""Deterministic daily-run fixture for subrepo contract checks.

This is not alpha logic. It is a small no-network fixture that proves the
orchestrator can wire training, inference, execution, backtesting, and run
bundle persistence through the real subrepo package contracts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from renquant_execution import get_broker
from renquant_pipeline import PanelScoringJob, SelectionJob
from renquant_strategy_104 import load_strategy_config, strategy_manifest

from .daily import DailyRunContext, DailyRunPipeline


def fixture_data_manifest() -> dict[str, Any]:
    return {
        "dataset_id": "subrepo-smoke-daily-panel",
        "schema_version": "smoke-v1",
        "fingerprint": "sha256:smoke-data",
        "uri": "object://renquant-data/subrepo-smoke-daily-panel.parquet",
        "asset_class": "equity",
        "retention_class": "fixture",
    }


def run_contract_fixture(
    *,
    strategy_config_path: str | Path,
    output_dir: str | Path,
    run_id: str,
    as_of: str,
    code_commit: str = "uncommitted",
    broker_type: str = "paper",
    broker_name: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run the deterministic training-to-trading fixture and return summary."""
    strategy_path = Path(strategy_config_path)
    strategy_config = load_strategy_config(strategy_path)
    strategy_ref = strategy_manifest(strategy_path)
    data_manifest = fixture_data_manifest()
    calls: list[str] = []

    def loader(manifest: dict[str, Any]) -> dict[str, Any]:
        calls.append("load")
        return {"manifest": manifest, "rows": [1, 2, 3]}

    def trainer(
        dataset: Any,
        config: dict[str, Any],
        model_output_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append("train")
        model_output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "artifact_id": "subrepo-smoke-gbdt",
            "model_family": "gbdt-panel-ltr",
            "fingerprint": "sha256:smoke-model",
            "uri": "object://renquant-artifacts/subrepo-smoke-gbdt.json",
            "promotion_status": "candidate",
            "feature_cols": ["alpha_1", "alpha_2"],
            "trained_date": as_of,
            "config_fingerprint": config["config_fingerprint"],
            "panel_shape": {"rows": len(dataset["rows"]), "cols": 2},
            "lookahead_days": 5,
            "train_run_id": run_id,
            "oos_mean_ic": 0.0,
            "oos_std_ic": 0.0,
            "oos_per_fold_ic": [0.0, 0.0],
            "cv_method": "purged-walk-forward-smoke",
            "cv_embargo_days": 5,
        }, {"artifact_id": "subrepo-smoke-calibrator"}

    def validator(
        artifact: dict[str, Any],
        dataset: Any,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        calls.append("validate")
        return {"accepted": True, "oos_mean_ic": 0.0, "smoke": True}

    broker = get_broker(broker_type, initial_cash=100000.0)
    if broker_type == "paper":
        broker.broker_name = broker_name or "paper-smoke"
    elif broker_name is not None and broker.broker_name != broker_name:
        raise ValueError(
            f"broker_name={broker_name!r} does not match broker_type={broker_type!r} "
            f"({broker.broker_name!r})"
        )
    ctx = DailyRunContext(
        run_id=run_id,
        run_type="daily_full",
        strategy_config=strategy_config,
        strategy_manifest=strategy_ref,
        data_manifest=data_manifest,
        model_config={
            "strategy": "renquant_104",
            "objective": "rank:pairwise",
            "config_fingerprint": strategy_ref["fingerprint"],
            "code_commit": code_commit,
        },
        market_snapshot={
            "as_of": as_of,
            "feature_frame": {
                strategy_config["watchlist"][0]: {"alpha_1": 1.0, "alpha_2": 0.2}
            },
            "panel_scores": {strategy_config["watchlist"][0]: 0.42},
            "order_quantity_by_ticker": {strategy_config["watchlist"][0]: 1},
        },
        account_snapshot={"cash": 100000.0},
        output_dir=Path(output_dir),
        broker=broker,
        runtime_stages=[PanelScoringJob(), SelectionJob(), PanelScoringJob(emit_orders=True)],
        price_map={strategy_config["watchlist"][0]: 100.0},
        dry_run=dry_run,
    )
    DailyRunPipeline(
        loader,
        trainer,
        validator,
        backtest_runner=lambda bctx: {
            "ok": True,
            "n_orders": len(ctx.inference_context.order_intents),
        },
    ).run(ctx)
    if ctx.training_context is None or ctx.training_context.artifact_manifest is None:
        raise RuntimeError("fixture did not produce artifact_manifest")
    if ctx.inference_context is None or ctx.execution_context is None:
        raise RuntimeError("fixture did not produce inference/execution contexts")
    if not ctx.run_bundle:
        raise RuntimeError("fixture did not produce run_bundle")
    return {
        "ok": True,
        "broker_type": broker_type,
        "broker_name": ctx.execution_context.broker_name,
        "dry_run": dry_run,
        "training_calls": calls,
        "artifact_id": ctx.training_context.artifact_manifest["artifact_id"],
        "order_intents": ctx.inference_context.order_intents,
        "submitted_orders": ctx.execution_context.submitted_orders,
        "backtest_report": (
            ctx.backtest_context.report if ctx.backtest_context is not None else None
        ),
        "run_bundle_path": ctx.run_bundle["output_files"]["run_bundle"],
        "run_bundle_keys": sorted(ctx.run_bundle.keys()),
    }
