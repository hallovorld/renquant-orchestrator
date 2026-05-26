from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from renquant_common import Task
from renquant_execution import PaperBroker
from renquant_model_gbdt import train_panel_ltr_artifact, validate_panel_ltr_artifact
from renquant_orchestrator import DailyRunContext, DailyRunPipeline
from renquant_pipeline import stamp_order_attribution


class ScoreTask(Task):
    def run(self, ctx) -> bool | None:
        ctx.scores = {"AAPL": 0.7, "MSFT": 0.2}
        ctx.decision_trace.append({"stage": "score", "ticker": "AAPL", "score": 0.7})
        return True


class SelectTask(Task):
    def run(self, ctx) -> bool | None:
        ctx.order_intents.append(
            stamp_order_attribution(
                {"ticker": "AAPL", "action": "buy", "quantity": 2},
                ctx,
                source_job="FixtureSelectionJob",
                source_task=type(self).__name__,
                acceptance_reason="unit_test_selected",
                decision_inputs={"score": ctx.scores["AAPL"]},
            )
        )
        ctx.decision_trace.append({"stage": "select", "ticker": "AAPL", "quantity": 2})
        return True


class BareSelectTask(Task):
    def run(self, ctx) -> bool | None:
        ctx.order_intents.append({"ticker": "AAPL", "action": "buy", "quantity": 2})
        return True


def _strategy_config() -> dict[str, Any]:
    return {
        "watchlist": ["AAPL", "MSFT"],
        "ranking": {"panel_scoring": {"enabled": True}},
        "regime_params": {"BULL_CALM": {"disable_new_buys": False}},
        "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
    }


def _strategy_manifest() -> dict[str, Any]:
    return {
        "strategy": "renquant_104",
        "config_name": "strategy_config.json",
        "fingerprint": "sha256:strategy",
        "watchlist_size": 2,
    }


def _data_manifest() -> dict[str, Any]:
    return {
        "dataset_id": "daily-fixture",
        "schema_version": "fixture-v1",
        "fingerprint": "sha256:data",
        "uri": "object://renquant-data/daily-fixture.parquet",
        "asset_class": "equity",
    }


def _loader(manifest: dict[str, Any]) -> dict[str, Any]:
    return {"rows": [1, 2, 3], "manifest": manifest}


def _trainer(dataset: Any, config: dict[str, Any], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "artifact_id": "gbdt-fixture",
        "model_family": "gbdt-panel-ltr",
        "fingerprint": "sha256:model",
        "uri": "object://renquant-artifacts/gbdt-fixture.json",
        "promotion_status": "candidate",
        "feature_cols": ["alpha_1", "alpha_2"],
        "trained_date": "2026-05-25",
        "config_fingerprint": config["config_fingerprint"],
        "panel_shape": {"rows": len(dataset["rows"]), "cols": 2},
        "lookahead_days": 5,
        "train_run_id": "daily-fixture-run",
        "oos_mean_ic": 0.03,
        "oos_std_ic": 0.01,
        "oos_per_fold_ic": [0.02, 0.04],
        "cv_method": "purged-walk-forward",
        "cv_embargo_days": 5,
    }, {"kind": "global_calibrator"}


def _validator(artifact: dict[str, Any], dataset: Any, config: dict[str, Any]) -> dict[str, Any]:
    return {"accepted": False, "oos_mean_ic": 0.03}


def test_daily_run_pipeline_flows_from_training_to_trading_and_bundle(tmp_path: Path) -> None:
    broker = PaperBroker(initial_cash=100_000.0)
    ctx = DailyRunContext(
        run_id="daily-2026-05-25",
        run_type="daily_full",
        strategy_config=_strategy_config(),
        strategy_manifest=_strategy_manifest(),
        data_manifest=_data_manifest(),
        model_config={"objective": "rank:pairwise"},
        market_snapshot={"as_of": "2026-05-25"},
        output_dir=tmp_path / "run",
        broker=broker,
        runtime_stages=[ScoreTask(), SelectTask()],
        price_map={"AAPL": 100.0},
        dry_run=False,
    )

    result = DailyRunPipeline(
        _loader,
        _trainer,
        _validator,
        backtest_runner=lambda bctx: {"ok": True, "n_orders": 1},
    ).run(ctx)

    assert result.ok is True
    assert result.name == "daily-training-to-trading"
    assert ctx.training_context is not None
    assert ctx.inference_context is not None
    assert ctx.execution_context is not None
    assert ctx.execution_context.submitted_orders[0]["status"] == "filled"
    assert broker.get_position("AAPL") == pytest.approx(2.0)
    assert ctx.run_bundle["artifact_manifest"]["artifact_id"] == "gbdt-fixture"
    assert ctx.run_bundle["submitted_orders"][0]["order_id"] == "PAPER-0001"
    assert (tmp_path / "run" / "run_bundle.json").exists()

    bundle = json.loads((tmp_path / "run" / "run_bundle.json").read_text())
    assert bundle["run_id"] == "daily-2026-05-25"
    assert bundle["decision_trace"][0]["stage"] == "score"
    assert bundle["order_intents"][0]["attribution"]["source_job"] == "FixtureSelectionJob"
    assert bundle["backtest_report"] == {"ok": True, "n_orders": 1}


def test_daily_run_pipeline_requires_execution_prices_for_orders(tmp_path: Path) -> None:
    ctx = DailyRunContext(
        run_id="daily-2026-05-25",
        run_type="daily_full",
        strategy_config=_strategy_config(),
        strategy_manifest=_strategy_manifest(),
        data_manifest=_data_manifest(),
        model_config={"objective": "rank:pairwise"},
        market_snapshot={"as_of": "2026-05-25"},
        output_dir=tmp_path / "run",
        broker=PaperBroker(),
        runtime_stages=[ScoreTask(), SelectTask()],
        price_map={},
        dry_run=False,
    )

    with pytest.raises(ValueError, match="price_map missing execution price for AAPL"):
        DailyRunPipeline(_loader, _trainer, _validator).run(ctx)


def test_daily_run_pipeline_rejects_unattributed_order_intents(tmp_path: Path) -> None:
    ctx = DailyRunContext(
        run_id="daily-2026-05-25",
        run_type="daily_full",
        strategy_config=_strategy_config(),
        strategy_manifest=_strategy_manifest(),
        data_manifest=_data_manifest(),
        model_config={"objective": "rank:pairwise"},
        market_snapshot={"as_of": "2026-05-25"},
        output_dir=tmp_path / "run",
        broker=PaperBroker(),
        runtime_stages=[ScoreTask(), BareSelectTask()],
        price_map={"AAPL": 100.0},
        dry_run=False,
    )

    with pytest.raises(ValueError, match="order missing attribution"):
        DailyRunPipeline(_loader, _trainer, _validator).run(ctx)


def test_daily_run_pipeline_rejects_unfingerprinted_strategy(tmp_path: Path) -> None:
    ctx = DailyRunContext(
        run_id="daily-2026-05-25",
        run_type="daily_full",
        strategy_config=_strategy_config(),
        strategy_manifest={"strategy": "renquant_104"},
        data_manifest=_data_manifest(),
        model_config={"objective": "rank:pairwise"},
        market_snapshot={"as_of": "2026-05-25"},
        output_dir=tmp_path / "run",
        broker=PaperBroker(),
        runtime_stages=[ScoreTask()],
    )

    with pytest.raises(ValueError, match="strategy_manifest missing fingerprint"):
        DailyRunPipeline(_loader, _trainer, _validator).run(ctx)


def test_daily_run_pipeline_real_gbdt_to_panel_scoring_to_paper_fill(tmp_path: Path) -> None:
    from renquant_pipeline import PanelScoringJob, SelectionJob

    dataset = _real_panel_dataset()
    strategy_config = {
        "watchlist": ["AAPL", "MSFT"],
        "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
        "ranking": {"panel_scoring": {"enabled": True, "buy_floor": 0.0}},
        "execution": {"default_quantity": 1},
    }
    broker = PaperBroker(initial_cash=100_000.0)
    ctx = DailyRunContext(
        run_id="daily-real-gbdt-fixture",
        run_type="daily_full",
        strategy_config=strategy_config,
        strategy_manifest=_strategy_manifest(),
        data_manifest=_data_manifest(),
        model_config={
            "strategy": "renquant_104",
            "backend": "xgboost",
            "objective": "rank:pairwise",
            "config_fingerprint": _strategy_manifest()["fingerprint"],
            "code_commit": "unit-real-gbdt",
            "train_run_id": "daily-real-gbdt-fixture",
            "artifact_id": "daily-real-gbdt-fixture",
            "lookahead_days": 2,
            "cv_embargo_days": 2,
            "cv_n_splits": 3,
            "num_boost_round": 12,
            "cv_num_boost_round": 6,
            "feature_cols": ["alpha_1", "alpha_2"],
            "feature_means": [0.0, 0.0],
            "feature_stds": [1.0, 1.0],
            "feature_norm_kind": ["legacy_full_z", "legacy_full_z"],
            "feature_source_space": "raw",
            "xgb_params": {"max_depth": 2, "eta": 0.2, "nthread": 1, "seed": 11},
            "acceptance_min_oos_ic": -1.0,
        },
        market_snapshot={
            "as_of": "2026-05-25",
            "raw_feature_frame": {
                "AAPL": {"alpha_1": 1.0, "alpha_2": 0.1},
                "MSFT": {"alpha_1": -1.0, "alpha_2": 0.0},
            },
            "order_quantity_by_ticker": {"AAPL": 1, "MSFT": 1},
        },
        output_dir=tmp_path / "run",
        broker=broker,
        runtime_stages=[PanelScoringJob(), SelectionJob(), PanelScoringJob(emit_orders=True)],
        price_map={"AAPL": 100.0, "MSFT": 100.0},
        dry_run=False,
    )

    result = DailyRunPipeline(
        lambda manifest: dataset,
        train_panel_ltr_artifact,
        validate_panel_ltr_artifact,
        backtest_runner=lambda bctx: {"ok": True, "n_orders": len(ctx.inference_context.order_intents)},
    ).run(ctx)

    assert result.ok is True
    assert ctx.training_context is not None
    assert ctx.training_context.artifact_manifest is not None
    assert ctx.training_context.artifact_manifest["local_artifact_path"]
    assert ctx.training_context.artifact_manifest["feature_source_space"] == "raw"
    assert ctx.inference_context is not None
    assert ctx.inference_context.scores["AAPL"] > ctx.inference_context.scores["MSFT"]
    assert ctx.inference_context.order_intents
    assert all("attribution" in order for order in ctx.inference_context.order_intents)
    assert ctx.execution_context is not None
    assert ctx.execution_context.submitted_orders
    assert ctx.run_bundle["order_intents"][0]["attribution"]["source_job"] == "PanelScoringJob"


def _real_panel_dataset() -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    rows: list[dict[str, Any]] = []
    tickers = ["AAPL", "MSFT", "GOOG", "IBM"]
    for day in range(18):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=day)
        for idx, ticker in enumerate(tickers):
            alpha_1 = 1.5 - idx + 0.01 * day
            alpha_2 = ((day % 3) - 1) * 0.1
            rows.append({
                "date": date,
                "ticker": ticker,
                "alpha_1": alpha_1,
                "alpha_2": alpha_2,
                "label": alpha_1 + 0.05 * alpha_2,
                "weight": 1.0,
            })
    panel = pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)
    group_sizes = panel.groupby("date", sort=False).size().to_numpy(dtype=np.int32)
    return {
        "panel": panel,
        "group_sizes": group_sizes,
        "feature_cols": ["alpha_1", "alpha_2"],
    }
