#!/usr/bin/env python3
"""PIT N2 liveness check (#212 rule: liveness alert, separate from freshness).

Verifies TODAY's estimate snapshot was actually PUBLISHED per the collector's own
contract, not merely "some parquet exists somewhere":
  data/estimate_snapshots/<today>/{endpoint}.manifest.json  for EVERY endpoint in
  ``ENDPOINTS`` below, each non-zero-byte, each with ``status == "ok"`` and
  ``as_of == today`` in its own JSON body (a stale/mismatched manifest left over
  from a prior run is rejected, not just "any file present").

A missed day is UNRECOVERABLE (PIT invariant: no backfill), so this alert is the
package's most important file. Read-only.

Session-day gating uses the REAL NYSE exchange calendar
(``renquant_orchestrator.intraday_quote_logger.default_session_calendar`` —
``pandas_market_calendars``-backed, the SAME primitive #232's rq105 liveness
check and ``renquant_execution.preopen_cancel_gate`` use) rather than a bare
weekday check, so a scheduled market holiday does not fire a false
"snapshot lapsed" alert.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
ROOT = os.path.join(RQ, "data", "estimate_snapshots")
# The run-checkout root this script is deployed under (see README) — matches
# #232's own convention for locating the orchestrator src tree from an ops/
# script deployed outside a normal editable install.
RQ_ORCH_ROOT = os.environ.get(
    "RQ_ORCH_ROOT", "/Users/renhao/git/github/renquant-orchestrator-run"
)

# Mirrors renquant_base_data.fmp_estimate_revisions.ENDPOINTS exactly (a
# separate repo; not imported at runtime to keep this liveness check a
# lightweight, dependency-free standalone script). Naming convention
# (``{endpoint}.manifest.json``) and the "published iff every endpoint has a
# manifest" rule mirror that module's own ``_snapshot_is_published()`` — if
# that dict changes, update this tuple too.
ENDPOINTS = (
    "analyst_estimates",
    "grades_consensus",
    "price_target_consensus",
    "price_target_summary",
)


def _session_calendar():
    """Real NYSE calendar (holiday/half-day aware) — lazily imported so this
    script's argument parsing never requires the orchestrator package to be
    importable, only the actual liveness check does."""
    p = os.path.join(RQ_ORCH_ROOT, "src")
    if p not in sys.path:
        sys.path.insert(0, p)
    # Campaign B5: the primitive re-exported by intraday_quote_logger now
    # lives in renquant_common.market_calendar — a stale venv install may
    # predate it, so put a sibling renquant-common checkout on sys.path too
    # (pinned -run checkout preferred).
    for name in ("renquant-common-run", "renquant-common"):
        c = os.path.join(os.path.dirname(RQ_ORCH_ROOT), name, "src")
        if os.path.isdir(c) and c not in sys.path:
            sys.path.insert(0, c)
            break
    from renquant_orchestrator.intraday_quote_logger import default_session_calendar

    return default_session_calendar()


def _is_session_day(day: dt.date) -> bool:
    try:
        return _session_calendar().session_bounds(day) is not None
    except Exception as exc:  # pandas_market_calendars unavailable/broken — fail closed
        print(
            f"WARNING: NYSE calendar check failed ({exc}); treating {day} as a "
            f"session day (fail-closed: do not silently skip a possible lapse)",
            file=sys.stderr,
        )
        return True


def _alert(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic and os.path.exists(os.path.join(RQ, ".env")):
        for line in open(os.path.join(RQ, ".env")):
            if line.startswith("NTFY_TOPIC="):
                topic = line.split("=", 1)[1].strip().strip('"')
    if topic:
        subprocess.run(
            ["curl", "-s", "-H", f"Title: {title}", "-d", body, f"ntfy.sh/{topic}"],
            capture_output=True,
        )


def check_endpoint_manifest(day_dir: Path, endpoint: str, expected_as_of: str) -> str | None:
    """Return an error string if this endpoint's manifest fails the
    collector's own publication contract, else ``None``."""
    manifest_path = day_dir / f"{endpoint}.manifest.json"
    if not manifest_path.exists():
        return f"{endpoint}: manifest missing ({manifest_path.name})"
    if manifest_path.stat().st_size == 0:
        return f"{endpoint}: manifest is zero-byte"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"{endpoint}: manifest unreadable/corrupt ({exc})"
    status = manifest.get("status")
    if status != "ok":
        return f"{endpoint}: status={status!r} (not 'ok' — partial or dry-run publish)"
    as_of = manifest.get("as_of")
    if as_of != expected_as_of:
        return f"{endpoint}: as_of={as_of!r} != expected {expected_as_of!r} (stale/mismatched manifest)"
    parquet_name = manifest.get("output")
    if not parquet_name:
        return f"{endpoint}: manifest has no 'output' field"
    parquet_path = day_dir / parquet_name
    if not parquet_path.exists():
        return f"{endpoint}: parquet {parquet_name} referenced by manifest is missing"
    if parquet_path.stat().st_size == 0:
        return f"{endpoint}: parquet {parquet_name} is zero-byte"
    return None


def check_snapshot(today: dt.date) -> list[str]:
    """Every problem found for ``today``'s snapshot, empty list iff healthy."""
    day_dir = Path(ROOT) / today.isoformat()
    if not day_dir.is_dir():
        return [f"{day_dir} missing — snapshot never ran"]
    problems: list[str] = []
    for endpoint in ENDPOINTS:
        err = check_endpoint_manifest(day_dir, endpoint, today.isoformat())
        if err:
            problems.append(err)
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--as-of",
        default=None,
        help="ISO date to check instead of today (deterministic testing; "
             "production/launchd invocation always omits this and uses today).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    if not _is_session_day(today):
        print(f"PIT liveness: {today} is not an NYSE session day — skip")
        return 0

    problems = check_snapshot(today)
    if problems:
        _alert(
            f"PIT LIVENESS: snapshot incomplete {today.isoformat()}",
            "\n".join(problems) + "\nEvery missed day is UNRECOVERABLE.",
        )
        print("\n".join(problems))
        return 1
    print(f"PIT liveness OK {today.isoformat()}: all {len(ENDPOINTS)} endpoints published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
