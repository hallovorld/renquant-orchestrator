from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_rehearsal_plan import build_live_rehearsal_plan


def test_live_rehearsal_plan_reports_missing_alpaca_env(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    plan = build_live_rehearsal_plan(output_dir="/tmp/rehearsal")

    assert plan["ready"] is False
    assert plan["missing_env"] == ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
    assert plan["commands"]["bridge_capture"] == [
        "renquant-orchestrator",
        "run-job",
        "live_runner_bridge",
        "--",
        "--broker",
        "readonly-alpaca",
        "--once",
        "--bridge-bundle-output",
        "/tmp/rehearsal/live-bridge-bundle.json",
    ]
    assert "--fail-on-diff" in plan["commands"]["native_payload_parity"]


def test_daily_rehearsal_plan_uses_daily_bridge_job(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    plan = build_live_rehearsal_plan(mode="daily", output_dir="/tmp/rehearsal")

    assert plan["ready"] is True
    assert plan["commands"]["bridge_capture"][2] == "daily_live_runner_bridge"
    assert plan["artifacts"]["bridge_bundle"] == "/tmp/rehearsal/daily-bridge-bundle.json"


def test_live_rehearsal_plan_cli_strict_returns_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    rc = main([
        "live-rehearsal-plan",
        "--output-dir",
        "/tmp/rehearsal",
        "--strict",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["ready"] is False
    assert out["missing_env"] == ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
