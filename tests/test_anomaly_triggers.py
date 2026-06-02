from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import anomaly_triggers as mod


def test_pipeline_shape_is_single_market_move_job() -> None:
    pipeline = mod.build_pipeline()

    assert pipeline.name == "market-anomaly-retrain-triggers"
    assert [type(job).__name__ for job in pipeline.jobs] == ["MarketMoveJob"]
    assert [type(task).__name__ for task in pipeline.jobs[0].tasks] == [
        "FetchMarketMovesTask",
        "EvaluateAnomalyTriggersTask",
    ]


def test_pct_change_from_closes_requires_valid_prior_close() -> None:
    assert mod.pct_change_from_closes([100.0, 103.0]) == pytest.approx(0.03)
    assert mod.pct_change_from_closes([0.0, 103.0]) is None
    assert mod.pct_change_from_closes([100.0]) is None


def test_pipeline_fetches_spy_and_vix_trigger_tags() -> None:
    seen: list[str] = []

    def fetch(symbol: str) -> float | None:
        seen.append(symbol)
        return {"SPY": -0.031, "^VIX": 0.061}[symbol]

    ctx = mod.AnomalyTriggerContext(fetch_pct_change=fetch)

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert seen == ["SPY", "^VIX"]
    assert ctx.changes == {"SPY": -0.031, "VIX": 0.061}
    assert ctx.triggers == ["anomaly_spy_2pct", "anomaly_vix_5pct"]


def test_yfinance_is_market_data_extra_not_base_dependency() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    base_deps = pyproject.split("[project.optional-dependencies]", 1)[0]

    assert '"yfinance>=0.2.40"' not in base_deps
    assert "[project.optional-dependencies]" in pyproject
    assert "market-data" in pyproject
    assert '"yfinance>=0.2.40"' in pyproject


def test_evaluate_triggers_respects_custom_threshold_tags() -> None:
    assert mod.evaluate_triggers(
        spy_change=0.016,
        vix_change=0.071,
        spy_pct=0.015,
        vix_pct=0.07,
    ) == ["anomaly_spy_15bp", "anomaly_vix_70bp"]


def test_main_dry_run_prints_triggers_but_returns_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mod, "fetch_yfinance_pct_change", lambda symbol: {"SPY": 0.04, "^VIX": 0.0}[symbol])

    assert mod.main(["--dry-run"]) == 0

    assert capsys.readouterr().out.strip() == "anomaly_spy_2pct"


def test_main_json_emits_changes_and_exit_one_on_trigger(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mod, "fetch_yfinance_pct_change", lambda symbol: {"SPY": 0.0, "^VIX": 0.06}[symbol])

    assert mod.main(["--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["changes"] == {"SPY": 0.0, "VIX": 0.06}
    assert payload["triggers"] == ["anomaly_vix_5pct"]
