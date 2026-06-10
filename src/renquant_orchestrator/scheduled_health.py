"""Scheduled-job health surface for the orchestrator control plane."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scheduled_jobs import inventory_payload


REJECT_MARKERS = (
    "gate rejected",
    "wf gate fail",
    "wf gate failed",
    "acceptance fail",
    "acceptance failed",
    "preflight reject",
    "preflight failed",
    "model rejected",
    "not promoted",
    "blocked by gate",
    "p-wf-gate",
)


def _load_status_source(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scheduled health status source must be a JSON object")
    return payload


def _status_by_job(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("jobs", payload)
    if isinstance(raw, dict):
        return {
            str(job_id): dict(value)
            for job_id, value in raw.items()
            if isinstance(value, dict)
        }
    if isinstance(raw, list):
        out: dict[str, dict[str, Any]] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("job_id"):
                out[str(item["job_id"])] = dict(item)
        return out
    return {}


def _last_log_excerpt(paths: list[str | None], *, max_chars: int) -> tuple[str | None, str | None]:
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        return str(path), text[-max_chars:]
    return None, None


def _classify(last_exit: Any, reason: Any, log_excerpt: str | None) -> str:
    if last_exit is None:
        return "unknown"
    try:
        exit_code = int(last_exit)
    except (TypeError, ValueError):
        return "unknown"
    if exit_code == 0:
        return "ok"
    haystack = f"{reason or ''}\n{log_excerpt or ''}".lower()
    if any(marker in haystack for marker in REJECT_MARKERS):
        return "reject"
    return "crash"


def build_scheduled_health(
    *,
    status_json: str | Path | None = None,
    log_tail_chars: int = 4000,
) -> dict[str, Any]:
    """Return a JSON-ready health view for scheduled jobs.

    ``status_json`` is intentionally a plain file contract so launchd, cron, or
    an operator script can publish last-exit facts without coupling this module
    to a specific scheduler API. Supported shapes are either
    ``{"jobs": {"job_id": {...}}}`` or a top-level ``{"job_id": {...}}`` map.
    """
    inventory = inventory_payload()
    facts = _status_by_job(_load_status_source(status_json))
    rows: list[dict[str, Any]] = []
    for job in inventory["jobs"]:
        fact = facts.get(job["job_id"], {})
        log_path = fact.get("last_log_path")
        excerpt_path, excerpt = _last_log_excerpt(
            [
                log_path if isinstance(log_path, str) else None,
                job.get("launchd_stderr_path"),
                job.get("launchd_stdout_path"),
            ],
            max_chars=log_tail_chars,
        )
        last_exit = fact.get("last_exit")
        verdict = _classify(last_exit, fact.get("reason"), excerpt)
        rows.append({
            "job_id": job["job_id"],
            "kind": job["kind"],
            "migration_state": job["migration_state"],
            "production_safe": job["production_safe"],
            "launchd_label": job.get("launchd_label"),
            "last_exit": last_exit,
            "last_started_at": fact.get("last_started_at"),
            "last_finished_at": fact.get("last_finished_at"),
            "last_log_path": log_path or excerpt_path,
            "health_verdict": verdict,
            "reason": fact.get("reason"),
            "log_excerpt": excerpt,
        })
    red = [row for row in rows if row["health_verdict"] in {"crash", "reject"}]
    unknown = [row for row in rows if row["health_verdict"] == "unknown"]
    return {
        "schema_version": 1,
        "owner_repo": "renquant-orchestrator",
        "status_source": str(status_json) if status_json is not None else None,
        "jobs": rows,
        "summary": {
            "total": len(rows),
            "ok": sum(row["health_verdict"] == "ok" for row in rows),
            "reject": sum(row["health_verdict"] == "reject" for row in rows),
            "crash": sum(row["health_verdict"] == "crash" for row in rows),
            "unknown": len(unknown),
            "red_job_count": len(red),
            "red_jobs": [row["job_id"] for row in red],
            "unknown_jobs": [row["job_id"] for row in unknown],
        },
    }


__all__ = ["build_scheduled_health"]
