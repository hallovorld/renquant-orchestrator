"""Readonly live offboard rehearsal plan."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .env_files import read_env_file
from .runtime_paths import default_repo_root


REQUIRED_ALPACA_ENV = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
RUN_ID_PLACEHOLDER = "<RUN_ID>"


def _missing_env(names: tuple[str, ...], env_file: str | Path | None = None) -> list[str]:
    file_values = read_env_file(env_file)
    return [name for name in names if not os.environ.get(name) and not file_values.get(name)]


def _broker_key(broker_name: str) -> str:
    return broker_name.replace("-", "_")


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
    readonly_commit_plan = out / f"{mode}-native-commit-plan.json"
    native_bundle = out / f"{mode}-native-bundle.json"
    live_state_contract = out / f"{mode}-live-state-contract.json"
    commit_execution_payload = out / f"{mode}-native-live-commit-execution.json"
    live_commit_plan = out / f"{mode}-native-live-commit-plan.json"
    commit_native_bundle = out / f"{mode}-native-live-commit-bundle.json"
    commit_live_state_contract = out / f"{mode}-native-live-commit-state-contract.json"
    verdict = out / f"{mode}-parity-verdict.json"
    repo_root = default_repo_root()
    strategy_dir = repo_root / "backtesting" / "renquant_104"
    live_state_broker = "alpaca" if broker == "readonly-alpaca" else broker
    broker_key = _broker_key(live_state_broker)
    runs_db = repo_root / "data" / f"runs.{broker_key}.db"
    persistence_live_state = strategy_dir / f"live_state.{broker_key}.json"
    persistence_trade_journal = (
        repo_root
        / "live"
        / "logs"
        / "renquant-104"
        / f"native-trade-journal.{broker_key}.jsonl"
    )
    persistence_lifecycle_journal = (
        repo_root
        / "live"
        / "logs"
        / "renquant-104"
        / f"native-order-lifecycle.{broker_key}.jsonl"
    )

    native_run_command = [
        "renquant-orchestrator",
        "run-job",
        "native_live_run_candidate",
        "--",
        "--inference-json",
        str(inference_payload),
        "--output-json",
        str(native_bundle),
        "--broker-name",
        broker,
        "--strategy-dir",
        str(strategy_dir),
        "--runs-db",
        str(runs_db),
        "--live-state-broker-name",
        live_state_broker,
        "--live-state-contract-output-json",
        str(live_state_contract),
    ]
    if include_execution_payload:
        native_run_command.extend([
            "--execution-output-json",
            str(execution_payload),
            "--commit-plan-output-json",
            str(readonly_commit_plan),
        ])
    native_live_commit_template = [
        "renquant-orchestrator",
        "run-job",
        "native_live_run_candidate",
        "--",
        "--inference-json",
        str(inference_payload),
        "--execution-output-json",
        str(commit_execution_payload),
        "--commit-plan-output-json",
        str(live_commit_plan),
        "--output-json",
        str(commit_native_bundle),
        "--run-id",
        RUN_ID_PLACEHOLDER,
        "--broker-name",
        live_state_broker,
        "--execute-live",
        "--commit-persistence",
        "--live-state-output-json",
        str(persistence_live_state),
        "--trade-journal-output-json",
        str(persistence_trade_journal),
        "--lifecycle-journal-output-json",
        str(persistence_lifecycle_journal),
        "--strategy-dir",
        str(strategy_dir),
        "--runs-db",
        str(runs_db),
        "--live-state-broker-name",
        live_state_broker,
        "--live-state-strategy",
        "renquant_104",
        "--live-state-contract-output-json",
        str(commit_live_state_contract),
    ]
    execution_command = [
        "renquant-orchestrator",
        "run-job",
        "native_live_execution_payload_fixture",
        "--",
        "--inference-json",
        str(inference_payload),
        "--output-json",
        str(execution_payload),
        "--broker-name",
        broker,
    ]
    live_parity_command = [
        "renquant-orchestrator",
        "run-job",
        "native_live_parity_fixture",
        "--",
        "--bridge-bundle",
        str(bridge_bundle),
        "--native-bundle",
        str(native_bundle),
        "--output-json",
        str(verdict),
        "--fail-on-diff",
    ]
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
        "Produce the native inference payload, then run native_live_run_candidate before native_live_parity.",
        "Do not change production launchd commands until parity_verdict ok=true.",
        "Do not run native_live_commit_template until <RUN_ID> is replaced and the offboard cutover packet is ready.",
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
        "--native-inference-payload-output",
        str(inference_payload),
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
            "native_commit_plan": (
                str(readonly_commit_plan) if include_execution_payload else None
            ),
            "native_bundle": str(native_bundle),
            "live_state_contract": str(live_state_contract),
            "native_live_commit_execution_payload": str(commit_execution_payload),
            "native_live_commit_plan": str(live_commit_plan),
            "native_live_commit_bundle": str(commit_native_bundle),
            "native_live_commit_state_contract": str(commit_live_state_contract),
            "parity_verdict": str(verdict),
        },
        "persistence_targets": {
            "live_state": str(persistence_live_state),
            "trade_journal": str(persistence_trade_journal),
            "lifecycle_journal": str(persistence_lifecycle_journal),
            "runs_db": str(runs_db),
        },
        "required_operator_inputs": [
            {
                "placeholder": RUN_ID_PLACEHOLDER,
                "description": (
                    "unique native live run id used for persistence audit "
                    "and live_state_snapshots"
                ),
            }
        ],
        "commands": {
            "bridge_capture": bridge_command,
            "native_execution_payload": execution_command,
            "native_live_run_candidate": native_run_command,
            "native_live_commit_template": native_live_commit_template,
            "native_live_parity": live_parity_command,
            "native_payload_parity": parity_command,
        },
        "notes": notes,
    }


__all__ = ["build_live_rehearsal_plan"]
