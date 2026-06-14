from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_offboard_rehearsal import run_live_offboard_rehearsal


def _write_rehearsal_artifacts(out: Path, *, mode: str = "live") -> None:
    (out / f"{mode}-bridge-bundle.json").write_text(
        json.dumps({
            "decision_trace": [],
            "order_intents": [],
            "state_mutations": [],
        }),
        encoding="utf-8",
    )
    (out / f"{mode}-native-inference.json").write_text(
        json.dumps({"schema_version": 1, "order_intents": []}),
        encoding="utf-8",
    )
    (out / f"{mode}-native-execution.json").write_text(
        json.dumps({"schema_version": 1, "submitted_orders": []}),
        encoding="utf-8",
    )
    (out / f"{mode}-native-commit-plan.json").write_text(
        json.dumps({
            "broker_name": "readonly-alpaca",
            "readonly": True,
            "state_mutations": [],
        }),
        encoding="utf-8",
    )
    (out / f"{mode}-native-bundle.json").write_text(
        json.dumps({
            "metadata": {},
            "decision_trace": [],
            "order_intents": [],
            "state_mutations": [],
        }),
        encoding="utf-8",
    )
    (out / f"{mode}-live-state-contract.json").write_text(
        json.dumps({
            "schema_version": 1,
            "source": "empty",
            "account_snapshot": {"positions": {}},
        }),
        encoding="utf-8",
    )
    (out / f"{mode}-parity-verdict.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )


def test_live_offboard_rehearsal_runs_readonly_steps(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    commands: list[list[str]] = []

    def runner(command):
        commands.append(list(command))
        _write_rehearsal_artifacts(tmp_path)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    payload = run_live_offboard_rehearsal(output_dir=tmp_path, runner=runner)

    assert payload["ok"] is True
    assert [step["step"] for step in payload["steps"]] == [
        "bridge_capture",
        "native_live_run_candidate",
        "native_live_parity",
    ]
    assert all(command[:3] == [sys.executable, "-m", "renquant_orchestrator"] for command in commands)
    rendered = json.dumps(commands)
    assert "native_live_commit_template" not in rendered
    assert "--execute-live" not in rendered
    assert (tmp_path / "live-offboard-rehearsal-manifest.json").exists()
    assert (tmp_path / "live-rehearsal-plan.json").exists()
    assert (tmp_path / "live-offboard-status.json").exists()


def test_live_offboard_rehearsal_stops_on_first_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    commands: list[list[str]] = []

    def runner(command):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="boom\n")

    payload = run_live_offboard_rehearsal(output_dir=tmp_path, runner=runner)

    assert payload["ok"] is False
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["step"] == "bridge_capture"
    assert payload["steps"][0]["stderr_tail"] == ["boom"]
    assert len(commands) == 1


def test_live_offboard_rehearsal_cli_strict_returns_nonzero_without_credentials(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    rc = main([
        "live-offboard-rehearsal",
        "--output-dir",
        str(tmp_path),
        "--strict",
    ])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready_to_start"] is False
    assert payload["steps"] == []
    assert "ALPACA_API_KEY" in payload["blocking_reasons"]
