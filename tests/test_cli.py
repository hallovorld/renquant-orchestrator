from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main


def _strategy_config(path: Path) -> None:
    path.write_text(
        json.dumps({
            "watchlist": ["AAPL", "MSFT"],
            "benchmark": "AAPL",
            "regime_params": {
                "BULL_CALM": {"disable_new_buys": False},
                "BULL_VOLATILE": {"disable_new_buys": False},
                "BULL_STRONG": {"disable_new_buys": False},
                "BEAR": {"disable_new_buys": False},
                "CHOPPY": {"disable_new_buys": False},
            },
            "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
            "ranking": {
                "panel_scoring": {
                    "enabled": True,
                    "kind": "xgb",
                    "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
                    "global_calibration": {
                        "enabled": True,
                        "artifact_path": "artifacts/prod/panel-rank-calibration.json",
                    },
                }
            },
        }),
        encoding="utf-8",
    )


def test_daily_contract_cli_writes_run_bundle(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "strategy_config.json"
    out = tmp_path / "out"
    _strategy_config(cfg)

    rc = main([
        "daily-contract",
        "--strategy-config",
        str(cfg),
        "--output-dir",
        str(out),
        "--run-id",
        "cli-fixture",
        "--as-of",
        "2026-05-26",
        "--code-commit",
        "sha-fixture",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["broker_type"] == "paper"
    assert summary["broker_name"] == "paper-smoke"
    assert summary["training_calls"] == ["load", "train", "validate"]
    assert Path(summary["run_bundle_path"]).exists()
    bundle = json.loads(Path(summary["run_bundle_path"]).read_text())
    assert bundle["run_id"] == "cli-fixture"
    assert bundle["order_intents"][0]["attribution"]["source_job"] == "PanelScoringJob"
    assert (
        bundle["order_intents"][0]["attribution"]["source_task"]
        == "EmitAttributedOrderIntentsTask"
    )
    assert bundle["submitted_orders"][0]["status"] == "dry_run"


def test_daily_contract_cli_execute_uses_paper_fill(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "strategy_config.json"
    out = tmp_path / "out"
    _strategy_config(cfg)

    rc = main([
        "daily-contract",
        "--strategy-config",
        str(cfg),
        "--output-dir",
        str(out),
        "--run-id",
        "cli-execute-fixture",
        "--as-of",
        "2026-05-26",
        "--broker-type",
        "paper",
        "--broker-name",
        "paper-test",
        "--execute",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is False
    assert summary["broker_name"] == "paper-test"
    assert summary["submitted_orders"][0]["status"] == "filled"
    assert summary["submitted_orders"][0]["price"] == 100.0
