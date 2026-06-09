"""Readonly live offboard rehearsal plan."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


REQUIRED_ALPACA_ENV = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")


def _missing_env(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not os.environ.get(name)]


def build_live_rehearsal_plan(
    *,
    mode: str = "live",
    output_dir: str | Path = "/tmp/renquant-live-rehearsal",
    broker: str = "readonly-alpaca",
    include_execution_payload: bool = True,
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

    missing = _missing_env(REQUIRED_ALPACA_ENV) if broker != "paper" else []
    return {
        "schema_version": 1,
        "mode": mode,
        "broker": broker,
        "ready": not missing,
        "missing_env": missing,
        "output_dir": str(out),
        "artifacts": {
            "bridge_bundle": str(bridge_bundle),
            "native_inference_payload": str(inference_payload),
            "native_execution_payload": str(execution_payload) if include_execution_payload else None,
            "native_bundle": str(native_bundle),
            "parity_verdict": str(verdict),
        },
        "commands": {
            "bridge_capture": [
                "renquant-orchestrator",
                "run-job",
                job_id,
                "--",
                "--broker",
                broker,
                "--once",
                "--bridge-bundle-output",
                str(bridge_bundle),
            ],
            "native_payload_parity": parity_command,
        },
        "notes": [
            "Run bridge_capture first to capture the readonly umbrella bridge bundle.",
            "Produce native inference/execution payloads at the planned paths before native_payload_parity.",
            "Do not change production launchd commands until parity_verdict ok=true.",
        ],
    }


__all__ = ["build_live_rehearsal_plan"]
