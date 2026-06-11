"""Live bridge offboard readiness status."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .live_rehearsal_plan import build_live_rehearsal_plan
from .scheduled_jobs import inventory_payload


def _artifact_status(artifacts: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for name, raw_path in artifacts.items():
        if raw_path is None:
            status[name] = {"path": None, "exists": False}
            continue
        path = Path(raw_path)
        exists = path.exists()
        status[name] = {"path": str(path), "exists": exists}
        if exists:
            status[name]["size_bytes"] = path.stat().st_size
    verdict_path = artifacts.get("parity_verdict")
    verdict = status.get("parity_verdict")
    if verdict_path and verdict is not None and verdict["exists"]:
        try:
            payload = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface corrupt verdict artifacts
            verdict["ok"] = False
            verdict["error"] = str(exc)
        else:
            verdict["ok"] = bool(payload.get("ok"))
    live_state_path = artifacts.get("live_state_contract")
    live_state = status.get("live_state_contract")
    if live_state_path and live_state is not None and live_state["exists"]:
        try:
            payload = json.loads(Path(live_state_path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("live_state_contract must be a JSON object")
        except Exception as exc:  # noqa: BLE001 - surface corrupt state-contract artifacts
            live_state["ok"] = False
            live_state["error"] = str(exc)
        else:
            account_snapshot = payload.get("account_snapshot")
            positions = account_snapshot.get("positions") if isinstance(account_snapshot, dict) else None
            live_state["ok"] = (
                payload.get("schema_version") == 1
                and payload.get("source") in {"live_state_file", "live_state_snapshots_db", "empty"}
                and isinstance(account_snapshot, dict)
            )
            live_state["source"] = payload.get("source")
            live_state["used_legacy"] = bool(payload.get("used_legacy"))
            live_state["warnings"] = list(payload.get("warnings") or [])
            live_state["account_snapshot_position_count"] = (
                len(positions) if isinstance(positions, dict) else 0
            )
    return status


def _artifact_blockers(
    artifact_status: dict[str, dict[str, Any]],
    *,
    include_execution_payload: bool,
) -> list[str]:
    blockers: list[str] = []
    if not artifact_status["bridge_bundle"]["exists"]:
        blockers.append("missing_bridge_bundle")
    if not artifact_status["native_inference_payload"]["exists"]:
        blockers.append("missing_native_inference_payload")
    if include_execution_payload and not artifact_status["native_execution_payload"]["exists"]:
        blockers.append("missing_native_execution_payload")
    if include_execution_payload and not artifact_status["native_commit_plan"]["exists"]:
        blockers.append("missing_native_commit_plan")
    if not artifact_status["native_bundle"]["exists"]:
        blockers.append("missing_native_bundle")
    live_state = artifact_status.get("live_state_contract")
    if live_state is not None:
        if not live_state["exists"]:
            blockers.append("missing_live_state_contract")
        elif live_state.get("error"):
            blockers.append("invalid_live_state_contract")
        elif not live_state.get("ok"):
            blockers.append("live_state_contract_not_ok")
    verdict = artifact_status["parity_verdict"]
    if not verdict["exists"]:
        blockers.append("missing_parity_verdict")
    elif verdict.get("error"):
        blockers.append("invalid_parity_verdict")
    elif not verdict.get("ok"):
        blockers.append("parity_verdict_not_ok")
    return blockers


def _stage_status(
    *,
    credential_ready: bool,
    artifact_status: dict[str, dict[str, Any]],
    include_execution_payload: bool,
    remaining_bridge_job_count: int,
) -> dict[str, Any]:
    native_payloads_ready = artifact_status["native_inference_payload"]["exists"] and (
        not include_execution_payload
        or (
            artifact_status["native_execution_payload"]["exists"]
            and artifact_status["native_commit_plan"]["exists"]
        )
    )
    native_live_bundle_ready = artifact_status["native_bundle"]["exists"]
    live_state = artifact_status.get("live_state_contract", {})
    live_state_contract_ready = (
        live_state.get("exists") is True
        and not live_state.get("error")
        and live_state.get("ok") is True
    )
    parity_verdict = artifact_status["parity_verdict"]
    parity_verdict_ready = parity_verdict["exists"] and not parity_verdict.get("error")
    parity_ok = parity_verdict_ready and bool(parity_verdict.get("ok"))
    scheduled_bridge_jobs_clear = remaining_bridge_job_count == 0

    checks = {
        "credential_preflight_ready": credential_ready,
        "bridge_capture_ready": artifact_status["bridge_bundle"]["exists"],
        "native_payloads_ready": native_payloads_ready,
        "native_live_bundle_ready": native_live_bundle_ready,
        "live_state_contract_ready": live_state_contract_ready,
        "parity_verdict_ready": parity_verdict_ready,
        "parity_ok": parity_ok,
        "scheduled_bridge_jobs_clear": scheduled_bridge_jobs_clear,
    }
    if not credential_ready:
        current_stage = "credential_preflight"
        next_blocker = "missing_required_credentials"
    elif not checks["bridge_capture_ready"]:
        current_stage = "bridge_capture"
        next_blocker = "missing_bridge_bundle"
    elif not native_payloads_ready:
        current_stage = "native_payload_generation"
        next_blocker = "missing_native_payloads"
    elif not native_live_bundle_ready:
        current_stage = "native_live_bundle_generation"
        next_blocker = "missing_native_bundle"
    elif not live_state_contract_ready:
        current_stage = "native_live_state_contract"
        next_blocker = "missing_or_invalid_live_state_contract"
    elif not parity_verdict_ready:
        current_stage = "native_payload_parity"
        next_blocker = "missing_or_invalid_parity_verdict"
    elif not parity_ok:
        current_stage = "parity_review"
        next_blocker = "parity_verdict_not_ok"
    elif not scheduled_bridge_jobs_clear:
        current_stage = "native_live_job_cutover"
        next_blocker = "remaining_umbrella_bridge_jobs"
    else:
        current_stage = "ready"
        next_blocker = None
    return {
        "current_stage": current_stage,
        "next_blocker": next_blocker,
        "checks": checks,
    }


def build_live_offboard_status(
    *,
    mode: str = "live",
    output_dir: str | Path = "/tmp/renquant-live-rehearsal",
    broker: str = "readonly-alpaca",
    include_execution_payload: bool = True,
    env_file: str | Path | None = None,
    scheduled_health_json: str | Path | None = None,
) -> dict[str, Any]:
    """Return a single JSON-ready view of live bridge offboard readiness."""
    inventory = inventory_payload()
    summary = inventory["summary"]
    bridge_jobs = [
        job for job in inventory["jobs"]
        if job["migration_state"] == "umbrella_bridge"
    ]
    rehearsal = build_live_rehearsal_plan(
        mode=mode,
        output_dir=output_dir,
        broker=broker,
        include_execution_payload=include_execution_payload,
        env_file=env_file,
    )
    blocking_reasons = list(rehearsal["missing_env"])
    artifact_status = _artifact_status(rehearsal["artifacts"])
    blocking_reasons.extend(
        _artifact_blockers(
            artifact_status,
            include_execution_payload=include_execution_payload,
        )
    )
    if summary["remaining_umbrella_bridge_job_count"]:
        blocking_reasons.append("remaining_umbrella_bridge_jobs")
    stage_status = _stage_status(
        credential_ready=rehearsal["ready"],
        artifact_status=artifact_status,
        include_execution_payload=include_execution_payload,
        remaining_bridge_job_count=summary["remaining_umbrella_bridge_job_count"],
    )
    from .scheduled_health import build_scheduled_health

    scheduled_health = build_scheduled_health(status_json=scheduled_health_json)

    return {
        "schema_version": 1,
        "ready_for_live_offboard": not blocking_reasons,
        "mode": mode,
        "broker": broker,
        "blocking_reasons": blocking_reasons,
        "scheduled_jobs_summary": summary,
        "scheduled_health": scheduled_health,
        "stage_status": stage_status,
        "artifact_status": artifact_status,
        "remaining_bridge_jobs": [
            {
                "job_id": job["job_id"],
                "kind": job["kind"],
                "command": job["command"],
                "rehearsal_command": job["rehearsal_command"],
                "native_replacement_job_id": job["native_replacement_job_id"],
                "native_cutover_command": job["native_cutover_command"],
                "native_offboard_blockers": job["native_offboard_blockers"],
                "native_exit_criteria": job["native_exit_criteria"],
            }
            for job in bridge_jobs
        ],
        "rehearsal": rehearsal,
        "next_actions": [
            "Provide readonly Alpaca credentials when missing.",
            "Run rehearsal.commands.bridge_capture to capture the current bridge bundle.",
            "Produce the native inference payload at the planned artifact path.",
            "Run rehearsal.commands.native_live_run_candidate to build the readonly native bundle and live-state contract artifact.",
            "Run rehearsal.commands.native_live_parity and require ok=true before changing launchd.",
            "Replace each remaining bridge job with its native_cutover_command only after parity is ok.",
            "Lift production schedulers to a native live job with no RenQuant live.runner import before clearing bridge jobs.",
        ],
    }


__all__ = ["build_live_offboard_status"]
