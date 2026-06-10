from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_offboard_status import build_live_offboard_status


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
        (tmp_path / name).write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "live-parity-verdict.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert status["stage_status"]["current_stage"] == "native_live_job_cutover"
    assert status["stage_status"]["next_blocker"] == "remaining_umbrella_bridge_jobs"
    assert status["stage_status"]["checks"]["parity_ok"] is True
    assert status["ready_for_live_offboard"] is False


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
