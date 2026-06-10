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
        "--native-inference-payload-output",
        "/tmp/rehearsal/live-native-inference.json",
        "--bridge-bundle-output",
        "/tmp/rehearsal/live-bridge-bundle.json",
    ]
    assert plan["commands"]["native_execution_payload"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_execution_payload_fixture",
        "--",
        "--inference-json",
        "/tmp/rehearsal/live-native-inference.json",
        "--output-json",
        "/tmp/rehearsal/live-native-execution.json",
        "--broker-name",
        "readonly-alpaca",
    ]
    assert plan["commands"]["native_live_run_candidate"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_run_candidate",
        "--",
        "--inference-json",
        "/tmp/rehearsal/live-native-inference.json",
        "--output-json",
        "/tmp/rehearsal/live-native-bundle.json",
        "--broker-name",
        "readonly-alpaca",
        "--execution-output-json",
        "/tmp/rehearsal/live-native-execution.json",
    ]
    assert plan["commands"]["native_live_parity"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_parity_fixture",
        "--",
        "--bridge-bundle",
        "/tmp/rehearsal/live-bridge-bundle.json",
        "--native-bundle",
        "/tmp/rehearsal/live-native-bundle.json",
        "--output-json",
        "/tmp/rehearsal/live-parity-verdict.json",
        "--fail-on-diff",
    ]
    assert "--fail-on-diff" in plan["commands"]["native_payload_parity"]


def test_daily_rehearsal_plan_uses_daily_bridge_job(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    plan = build_live_rehearsal_plan(mode="daily", output_dir="/tmp/rehearsal")

    assert plan["ready"] is True
    assert plan["credential_source"] == "process_env"
    assert plan["commands"]["bridge_capture"][2] == "daily_live_runner_bridge"
    assert plan["artifacts"]["bridge_bundle"] == "/tmp/rehearsal/daily-bridge-bundle.json"


def test_live_rehearsal_plan_can_read_required_env_from_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_API_KEY=file-key\nexport ALPACA_SECRET_KEY='file-secret'\n",
        encoding="utf-8",
    )

    plan = build_live_rehearsal_plan(output_dir="/tmp/rehearsal", env_file=env_file)

    assert plan["ready"] is True
    assert plan["missing_env"] == []
    assert plan["credential_source"] == "env_file"
    assert plan["env_file"] == str(env_file)
    assert plan["env_file_exists"] is True
    assert "loads env_file" in plan["notes"][0]
    assert plan["commands"]["bridge_capture"][4:6] == ["--env-file", str(env_file)]
    assert "file-secret" not in json.dumps(plan)


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


def test_live_rehearsal_plan_cli_strict_accepts_env_file(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=key\nALPACA_SECRET_KEY=secret\n", encoding="utf-8")

    rc = main([
        "live-rehearsal-plan",
        "--output-dir",
        "/tmp/rehearsal",
        "--env-file",
        str(env_file),
        "--strict",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ready"] is True
    assert out["missing_env"] == []
