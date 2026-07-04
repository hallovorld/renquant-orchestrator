"""Liveness/health monitor for the weekly model-promote chain (renquant_104).

The weekly walk-forward retrain -> WF-gate -> staged-artifact promotion chain
(``com.renquant.weekly-wf-promote`` -> ``scripts/weekly_wf_promote.sh``, Sat
04:00 PT) was silently broken for ~a month by a manifest-path bug with no
alert. The daily *trading*-health reporter (PR #174) answers "did we trade /
are we deployed?"; this module answers the DISTINCT question:

    Did the weekly promote pipeline actually RUN on schedule, and did it
    error/stall, or run cleanly?

It is intentionally additive, conservative, and strictly READ-ONLY:

- It never writes under ``artifacts/prod/`` (or any live state), never trains,
  never promotes, never places orders.
- It is fail-soft: any missing/unreadable input degrades a single signal to
  ``"unknown"`` instead of raising, so one missing file can't wedge the job.

Primary liveness signal: the newest ``*.weekly_<UTC-TIMESTAMP>.staging.json``
artifact under ``artifacts/prod/``. Every weekly run writes a fresh staging
artifact *even when the WF gate rejects the candidate* (a healthy outcome --
the chain ran and correctly refused a bad model), so staging-artifact freshness
cleanly separates "the chain ran" from "the chain stopped running".

Secondary signal: the per-run promote log
(``logs/weekly_wf_promote/<date>.log``) carries a final ``VERDICT: PASS`` /
``VERDICT: FAIL`` line plus crash tracebacks; it disambiguates a clean
pass/reject from an errored/partial run.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

from renquant_common.notify import send as post_ntfy  # canonical sender (campaign B6)

from .runtime_paths import default_repo_root


SCHEMA_VERSION = 1
OWNER_REPO = "renquant-orchestrator"

# --- thresholds (named constants) -------------------------------------------

# Nominal cadence of the weekly promote chain, in days. The chain is scheduled
# weekly (Saturday 04:00 PT) by com.renquant.weekly-wf-promote.plist.
EXPECTED_CADENCE_DAYS = 7

# Liveness tolerance: how old the newest staging artifact may be before the
# chain is considered "stale" (i.e. it most likely did NOT run last cycle).
# One nominal cadence plus a buffer so a slightly-delayed run does not alert.
STALE_AFTER_DAYS = 8

# Per-run promote log location, relative to the umbrella runtime repo root.
PROMOTE_LOG_SUBDIR = ("logs", "weekly_wf_promote")

# artifacts/prod subdir, relative to the umbrella runtime repo root.
PROD_ARTIFACTS_SUBDIR = ("backtesting", "renquant_104", "artifacts", "prod")

# Staging-artifact glob: panel-ltr.alpha158_fund.weekly_<TS>.staging.json and
# panel-rank-calibration.weekly_<TS>.staging.json both match this.
STAGING_GLOB = "*.weekly_*.staging.json"

# Filenames matching *.weekly_rollback_<date>.json are rollback markers, NOT
# fresh staging runs; they must be excluded from the liveness signal.
_ROLLBACK_RE = re.compile(r"\.weekly_rollback_", re.IGNORECASE)

# Embedded UTC timestamp inside a staging filename, e.g.
# panel-ltr.alpha158_fund.weekly_20260622T201008Z.staging.json
_STAGING_TS_RE = re.compile(r"\.weekly_(\d{8}T\d{6}Z)\.staging\.json$")

# Markers in the promote log used to classify the last run's outcome. The chain
# writes a final "VERDICT: PASS|FAIL" line; a reject is a *healthy* run (the
# gate refused a bad model), whereas a crash/traceback is an errored run.
_VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|FAIL)", re.IGNORECASE)
_ERROR_MARKERS = (
    "traceback (most recent call last)",
    "fatal:",
    "command not found",
    "no such file or directory",
)

# How much of the tail of the promote log to inspect.
LOG_TAIL_CHARS = 8000

DEFAULT_NTFY_TOPIC = "renquant"


@dataclass
class WeeklyPromoteMonitorContext:
    prod_artifacts_dir: Path
    promote_log_dir: Path
    stale_after_days: int = STALE_AFTER_DAYS
    topic: str = DEFAULT_NTFY_TOPIC


def _now_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_staging_timestamp(name: str) -> datetime | None:
    """Return the embedded UTC timestamp of a staging filename, or ``None``."""
    match = _STAGING_TS_RE.search(name)
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def newest_staging_artifact(prod_artifacts_dir: Path) -> tuple[Path | None, datetime | None]:
    """Return the newest non-rollback weekly staging artifact and its effective
    timestamp.

    The effective timestamp prefers the UTC stamp embedded in the filename (the
    chain's own notion of when it ran) and falls back to filesystem mtime when
    the name does not parse. Fail-soft: a missing/unreadable dir yields
    ``(None, None)`` rather than raising.
    """
    try:
        if not prod_artifacts_dir.is_dir():
            return None, None
        candidates = list(prod_artifacts_dir.glob(STAGING_GLOB))
    except OSError:
        return None, None

    best_path: Path | None = None
    best_ts: datetime | None = None
    for path in candidates:
        if _ROLLBACK_RE.search(path.name):
            continue
        ts = _parse_staging_timestamp(path.name)
        if ts is None:
            try:
                ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_path = path
    return best_path, best_ts


def newest_promote_log(promote_log_dir: Path) -> tuple[Path | None, datetime | None]:
    """Return the newest dated promote log (``<date>.log``) and its mtime.

    Fail-soft: a missing dir or unreadable entries yield ``(None, None)``.
    """
    try:
        if not promote_log_dir.is_dir():
            return None, None
        logs = [p for p in promote_log_dir.glob("*.log") if p.is_file()]
    except OSError:
        return None, None
    if not logs:
        return None, None
    best = max(logs, key=lambda p: _safe_mtime(p))
    return best, _safe_mtime_dt(best)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_mtime_dt(path: Path) -> datetime | None:
    mtime = _safe_mtime(path)
    if mtime <= 0.0:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def classify_promote_log(path: Path | None) -> tuple[str, str | None]:
    """Classify the last promote run from its log tail.

    Returns ``(status, detail)`` where status is one of:

    - ``"pass"``    -- chain ran and the gate promoted a model.
    - ``"reject"``  -- chain ran and the gate cleanly refused the candidate
                       (a HEALTHY outcome: production was intentionally left
                       unchanged).
    - ``"error"``   -- chain crashed / left a traceback or fatal marker with no
                       clean verdict.
    - ``"unknown"`` -- no log, unreadable, or no recognizable marker.
    """
    if path is None:
        return "unknown", None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "unknown", None
    tail = text[-LOG_TAIL_CHARS:]
    lowered = tail.lower()

    verdict = None
    for match in _VERDICT_RE.finditer(tail):
        verdict = match.group(1).upper()  # last verdict wins
    has_error = any(marker in lowered for marker in _ERROR_MARKERS)

    if verdict == "PASS":
        return "pass", "VERDICT: PASS"
    if verdict == "FAIL":
        # A clean gate rejection is healthy; only flag as error if the run also
        # left a crash/traceback marker AFTER (or without) a clean verdict.
        return "reject", "VERDICT: FAIL (gate rejected staged model)"
    if has_error:
        return "error", "promote log left a crash/traceback marker, no clean verdict"
    return "unknown", None


def build_weekly_promote_health(
    *,
    prod_artifacts_dir: str | Path | None = None,
    promote_log_dir: str | Path | None = None,
    stale_after_days: int = STALE_AFTER_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a JSON-ready health record for the weekly promote chain.

    Fields mirror the package's sibling ``build_*`` health surfaces
    (``schema_version`` / ``owner_repo`` / ``summary``). The record is
    fail-soft: any missing input degrades to ``"unknown"`` and never raises.

    ``health_verdict`` is one of:

    - ``"ok"``      -- a fresh staging artifact exists within tolerance and the
                       last run did not error.
    - ``"stale"``   -- no fresh staging artifact within tolerance: the chain
                       most likely did NOT run last cycle (the exact silent
                       failure this monitor exists to catch).
    - ``"error"``   -- the last run crashed/stalled (partial/errored log marker).
    - ``"unknown"`` -- inputs are missing and the chain's liveness can't be
                       determined.

    Only ``"stale"`` and ``"error"`` are alertable.
    """
    current = _now_utc(now)
    repo_root = default_repo_root()
    prod_dir = (
        Path(prod_artifacts_dir).expanduser()
        if prod_artifacts_dir is not None
        else repo_root.joinpath(*PROD_ARTIFACTS_SUBDIR)
    )
    log_dir = (
        Path(promote_log_dir).expanduser()
        if promote_log_dir is not None
        else repo_root.joinpath(*PROMOTE_LOG_SUBDIR)
    )

    staging_path, staging_ts = newest_staging_artifact(prod_dir)
    log_path, log_mtime = newest_promote_log(log_dir)
    last_run_status, last_run_detail = classify_promote_log(log_path)

    age_days: float | None = None
    if staging_ts is not None:
        age_days = (current - staging_ts).total_seconds() / 86400.0

    is_stale = age_days is not None and age_days > stale_after_days

    if staging_ts is None:
        verdict = "unknown"
        summary = (
            f"no weekly staging artifact found under {prod_dir}; "
            "weekly promote-chain liveness unknown"
        )
    elif is_stale:
        verdict = "stale"
        summary = (
            f"newest weekly staging artifact is {age_days:.1f}d old "
            f"(> {stale_after_days}d tolerance); promote chain likely did not "
            f"run last cycle ({staging_path.name if staging_path else '?'})"
        )
    elif last_run_status == "error":
        verdict = "error"
        summary = (
            f"last weekly promote run errored/stalled: {last_run_detail} "
            f"(newest staging artifact {age_days:.1f}d old)"
        )
    else:
        verdict = "ok"
        summary = (
            f"weekly promote chain fresh: newest staging artifact {age_days:.1f}d old "
            f"(<= {stale_after_days}d), last run = {last_run_status}"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "owner_repo": OWNER_REPO,
        "as_of": current.isoformat(),
        "prod_artifacts_dir": str(prod_dir),
        "promote_log_dir": str(log_dir),
        "expected_cadence_days": EXPECTED_CADENCE_DAYS,
        "stale_after_days": stale_after_days,
        "newest_staging_artifact": str(staging_path) if staging_path else None,
        "newest_staging_timestamp": staging_ts.isoformat() if staging_ts else None,
        "staging_age_days": round(age_days, 2) if age_days is not None else None,
        "newest_promote_log": str(log_path) if log_path else None,
        "newest_promote_log_mtime": log_mtime.isoformat() if log_mtime else None,
        "last_run_status": last_run_status,
        "last_run_detail": last_run_detail,
        "health_verdict": verdict,
        "alert": verdict in {"stale", "error"},
        "summary": summary,
    }


def emit_alert(health: dict[str, Any], *, topic: str = DEFAULT_NTFY_TOPIC, quiet: bool = False) -> bool:
    """Emit an ntfy alert when the chain is stale or errored. Returns whether an
    alert was (or, when ``quiet``, would have been) warranted."""
    if not health.get("alert"):
        return False
    if not quiet:
        title = "RenQuant 104 weekly-promote WATCH"
        post_ntfy(title, str(health.get("summary", "")), topic)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prod-artifacts-dir", default=None)
    parser.add_argument("--promote-log-dir", default=None)
    parser.add_argument("--stale-after-days", type=int, default=STALE_AFTER_DAYS)
    parser.add_argument("--topic", default=DEFAULT_NTFY_TOPIC)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    health = build_weekly_promote_health(
        prod_artifacts_dir=args.prod_artifacts_dir,
        promote_log_dir=args.promote_log_dir,
        stale_after_days=args.stale_after_days,
    )
    alerted = emit_alert(health, topic=args.topic, quiet=args.quiet)
    if args.json:
        print(json.dumps(health, indent=2, sort_keys=True))
    elif alerted:
        print(f"{health['health_verdict'].upper()}: {health['summary']}", file=sys.stderr)
    else:
        print(f"weekly_promote_check: {health['health_verdict']} - {health['summary']}")
    # Non-zero exit on an actionable problem, for scheduler visibility.
    return 2 if health["alert"] else 0


__all__ = [
    "build_weekly_promote_health",
    "classify_promote_log",
    "emit_alert",
    "newest_promote_log",
    "newest_staging_artifact",
    "post_ntfy",
    "DEFAULT_NTFY_TOPIC",
    "EXPECTED_CADENCE_DAYS",
    "STALE_AFTER_DAYS",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
