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

The snapshotter runs on ALL weekdays (Mon–Fri) because FMP analyst estimates
update regardless of NYSE market status. The liveness check therefore verifies
on all weekdays too — not just NYSE trading days — so a snapshot failure on a
market holiday is never silently missed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
ROOT = os.path.join(RQ, "data", "estimate_snapshots")

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


def _is_collection_day(day: dt.date) -> bool:
    """The snapshotter runs Mon–Fri via launchd (FMP data updates regardless of
    NYSE market status). Only skip Sat/Sun where launchd never fires."""
    return day.weekday() < 5


def _alert(title: str, body: str) -> None:
    """Canonical sender re-point (campaign B6): topic resolution (NTFY_TOPIC env
    > $RQ/.env parse > "renquant") and RENQUANT_NO_NOTIFY suppression live in
    renquant_common.notify. Imported lazily + guarded so this liveness check
    still runs (and logs the loss loudly) against a venv whose renquant-common
    predates the notify module."""
    try:
        from renquant_common.notify import send
    except ImportError as exc:  # stale venv — do not let the alert path crash the check
        print(
            f"WARNING: renquant_common.notify unavailable ({exc}); "
            f"alert NOT sent: {title}: {body}",
            file=sys.stderr,
        )
        return
    send(title, body, env_file=os.path.join(RQ, ".env"))


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

    if not _is_collection_day(today):
        print(f"PIT liveness: {today} is a weekend — skip")
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
