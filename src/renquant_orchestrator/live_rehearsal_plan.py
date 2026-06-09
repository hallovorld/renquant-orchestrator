"""Readonly live offboard rehearsal plan."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .env_files import read_env_file


REQUIRED_ALPACA_ENV = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")


def _missing_env(names: tuple[str, ...], env_file: str | Path | None = None) -> list[str]:
    file_values = read_env_file(env_file)
    return [name for name in names if not os.environ.get(name) and not file_values.get(name)]


def build_live_rehearsal_plan(
    *,
    mode: str = "live",
    output_dir: str | Path = "/tmp/renquant-live-rehearsal",
    broker: str = "readonly-alpaca",
    include_execution_payload: bool = True,
    env_file: str | Path | None = None,
) -> dict[str, Any]:
    """Build the operator command plan for live-runner offboard rehearsal."""
    if mode not in {"live", "daily"}:
        raise ValueError("mode must be 'live' or 'daily'")
    out = Path(output_dir)
    job_id = "daily_live_runner_bridge" if mode == "daily" else "live_runner_bridge"
    bridge_bundle = out / f"{mode}-bridge-bundle.json"
    inference_payload = out / f"{mode}-native-inference.json"
    execution_payload = out / f"{mode}-native-execution.json"
    native_bundle = out / f"{mode}-native-bundle.json"
    verdict = out / f"{mode}-parity-verdict.json"

    parity_command = [
        "renquant-orchestrator",
        "run-job",
        "native_live_payload_parity_fixture",
        "--",
        "--bridge-bundle",
        str(bridge_bundle),
        "--inference-json",
        str(inference_payload),
    ]
    if include_execution_payload:
        parity_command.extend(["--execution-json", str(execution_payload)])
    parity_command.extend([
        "--native-bundle-output",
        str(native_bundle),
        "--output-json",
        str(verdict),
        "--fail-on-diff",
    ])

    env_file_path = Path(env_file) if env_file is not None else None
    missing = _missing_env(REQUIRED_ALPACA_ENV, env_file_path) if broker != "paper" else []
    credential_source = (
        "not_required" if broker == "paper"
        else "process_env" if not missing and all(os.environ.get(name) for name in REQUIRED_ALPACA_ENV)
        else "env_file" if not missing and env_file_path is not None
        else "missing"
    )
    notes = [
        "Run bridge_capture first to capture the readonly umbrella bridge bundle.",
        "Produce native inference/execution payloads at the planned paths before native_payload_parity.",
        "Do not change production launchd commands until parity_verdict ok=true.",
    ]
    if credential_source == "env_file":
        notes.insert(
            0,
            "The bridge_capture command loads env_file before delegating to live.runner.",
        )
    bridge_command = [
        "renquant-orchestrator",
        "run-job",
        job_id,
        "--",
    ]
    if env_file_path is not None:
        bridge_command.extend(["--env-file", str(env_file_path)])
    bridge_command.extend([
        "--broker",
        broker,
        "--once",
        "--bridge-bundle-output",
        str(bridge_bundle),
    ])
    return {
        "schema_version": 1,
        "mode": mode,
        "broker": broker,
        "ready": not missing,
        "missing_env": missing,
        "credential_source": credential_source,
        "env_file": str(env_file_path) if env_file_path is not None else None,
        "env_file_exists": env_file_path.exists() if env_file_path is not None else None,
        "output_dir": str(out),
        "artifacts": {
            "bridge_bundle": str(bridge_bundle),
            "native_inference_payload": str(inference_payload),
            "native_execution_payload": str(execution_payload) if include_execution_payload else None,
            "native_bundle": str(native_bundle),
            "parity_verdict": str(verdict),
        },
        "commands": {
            "bridge_capture": bridge_command,
            "native_payload_parity": parity_command,
        },
        "notes": notes,
    }


__all__ = ["build_live_rehearsal_plan"]
