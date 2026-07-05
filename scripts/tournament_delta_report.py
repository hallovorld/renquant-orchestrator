#!/usr/bin/env python3
"""M5 Tournament Retirement — Delta Report CLI.

Reads the shadow admission JSONL log and prints a summary comparing
tournament vs. panel admission paths.  Designed to run after >= 20 sessions
of shadow logging to inform the retirement decision.

Usage:
    python scripts/tournament_delta_report.py [LOG_PATH] [--json]

Arguments:
    LOG_PATH  Path to the shadow JSONL log.
              Default: data/shadow/tournament_vs_panel_admission.jsonl

Options:
    --json    Output as machine-readable JSON instead of text.
    --last N  Only analyze the last N sessions.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[0] / ".." / "src"))

from renquant_orchestrator.tournament_shadow_admission import (
    format_delta_report,
    generate_delta_report,
    read_records,
)

DEFAULT_LOG = "data/shadow/tournament_vs_panel_admission.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tournament vs Panel admission delta report",
    )
    parser.add_argument(
        "log_path",
        nargs="?",
        default=DEFAULT_LOG,
        help=f"Path to the JSONL shadow log (default: {DEFAULT_LOG})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        metavar="N",
        help="Analyze only the last N sessions",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"Error: shadow log not found at {log_path}", file=sys.stderr)
        print(
            "Enable shadow logging by setting RQ_TOURNAMENT_SHADOW_ENABLED=1 "
            "or passing enabled=True to log_shadow_admission().",
            file=sys.stderr,
        )
        return 1

    records = read_records(log_path)
    if not records:
        print(f"Error: no valid records in {log_path}", file=sys.stderr)
        return 1

    if args.last is not None and args.last > 0:
        records = records[-args.last:]

    report = generate_delta_report(records)

    if args.json_output:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        print(format_delta_report(report))

    # Exit code: 0 if ready, 1 if not enough data, 2 if not ready
    if report.n_sessions < 20:
        return 1
    if report.mean_agreement_rate >= 0.85:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
