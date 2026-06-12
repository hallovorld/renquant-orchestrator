"""Live bridge offboard readiness status."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .live_rehearsal_plan import build_live_rehearsal_plan
from .scheduled_jobs import inventory_payload


_PENDING_PERSISTENCE_MUTATIONS = {
    "planned_live_state_update",
    "planned_trade_log_append",
}


def _commit_plan_pending_persistence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_mutations = payload.get("state_mutations") or []
    if not isinstance(raw_mutations, list):
        raise ValueError("native_commit_plan.state_mutations must be a list")
    pending: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_mutations):
        if not isinstance(raw, dict):
            raise ValueError(f"native_commit_plan.state_mutations[{idx}] must be an object")
        if raw.get("mutation_type") not in _PENDING_PERSISTENCE_MUTATIONS:
            continue
        if raw.get("committed") is True:
            continue
        pending.append({
            "mutation_id": raw.get("mutation_id"),
            "mutation_type": raw.get("mutation_type"),
            "symbol": raw.get("symbol"),
            "action": raw.get("action"),
            "source_order_id": raw.get("source_order_id"),
            "status": raw.get("status"),
        })
    return pending


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
    commit_plan_path = artifacts.get("native_commit_plan")
    commit_plan = status.get("native_commit_plan")
    if commit_plan_path and commit_plan is not None and commit_plan["exists"]:
        try:
            payload = json.loads(Path(commit_plan_path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("native_commit_plan must be a JSON object")
            pending = _commit_plan_pending_persistence(payload)
        except Exception as exc:  # noqa: BLE001 - surface corrupt commit-plan artifacts
            commit_plan["error"] = str(exc)
        else:
            commit_plan["readonly"] = bool(payload.get("readonly", True))
            commit_plan["broker_name"] = payload.get("broker_name")
            commit_plan["dry_run"] = bool(payload.get("dry_run", False))
            commit_plan["persistence_committed"] = len(pending) == 0
            commit_plan["pending_persistence_mutation_count"] = len(pending)
            commit_plan["pending_persistence_mutations"] = pending[:20]
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
    elif include_execution_payload:
        commit_plan = artifact_status["native_commit_plan"]
        if commit_plan.get("error"):
            blockers.append("invalid_native_commit_plan")
        elif commit_plan.get("pending_persistence_mutation_count", 0):
            blockers.append("native_commit_plan_has_uncommitted_persistence")
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
    commit_plan = artifact_status["native_commit_plan"]
    native_commit_persistence_ready = (
        not include_execution_payload
        or (
            commit_plan["exists"]
            and not commit_plan.get("error")
            and commit_plan.get("persistence_committed") is True
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
        "native_commit_persistence_ready": native_commit_persistence_ready,
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
    elif not native_commit_persistence_ready:
        current_stage = "native_commit_persistence"
        next_blocker = "uncommitted_native_persistence_mutations"
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


def _cutover_execution_packet(
    *,
    bridge_jobs: list[dict[str, Any]],
    stage_status: dict[str, Any],
    blocking_reasons: list[str],
    rehearsal: dict[str, Any],
) -> dict[str, Any]:
    """Return the machine-readable scheduler cutover packet.

    This does not mutate scheduler state. It only declares whether the final
    bridge-job replacement step is ready to execute.
    """
    checks = stage_status.get("checks", {})
    only_bridge_blocker = set(blocking_reasons) <= {"remaining_umbrella_bridge_jobs"}
    ready = (
        bool(bridge_jobs)
        and only_bridge_blocker
        and bool(checks.get("credential_preflight_ready"))
        and bool(checks.get("bridge_capture_ready"))
        and bool(checks.get("native_payloads_ready"))
        and bool(checks.get("native_commit_persistence_ready"))
        and bool(checks.get("native_live_bundle_ready"))
        and bool(checks.get("live_state_contract_ready"))
        and bool(checks.get("parity_ok"))
    )
    readonly_native_commands = any(
        "readonly-alpaca" in [str(part) for part in job["native_cutover_command"]]
        for job in bridge_jobs
    )
    jobs = [
        {
            "bridge_job_id": job["job_id"],
            "kind": job["kind"],
            "current_command": job["command"],
            "native_replacement_job_id": job["native_replacement_job_id"],
            "native_cutover_command": job["native_cutover_command"],
            "launchd_label": job.get("launchd_label"),
        }
        for job in bridge_jobs
    ]
    status_command = [
        "renquant-orchestrator",
        "live-offboard-status",
        "--mode",
        rehearsal["mode"],
        "--output-dir",
        rehearsal["output_dir"],
        "--broker",
        rehearsal["broker"],
        "--strict",
    ]
    if rehearsal.get("env_file"):
        status_command.extend(["--env-file", rehearsal["env_file"]])
    return {
        "schema_version": 1,
        "ready_for_readonly_validation": ready,
        "ready_to_execute": ready and not readonly_native_commands,
        "reason": (
            "parity_green_but_native_cutover_is_readonly"
            if ready and readonly_native_commands
            else "parity_green_scheduler_cutover_only"
            if ready else "preconditions_not_satisfied"
        ),
        "jobs": jobs,
        "preconditions": [
            "readonly bridge bundle captured from the current umbrella path",
            "native inference/execution payloads and native live bundle generated",
            "native commit plan has no uncommitted live-state or trade-log persistence mutations",
            "live-state contract is valid and uses the native contract schema",
            "native parity verdict is ok for decision_trace, order_intents, and state_mutations",
            "operator has approved the readonly native scheduler validation",
            "live execution commit semantics are ported before replacing production trading",
        ],
        "verification_commands": [
            rehearsal["commands"]["native_live_parity"],
            status_command,
        ],
        "rollback_note": (
            "Keep the previous bridge job command until the first native run and "
            "scheduled-health check pass; rollback is restoring the prior "
            "renquant-orchestrator run-job <bridge> command."
        ),
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
    remaining_bridge_jobs = [
        {
            "job_id": job["job_id"],
            "kind": job["kind"],
            "command": job["command"],
            "rehearsal_command": job["rehearsal_command"],
            "native_replacement_job_id": job["native_replacement_job_id"],
            "native_cutover_command": job["native_cutover_command"],
            "native_offboard_blockers": job["native_offboard_blockers"],
            "native_exit_criteria": job["native_exit_criteria"],
            "launchd_label": job.get("launchd_label"),
        }
        for job in bridge_jobs
    ]

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
        "remaining_bridge_jobs": remaining_bridge_jobs,
        "cutover_execution_packet": _cutover_execution_packet(
            bridge_jobs=remaining_bridge_jobs,
            stage_status=stage_status,
            blocking_reasons=blocking_reasons,
            rehearsal=rehearsal,
        ),
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
