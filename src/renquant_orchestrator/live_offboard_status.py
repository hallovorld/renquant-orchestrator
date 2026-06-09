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
        status[name] = {"path": str(path), "exists": path.exists()}
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
    return status


def build_live_offboard_status(
    *,
    mode: str = "live",
    output_dir: str | Path = "/tmp/renquant-live-rehearsal",
    broker: str = "readonly-alpaca",
    include_execution_payload: bool = True,
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
    )
    blocking_reasons = list(rehearsal["missing_env"])
    if summary["remaining_umbrella_bridge_job_count"]:
        blocking_reasons.append("remaining_umbrella_bridge_jobs")

    return {
        "schema_version": 1,
        "ready_for_live_offboard": not blocking_reasons,
        "mode": mode,
        "broker": broker,
        "blocking_reasons": blocking_reasons,
        "scheduled_jobs_summary": summary,
        "artifact_status": _artifact_status(rehearsal["artifacts"]),
        "remaining_bridge_jobs": [
            {
                "job_id": job["job_id"],
                "kind": job["kind"],
                "command": job["command"],
                "rehearsal_command": job["rehearsal_command"],
                "native_offboard_blockers": job["native_offboard_blockers"],
                "native_exit_criteria": job["native_exit_criteria"],
            }
            for job in bridge_jobs
        ],
        "rehearsal": rehearsal,
        "next_actions": [
            "Provide readonly Alpaca credentials when missing.",
            "Run rehearsal.commands.bridge_capture to capture the current bridge bundle.",
            "Produce native inference/execution payloads at the planned artifact paths.",
            "Run rehearsal.commands.native_payload_parity and require ok=true before changing launchd.",
        ],
    }


__all__ = ["build_live_offboard_status"]
