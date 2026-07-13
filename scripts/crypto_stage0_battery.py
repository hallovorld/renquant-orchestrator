#!/usr/bin/env python3
"""Stage-0 paper battery CLI for crypto trading capability (RFC D-C12).

**Paper/shadow readiness work only.** This CLI is structurally unable to
authorize live trading entries — it verifies Alpaca crypto prerequisites
empirically on the PAPER account and persists the results as a scoped
``crypto_stage0_readiness`` record for audit. Graduating from paper to
live requires a separate design gate.

This is a THIN CLI wrapper around the first-class Stage-0 workflow in
``renquant_orchestrator.crypto_stage0_workflow``. The CLI owns ONLY:
argument parsing, creating the workflow context (with a fresh ``run_id``),
invoking the workflow pipeline, optional stdout/file report output, and
exit-code handling. All orchestration logic (Task/Job/Pipeline structure,
stage trace, readiness record persistence) lives in the workflow module.

Usage::

    # Dry-run (no orders placed, only account + asset checks):
    python scripts/crypto_stage0_battery.py --paper --dry-run

    # Full battery (places + cancels small test orders on paper):
    python scripts/crypto_stage0_battery.py --paper --bundle-dir ./bundles

Design reference: doc/design/2026-07-10-crypto-trading-rfc.md §6 Stage 0.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from renquant_orchestrator.crypto_stage0_workflow import (
    BatteryReport,
    CryptoStage0Context,
    CryptoStage0Pipeline,
    StepResult,
    _report_to_jsonable,
    new_run_id,
    run_stage0_workflow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("crypto_stage0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage-0 paper battery for crypto trading capability"
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        required=True,
        help="Use paper account (REQUIRED — live is never permitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip order-placement steps (only check account + assets)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON report to file (default: stdout)",
    )
    parser.add_argument(
        "--bundle-dir",
        type=str,
        default=None,
        help=(
            "Persist the readiness record (report + identity + "
            "content hash) as a timestamped JSON file in this directory"
        ),
    )
    args = parser.parse_args(argv)

    # Non-dry-run battery runs MUST persist a bundle — a real battery run
    # that completes with no persisted bundle is an audit gap.
    if not args.dry_run and not args.bundle_dir:
        parser.error("--bundle-dir is required for non-dry-run battery runs")

    # Determine the output directory for the workflow's readiness record.
    output_dir = Path(args.bundle_dir) if args.bundle_dir else Path.cwd() / ".crypto_stage0_tmp"

    # Run the workflow pipeline.
    ctx = run_stage0_workflow(
        paper=args.paper,
        dry_run=args.dry_run,
        output_dir=output_dir,
    )

    # Report output (stdout or file).
    if ctx.report is not None:
        summary = _report_to_jsonable(ctx.report)
        output_str = json.dumps(summary, indent=2, default=str)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output_str)
            log.info("Report written to %s", args.output)
        else:
            print(output_str)

    # Log summary.
    verdict = ctx.readiness_record.get("verdict", "UNKNOWN")
    report_sha = ctx.readiness_record.get("report_sha256", "")
    n_steps = len(ctx.report.steps) if ctx.report else 0
    log.info(
        "Battery complete: run_id=%s, verdict=%s, %d step(s), report_sha256=%s",
        ctx.run_id,
        verdict,
        n_steps,
        report_sha[:16] + "..." if report_sha else "n/a",
    )

    return 0 if ctx.workflow_ok else 1


if __name__ == "__main__":
    sys.exit(main())
