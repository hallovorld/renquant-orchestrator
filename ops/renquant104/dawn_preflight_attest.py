#!/usr/bin/env python3
"""Verify the dawn preflight runner attested a no-write / no-notify probe.

GOAL-5 AC5 / PR #565 codex CR: `live.runner --preflight` drives the full
inference funnel to a decision line but must place NO orders, persist NO
DB/state, promote nothing, and send NO notification. It proves this by emitting
a single machine-readable line:

    preflight_attestation: {"persisted": false, "notified": false,
                            "promoted": false, "ordered": false,
                            "reached_decision": true}

This verifier is the shell guard's fail-closed gate: the probe is trusted ONLY
when that line is present, every mutation flag is false, AND a decision was
reached. A missing line (crash/hang/truncation) or ANY true mutation flag is a
problem — the guard must exit non-zero and alert. Read-only; no side effects
beyond an optional operator alert.

Exit 0 = attestation clean; exit 1 = fail closed (problem or alert); exit 2 =
usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert  # noqa: E402

_ATTEST_PREFIX = "preflight_attestation:"

# Mutation flags that MUST be false, plus the liveness flag that MUST be true.
_MUST_BE_FALSE = ("persisted", "notified", "promoted", "ordered")
_MUST_BE_TRUE = ("reached_decision",)


def verify(log_text: str) -> list[str]:
    """Return a list of problems; empty means the attestation is clean."""
    lines = [
        ln for ln in log_text.splitlines() if ln.strip().startswith(_ATTEST_PREFIX)
    ]
    if not lines:
        return [
            "no preflight_attestation line — the runner crashed, hung, or was "
            "truncated before attesting no-write/no-notify (fail closed)"
        ]
    # Use the LAST attestation line (the terminal one for the run).
    raw = lines[-1].split(_ATTEST_PREFIX, 1)[1].strip()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return [f"preflight_attestation is not valid JSON ({exc}): {raw[:200]}"]
    if not isinstance(payload, dict):
        return [f"preflight_attestation is not a JSON object: {raw[:200]}"]

    problems: list[str] = []
    for key in _MUST_BE_FALSE:
        if key not in payload:
            problems.append(f"attestation missing '{key}' (fail closed)")
        elif payload[key] is not False:
            problems.append(
                f"attestation '{key}' is {payload[key]!r}, expected false — a "
                "side effect was reached during the read-only probe"
            )
    for key in _MUST_BE_TRUE:
        if key not in payload:
            problems.append(f"attestation missing '{key}' (fail closed)")
        elif payload[key] is not True:
            problems.append(
                f"attestation '{key}' is {payload[key]!r}, expected true — the "
                "funnel never reached a decision line"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--no-alert", action="store_true", help="report only (tests)")
    args = ap.parse_args(argv)
    if not args.log.is_file():
        print(f"dawn preflight log missing: {args.log}", file=sys.stderr)
        if not args.no_alert:
            alert(
                "RQ104 dawn preflight",
                f"preflight log missing ({args.log}) — the dawn probe failed to "
                "start; treat as fail closed",
                rq_root=os.environ.get("RQ_ROOT"),
            )
        return 1
    problems = verify(args.log.read_text(encoding="utf-8", errors="replace"))
    if not problems:
        print("dawn preflight attestation OK (no writes, no notify, decision reached)")
        return 0
    body = "; ".join(problems[:5])
    print(f"dawn preflight attestation FAIL: {len(problems)} problem(s): {body}")
    if not args.no_alert:
        alert(
            "RQ104 dawn preflight",
            f"probe not attested clean 8h before the daily: {body}",
            rq_root=os.environ.get("RQ_ROOT"),
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
