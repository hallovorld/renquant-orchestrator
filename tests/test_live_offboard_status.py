from __future__ import annotations

import json

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_offboard_status import build_live_offboard_status


def test_live_offboard_status_reports_env_and_bridge_blockers(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    status = build_live_offboard_status(output_dir="/tmp/rehearsal")

    assert status["ready_for_live_offboard"] is False
    assert status["blocking_reasons"] == [
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "remaining_umbrella_bridge_jobs",
    ]
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
    assert status["next_actions"]


def test_live_offboard_status_reports_existing_parity_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    verdict = tmp_path / "live-parity-verdict.json"
    verdict.write_text(json.dumps({"ok": True}), encoding="utf-8")

    status = build_live_offboard_status(output_dir=tmp_path)

    assert status["artifact_status"]["parity_verdict"] == {
        "path": str(verdict),
        "exists": True,
        "ok": True,
    }


def test_daily_live_offboard_status_uses_daily_rehearsal(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    status = build_live_offboard_status(mode="daily", output_dir="/tmp/rehearsal")

    assert status["ready_for_live_offboard"] is False
    assert status["blocking_reasons"] == ["remaining_umbrella_bridge_jobs"]
    assert status["rehearsal"]["ready"] is True
    assert status["rehearsal"]["commands"]["bridge_capture"][2] == "daily_live_runner_bridge"


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
