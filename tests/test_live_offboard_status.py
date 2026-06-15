from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_offboard_status import build_live_offboard_status


def _native_inference_payload(
    *,
    producer_source: str = "renquant_orchestrator.native_inference",
) -> dict:
    return {
        "schema_version": 1,
        "source": "renquant_pipeline.live_context_inference",
        "metadata": {
            "native_inference_producer": {
                "source": producer_source,
            }
        },
    }


def test_live_offboard_status_reports_env_and_bridge_blockers(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    status = build_live_offboard_status(output_dir="/tmp/rehearsal")

    assert status["ready_for_live_offboard"] is False
    assert "ALPACA_API_KEY" in status["blocking_reasons"]
    assert "ALPACA_SECRET_KEY" in status["blocking_reasons"]
    assert "missing_bridge_bundle" in status["blocking_reasons"]
    assert "missing_native_inference_payload" in status["blocking_reasons"]
    assert "missing_native_execution_payload" in status["blocking_reasons"]
    assert "missing_native_commit_plan" in status["blocking_reasons"]
    assert "missing_native_bundle" in status["blocking_reasons"]
    assert "missing_live_state_contract" in status["blocking_reasons"]
    assert "missing_parity_verdict" in status["blocking_reasons"]
    assert "remaining_umbrella_bridge_jobs" in status["blocking_reasons"]
    assert status["stage_status"]["current_stage"] == "credential_preflight"
    assert status["stage_status"]["next_blocker"] == "missing_required_credentials"
    assert status["scheduled_jobs_summary"]["remaining_umbrella_bridge_job_count"] == 2
    assert [job["job_id"] for job in status["remaining_bridge_jobs"]] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert status["rehearsal"]["commands"]["bridge_capture"][2] == "live_runner_bridge"
    assert status["artifact_status"]["bridge_bundle"] == {
        "path": "/tmp/rehearsal/live-bridge-bundle.json",
        "exists": False,
    }
    assert "native_live_run_candidate" in " ".join(status["next_actions"])
    assert status["remaining_bridge_jobs"][0]["native_replacement_job_id"] == (
        "native_live_run_candidate"
    )
    assert "--commit-plan-output-json" in status["remaining_bridge_jobs"][0][
        "native_cutover_command"
    ]
    assert status["cutover_execution_packet"]["ready_to_execute"] is False
    assert status["cutover_execution_packet"]["ready_for_readonly_validation"] is False


def test_live_offboard_status_reports_existing_parity_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    verdict = tmp_path / "live-parity-verdict.json"
    verdict.write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    parity_status = status["artifact_status"]["parity_verdict"]
    assert parity_status["path"] == str(verdict)
    assert parity_status["exists"] is True
    assert parity_status["ok"] is True
    assert parity_status["size_bytes"] > 0


def test_daily_live_offboard_status_uses_daily_rehearsal(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    status = build_live_offboard_status(mode="daily", output_dir="/tmp/rehearsal")

    assert status["ready_for_live_offboard"] is False
    assert "remaining_umbrella_bridge_jobs" in status["blocking_reasons"]
    assert status["rehearsal"]["ready"] is True
    assert status["rehearsal"]["commands"]["bridge_capture"][2] == "daily_live_runner_bridge"
    assert status["stage_status"]["current_stage"] == "bridge_capture"


def test_live_offboard_status_env_file_clears_credential_blockers(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=key\nALPACA_SECRET_KEY=secret\n", encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path, env_file=env_file)

    assert status["ready_for_live_offboard"] is False
    assert "remaining_umbrella_bridge_jobs" in status["blocking_reasons"]
    assert "ALPACA_SECRET_KEY" not in status["blocking_reasons"]
    assert status["rehearsal"]["ready"] is True
    assert status["rehearsal"]["missing_env"] == []
    assert "secret" not in json.dumps(status)


def test_live_offboard_status_reports_bridge_capture_stage(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    bridge = tmp_path / "live-bridge-bundle.json"
    bridge.write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert status["stage_status"]["current_stage"] == "native_payload_generation"
    assert status["stage_status"]["next_blocker"] == "missing_native_payloads"
    assert status["stage_status"]["checks"]["bridge_capture_ready"] is True
    assert status["stage_status"]["checks"]["native_payloads_ready"] is False


def test_live_offboard_status_blocks_bridge_produced_native_inference(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    (tmp_path / "live-bridge-bundle.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "live-native-inference.json").write_text(
        json.dumps(_native_inference_payload(producer_source="live_runner_bridge_hook")),
        encoding="utf-8",
    )

    status = build_live_offboard_status(output_dir=tmp_path)

    assert "native_inference_producer_is_bridge" in status["blocking_reasons"]
    assert status["stage_status"]["current_stage"] == "native_inference_producer"
    assert status["stage_status"]["next_blocker"] == "native_inference_producer_is_bridge"
    assert status["stage_status"]["checks"]["native_inference_producer_ready"] is False
    inference_status = status["artifact_status"]["native_inference_payload"]
    assert inference_status["producer_source"] == "live_runner_bridge_hook"
    assert inference_status["bridge_produced"] is True


def test_live_offboard_status_blocks_unknown_native_inference_producer(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    (tmp_path / "live-bridge-bundle.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "live-native-inference.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert "native_inference_producer_unknown" in status["blocking_reasons"]
    assert status["stage_status"]["current_stage"] == "native_inference_producer"
    assert status["stage_status"]["next_blocker"] == "native_inference_producer_unknown"


def test_live_offboard_status_requires_valid_live_state_contract_before_parity(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    for name in (
        "live-bridge-bundle.json",
        "live-native-inference.json",
        "live-native-execution.json",
        "live-native-commit-plan.json",
        "live-native-bundle.json",
    ):
        payload = (
            _native_inference_payload()
            if name == "live-native-inference.json" else {"ok": True}
        )
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert status["stage_status"]["current_stage"] == "native_live_state_contract"
    assert status["stage_status"]["next_blocker"] == "missing_or_invalid_live_state_contract"
    assert status["stage_status"]["checks"]["native_live_bundle_ready"] is True
    assert status["stage_status"]["checks"]["live_state_contract_ready"] is False
    assert "missing_live_state_contract" in status["blocking_reasons"]


def test_live_offboard_status_reports_cutover_stage_after_parity_ok(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    for name in (
        "live-bridge-bundle.json",
        "live-native-inference.json",
        "live-native-execution.json",
        "live-native-commit-plan.json",
        "live-native-bundle.json",
    ):
        payload = (
            _native_inference_payload()
            if name == "live-native-inference.json" else {"ok": True}
        )
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "live-live-state-contract.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source": "live_state_file",
            "account_snapshot": {"positions": {"AAPL": {"quantity": 1}}},
            "used_legacy": False,
            "warnings": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-parity-verdict.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert status["stage_status"]["current_stage"] == "native_live_job_cutover"
    assert status["stage_status"]["next_blocker"] == "remaining_umbrella_bridge_jobs"
    assert status["stage_status"]["checks"]["live_state_contract_ready"] is True
    assert status["stage_status"]["checks"]["native_commit_persistence_ready"] is True
    assert status["stage_status"]["checks"]["parity_ok"] is True
    assert status["artifact_status"]["live_state_contract"]["account_snapshot_position_count"] == 1
    assert status["ready_for_live_offboard"] is False
    packet = status["cutover_execution_packet"]
    assert packet["ready_for_readonly_validation"] is True
    assert packet["ready_to_execute"] is False
    assert packet["reason"] == "parity_green_but_native_cutover_is_readonly"
    assert [job["bridge_job_id"] for job in packet["jobs"]] == [
        "daily_live_runner_bridge",
        "live_runner_bridge",
    ]
    assert all(
        job["native_replacement_job_id"] == "native_live_run_candidate"
        for job in packet["jobs"]
    )
    assert packet["verification_commands"][0][:3] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_parity_fixture",
    ]
    assert packet["verification_commands"][1] == [
        "renquant-orchestrator",
        "live-offboard-status",
        "--mode",
        "live",
        "--output-dir",
        str(tmp_path),
        "--broker",
        "readonly-alpaca",
        "--strict",
    ]
    assert packet["native_live_commit_template"][0:3] == [
        "renquant-orchestrator",
        "run-job",
        "native_live_run_candidate",
    ]
    assert "--execute-live" in packet["native_live_commit_template"]
    assert "--commit-persistence" in packet["native_live_commit_template"]
    assert "<RUN_ID>" in packet["native_live_commit_template"]
    assert packet["required_operator_inputs"][0]["placeholder"] == "<RUN_ID>"
    assert packet["persistence_targets"]["live_state"].endswith(
        "backtesting/renquant_104/live_state.alpaca.json"
    )
    assert packet["persistence_targets"]["lifecycle_journal"].endswith(
        "live/logs/renquant-104/native-order-lifecycle.alpaca.jsonl"
    )


def test_live_offboard_status_blocks_uncommitted_commit_plan_persistence(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    for name in (
        "live-bridge-bundle.json",
        "live-native-inference.json",
        "live-native-execution.json",
        "live-native-bundle.json",
    ):
        payload = (
            _native_inference_payload()
            if name == "live-native-inference.json" else {"ok": True}
        )
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "live-native-commit-plan.json").write_text(
        json.dumps({
            "readonly": False,
            "broker_name": "alpaca",
            "state_mutations": [
                {
                    "mutation_type": "order_submission",
                    "committed": True,
                    "source_order_id": "ord-1",
                },
                {
                    "mutation_id": "planned-order-1-live-state",
                    "mutation_type": "planned_live_state_update",
                    "committed": False,
                    "symbol": "MSFT",
                    "action": "SELL",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
                {
                    "mutation_id": "planned-order-1-trade-log",
                    "mutation_type": "planned_trade_log_append",
                    "committed": False,
                    "symbol": "MSFT",
                    "action": "SELL",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
            ],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-live-state-contract.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source": "live_state_file",
            "account_snapshot": {"positions": {"MSFT": {"quantity": 1}}},
            "used_legacy": False,
            "warnings": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-parity-verdict.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert "native_commit_plan_has_uncommitted_persistence" in status["blocking_reasons"]
    assert status["stage_status"]["current_stage"] == "native_commit_persistence"
    assert status["stage_status"]["next_blocker"] == "uncommitted_native_persistence_mutations"
    assert status["stage_status"]["checks"]["native_commit_persistence_ready"] is False
    commit_status = status["artifact_status"]["native_commit_plan"]
    assert commit_status["readonly"] is False
    assert commit_status["broker_name"] == "alpaca"
    assert commit_status["persistence_committed"] is False
    assert commit_status["pending_persistence_mutation_count"] == 2
    assert commit_status["pending_persistence_mutations"] == [
        {
            "mutation_id": "planned-order-1-live-state",
            "mutation_type": "planned_live_state_update",
            "symbol": "MSFT",
            "action": "SELL",
            "source_order_id": "ord-1",
            "status": "filled",
        },
        {
            "mutation_id": "planned-order-1-trade-log",
            "mutation_type": "planned_trade_log_append",
            "symbol": "MSFT",
            "action": "SELL",
            "source_order_id": "ord-1",
            "status": "filled",
        },
    ]
    assert status["cutover_execution_packet"]["ready_for_readonly_validation"] is False
    assert status["cutover_execution_packet"]["ready_to_execute"] is False


def test_live_offboard_status_blocks_committed_persistence_without_audit(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    for name in (
        "live-bridge-bundle.json",
        "live-native-inference.json",
        "live-native-execution.json",
    ):
        payload = (
            _native_inference_payload()
            if name == "live-native-inference.json" else {"ok": True}
        )
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "live-native-commit-plan.json").write_text(
        json.dumps({
            "readonly": False,
            "broker_name": "alpaca",
            "state_mutations": [
                {
                    "mutation_id": "planned-order-1-live-state",
                    "mutation_type": "planned_live_state_update",
                    "committed": True,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
                {
                    "mutation_id": "planned-order-1-trade-log",
                    "mutation_type": "planned_trade_log_append",
                    "committed": True,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
            ],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-native-bundle.json").write_text(
        json.dumps({"metadata": {"readonly": False}}),
        encoding="utf-8",
    )
    (tmp_path / "live-live-state-contract.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source": "live_state_file",
            "account_snapshot": {"positions": {"AAPL": {"quantity": 1}}},
            "used_legacy": False,
            "warnings": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-parity-verdict.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert "missing_native_persistence_audit" in status["blocking_reasons"]
    assert status["stage_status"]["current_stage"] == "native_persistence_audit"
    assert status["stage_status"]["next_blocker"] == (
        "missing_or_incomplete_native_persistence_audit"
    )
    assert status["stage_status"]["checks"]["native_commit_persistence_ready"] is True
    assert status["stage_status"]["checks"]["native_persistence_audit_ready"] is False
    assert status["artifact_status"]["native_commit_plan"][
        "committed_persistence_mutation_count"
    ] == 2
    assert status["artifact_status"]["native_bundle"]["persistence_audit"] == {
        "exists": False,
        "ok": False,
    }


def test_live_offboard_status_accepts_committed_persistence_audit(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    for name in (
        "live-bridge-bundle.json",
        "live-native-inference.json",
        "live-native-execution.json",
    ):
        payload = (
            _native_inference_payload()
            if name == "live-native-inference.json" else {"ok": True}
        )
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "live-native-commit-plan.json").write_text(
        json.dumps({
            "readonly": False,
            "broker_name": "alpaca",
            "state_mutations": [
                {
                    "mutation_id": "planned-order-1-live-state",
                    "mutation_type": "planned_live_state_update",
                    "committed": True,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
                {
                    "mutation_id": "planned-order-1-trade-log",
                    "mutation_type": "planned_trade_log_append",
                    "committed": True,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                },
            ],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-native-bundle.json").write_text(
        json.dumps({
            "metadata": {
                "readonly": False,
                "persistence_audit": {
                    "committed_mutation_count": 2,
                    "trade_journal_row_count": 1,
                    "lifecycle_journal_row_count": 1,
                    "live_state_snapshot_row_count": 1,
                    "live_state_path": str(tmp_path / "live_state.alpaca.json"),
                    "trade_journal_path": str(tmp_path / "trades.jsonl"),
                    "lifecycle_journal_path": str(tmp_path / "lifecycle.jsonl"),
                    "runs_db_path": str(tmp_path / "runs.alpaca.db"),
                },
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-live-state-contract.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source": "live_state_file",
            "account_snapshot": {"positions": {"AAPL": {"quantity": 1}}},
            "used_legacy": False,
            "warnings": [],
        }),
        encoding="utf-8",
    )
    (tmp_path / "live-parity-verdict.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert "missing_native_persistence_audit" not in status["blocking_reasons"]
    assert "native_persistence_audit_incomplete" not in status["blocking_reasons"]
    assert status["stage_status"]["checks"]["native_persistence_audit_ready"] is True
    assert status["stage_status"]["current_stage"] == "native_live_job_cutover"
    audit = status["artifact_status"]["native_bundle"]["persistence_audit"]
    assert audit["ok"] is True
    assert audit["lifecycle_journal_row_count"] == 1
    assert audit["live_state_snapshot_row_count"] == 1


def test_live_offboard_status_cli_strict_returns_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    rc = main([
        "live-offboard-status",
        "--output-dir",
        "/tmp/rehearsal",
        "--strict",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["ready_for_live_offboard"] is False
    assert "remaining_umbrella_bridge_jobs" in out["blocking_reasons"]


def test_live_offboard_status_folds_in_scheduled_health(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    status = tmp_path / "health.json"
    status.write_text(
        json.dumps({"jobs": {"daily_live_runner_bridge": {"last_exit": 2}}}),
        encoding="utf-8",
    )

    rc = main([
        "live-offboard-status",
        "--output-dir",
        str(tmp_path),
        "--scheduled-health-json",
        str(status),
    ])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scheduled_health"]["summary"]["red_jobs"] == [
        "daily_live_runner_bridge",
    ]
