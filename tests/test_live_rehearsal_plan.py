from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_rehearsal_plan import build_live_rehearsal_plan


def test_live_rehearsal_plan_reports_missing_alpaca_env(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.setenv("RENQUANT_REPO_ROOT", "/private/tmp/RenQuant")

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
    assert plan["commands"]["native_live_inference"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_inference_fixture",
        "--",
        "--context-json",
        "/tmp/rehearsal/live-native-context.json",
        "--output-json",
        "/tmp/rehearsal/live-native-inference.json",
    ]
    assert plan["commands"]["native_live_context"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_context_fixture",
        "--",
        "--strategy-config-json",
        "/private/tmp/RenQuant/backtesting/renquant_104/strategy_config.json",
        "--market-snapshot-json",
        "/tmp/rehearsal/live-market-snapshot.json",
        "--account-snapshot-json",
        "/tmp/rehearsal/live-account-snapshot.json",
        "--output-json",
        "/tmp/rehearsal/live-native-context.json",
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
        "--strategy-dir",
        "/private/tmp/RenQuant/backtesting/renquant_104",
        "--runs-db",
        "/private/tmp/RenQuant/data/runs.alpaca.db",
        "--live-state-broker-name",
        "alpaca",
        "--live-state-contract-output-json",
        "/tmp/rehearsal/live-live-state-contract.json",
        "--execution-output-json",
        "/tmp/rehearsal/live-native-execution.json",
        "--commit-plan-output-json",
        "/tmp/rehearsal/live-native-commit-plan.json",
    ]
    assert plan["artifacts"]["native_commit_plan"] == "/tmp/rehearsal/live-native-commit-plan.json"
    assert plan["artifacts"]["market_snapshot"] == "/tmp/rehearsal/live-market-snapshot.json"
    assert plan["artifacts"]["account_snapshot"] == "/tmp/rehearsal/live-account-snapshot.json"
    assert plan["artifacts"]["native_context"] == "/tmp/rehearsal/live-native-context.json"
    assert plan["artifacts"]["live_state_contract"] == "/tmp/rehearsal/live-live-state-contract.json"
    assert plan["artifacts"]["native_live_commit_plan"] == (
        "/tmp/rehearsal/live-native-live-commit-plan.json"
    )
    assert plan["persistence_targets"] == {
        "live_state": "/private/tmp/RenQuant/backtesting/renquant_104/live_state.alpaca.json",
        "trade_journal": (
            "/private/tmp/RenQuant/live/logs/renquant-104/"
            "native-trade-journal.alpaca.jsonl"
        ),
        "lifecycle_journal": (
            "/private/tmp/RenQuant/live/logs/renquant-104/"
            "native-order-lifecycle.alpaca.jsonl"
        ),
        "runs_db": "/private/tmp/RenQuant/data/runs.alpaca.db",
    }
    assert plan["required_operator_inputs"] == [
        {
            "placeholder": "<RUN_ID>",
            "description": (
                "unique native live run id used for persistence audit and "
                "live_state_snapshots"
            ),
        }
    ]
    assert plan["commands"]["native_live_commit_template"] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_run_candidate",
        "--",
        "--inference-json",
        "/tmp/rehearsal/live-native-inference.json",
        "--execution-output-json",
        "/tmp/rehearsal/live-native-live-commit-execution.json",
        "--commit-plan-output-json",
        "/tmp/rehearsal/live-native-live-commit-plan.json",
        "--output-json",
        "/tmp/rehearsal/live-native-live-commit-bundle.json",
        "--run-id",
        "<RUN_ID>",
        "--broker-name",
        "alpaca",
        "--execute-live",
        "--commit-persistence",
        "--live-state-output-json",
        "/private/tmp/RenQuant/backtesting/renquant_104/live_state.alpaca.json",
        "--trade-journal-output-json",
        (
            "/private/tmp/RenQuant/live/logs/renquant-104/"
            "native-trade-journal.alpaca.jsonl"
        ),
        "--lifecycle-journal-output-json",
        (
            "/private/tmp/RenQuant/live/logs/renquant-104/"
            "native-order-lifecycle.alpaca.jsonl"
        ),
        "--strategy-dir",
        "/private/tmp/RenQuant/backtesting/renquant_104",
        "--runs-db",
        "/private/tmp/RenQuant/data/runs.alpaca.db",
        "--live-state-broker-name",
        "alpaca",
        "--live-state-strategy",
        "renquant_104",
        "--live-state-contract-output-json",
        "/tmp/rehearsal/live-native-live-commit-state-contract.json",
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
    assert plan["commands"]["native_live_commit_template"][4:6] == [
        "--inference-json",
        "/tmp/rehearsal/daily-native-inference.json",
    ]


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
