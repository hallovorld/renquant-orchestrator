#!/usr/bin/env python3
"""Stage-0 paper battery for crypto trading capability (RFC D-C12).

Verifies Alpaca crypto prerequisites empirically on the PAPER account:
  1. Account status + crypto trading enabled + verified paper environment
  2. Pair snapshot (min_order_size, min_trade_increment, price_increment)
  3. GTC order acceptance (quote-derived canary prices)
  4. GTC stop-limit acceptance (quote-derived canary prices)
  5. Non-marginable buying power behavior (observational)
  6. Two-source data parity check (optional; data-domain placeholder)

Outputs a JSON report with PASS/FAIL/SKIP/ERROR per step.

Usage::

    # Dry-run (no orders placed, only account + asset checks):
    python scripts/crypto_stage0_battery.py --paper --dry-run

    # Full battery (places + cancels small test orders on paper):
    python scripts/crypto_stage0_battery.py --paper --output battery_report.json

Design reference: doc/design/2026-07-10-crypto-trading-rfc.md §6 Stage 0.

Ownership (2026-07-12 — see doc/progress/2026-07-12-crypto-stage0-battery.md):
this script is a THIN CLI/orchestration consumer. All broker-facing step
checks, the safety gates (paper-only enforcement, fail-closed environment
verification, required/optional step policy), and their aggregation into a
``BatteryReport`` live in ``renquant-execution``
(``renquant_execution.crypto_stage0_checks.run_full_battery``,
renquant-execution#34) — this repo's own ``CLAUDE.md`` hard-boundaries "do
not implement broker adapters here," and orchestrator's CI does not install
``alpaca-py``. ``run_full_battery`` is the ONLY sanctioned entry point that
may place transactional probe orders (per that module's Codex-reviewed
design) — this script must never call the individual step-check functions
directly, and must not import anything from ``alpaca.*``.  This script owns
only: CLI argument parsing, constructing/connecting the ``AlpacaBroker``,
invoking ``run_full_battery``, JSON report writing, and exit-code handling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from renquant_execution.alpaca_broker import AlpacaBroker
    from renquant_execution.crypto_stage0_checks import (
        BatteryReport,
        StepResult,
        StepStatus,
        run_full_battery,
    )

    _HAS_CHECKS = True
except ImportError:
    _HAS_CHECKS = False

    from dataclasses import dataclass, field as _field
    from typing import Any as _Any

    @dataclass
    class StepResult:  # type: ignore[no-redef]
        name: str
        status: str
        detail: str = ""
        data: dict[str, _Any] = _field(default_factory=dict)
        required: bool = True

    @dataclass
    class BatteryReport:  # type: ignore[no-redef]
        timestamp: str = ""
        account_id: str = ""
        environment: str = ""
        dry_run: bool = False
        steps: list[StepResult] = _field(default_factory=list)

        @property
        def all_passed(self) -> bool:
            # Fallback-only mirror of the real BatteryReport.all_passed
            # (renquant_execution.crypto_stage0_checks): only required
            # steps must PASS. Exercised when the execution-repo dependency
            # is unavailable (dependency-ordering window) or in tests that
            # construct this fallback class directly.
            return all(
                getattr(s.status, "value", s.status) == "PASS"
                for s in self.steps
                if s.required
            )

    AlpacaBroker = None  # type: ignore[assignment,misc]
    StepStatus = None  # type: ignore[assignment,misc]
    run_full_battery = None  # type: ignore[assignment]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("crypto_stage0")

#: Bundle contract version — bump when the bundle schema changes.
BUNDLE_CONTRACT_VERSION = "1.0.0"


def _orchestrator_commit() -> str:
    """Resolve the current orchestrator repo commit via ``git rev-parse HEAD``.

    Returns ``"unknown"`` if the git command fails (e.g. not in a git repo, CI
    shallow clone, etc.) — the bundle must still be written, but its provenance
    is degraded.
    """
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def _content_sha256(payload: str) -> str:
    """SHA-256 hex digest of a UTF-8 string payload."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to *path* via atomic temp-file + rename.

    Same pattern as ``shadow_ab_runner._write_json_atomic`` — the bundle file
    is never partially written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(
        path.suffix + f".tmp.{os.getpid()}.{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    )
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _step_to_jsonable(step: StepResult) -> dict[str, Any]:
    d = asdict(step)
    status = d.get("status")
    d["status"] = getattr(status, "value", status)
    return d


def _report_to_jsonable(report: BatteryReport) -> dict[str, Any]:
    return {
        "timestamp": report.timestamp,
        "account_id": report.account_id,
        "environment": report.environment,
        "dry_run": report.dry_run,
        "all_passed": report.all_passed,
        "steps": [_step_to_jsonable(s) for s in report.steps],
    }


def build_run_bundle(report: BatteryReport) -> dict[str, Any]:
    """Build an orchestration run bundle envelope around a ``BatteryReport``.

    The bundle binds the execution report to orchestrator identity and includes
    a content hash of the serialized report for tamper-evidence (Codex review
    finding 4 on PR #500: a standalone ``--output`` JSON file is not the
    orchestrator run bundle — it must carry run identity and a verifiable
    report digest).

    Fields:
    - ``bundle_contract_version``: schema version for forward compatibility.
    - ``orchestrator_commit``: the invoking orchestrator repo's commit SHA.
    - ``bundle_timestamp``: when the bundle was assembled (UTC ISO-8601).
    - ``verdict``: ``"PASS"`` or ``"FAIL"`` — mirrors ``report.all_passed``.
    - ``report``: the full serialized ``BatteryReport``.
    - ``report_sha256``: SHA-256 of the canonical JSON serialization of the
      report (sorted keys, 2-space indent) — the versioned execution report
      contract.
    """
    report_dict = _report_to_jsonable(report)
    # Canonical serialization for the content hash — deterministic key order.
    canonical_report_json = json.dumps(report_dict, indent=2, sort_keys=True, default=str)

    return {
        "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
        "orchestrator_commit": _orchestrator_commit(),
        "bundle_timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS" if report.all_passed else "FAIL",
        "report_sha256": _content_sha256(canonical_report_json),
        "report": report_dict,
    }


def run_battery(*, paper: bool, dry_run: bool) -> BatteryReport:
    """Construct a connected paper ``AlpacaBroker`` and run the full battery.

    All broker-adapter logic, safety gates, and step aggregation live in
    :func:`renquant_execution.crypto_stage0_checks.run_full_battery` — this
    function only handles the orchestrator-side concerns: refusing a
    non-``--paper`` invocation before any broker object is even created, and
    reporting a clear FAIL if the execution-repo dependency is unavailable
    (expected during the dependency-ordering window before renquant-execution
    #34 merges — see this module's docstring).
    """
    if not paper:
        return BatteryReport(
            timestamp="",
            account_id="",
            environment="LIVE-BLOCKED",
            dry_run=dry_run,
            steps=[
                StepResult(
                    name="safety",
                    status="FAIL",
                    detail="Battery requires --paper flag",
                )
            ],
        )

    if not _HAS_CHECKS:
        return BatteryReport(
            timestamp="",
            account_id="",
            environment="paper",
            dry_run=dry_run,
            steps=[
                StepResult(
                    name="dependency",
                    status="FAIL",
                    detail="renquant_execution.crypto_stage0_checks not installed",
                )
            ],
        )

    broker = AlpacaBroker(paper=True)
    broker.connect()
    return run_full_battery(broker, dry_run=dry_run)


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
            "Persist the orchestration run bundle (report + identity + "
            "content hash) as a timestamped JSON file in this directory"
        ),
    )
    args = parser.parse_args(argv)

    report = run_battery(paper=args.paper, dry_run=args.dry_run)

    # Build the run bundle envelope (always, even if not persisted — the
    # bundle dict is the canonical output format when --bundle-dir is set).
    bundle = build_run_bundle(report)

    # Plain report for --output / stdout (backward-compatible).
    summary = bundle["report"]
    output_str = json.dumps(summary, indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        log.info("Report written to %s", args.output)
    else:
        print(output_str)

    # Persist the full run bundle if requested.
    if args.bundle_dir:
        bundle_dir = Path(args.bundle_dir)
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle_path = bundle_dir / f"crypto_stage0_bundle_{ts_slug}.json"
        _write_json_atomic(bundle_path, bundle)
        log.info(
            "Run bundle written to %s (report_sha256=%s)",
            bundle_path,
            bundle["report_sha256"][:16] + "...",
        )

    log.info(
        "Battery complete: verdict=%s, %d step(s), report_sha256=%s",
        bundle["verdict"],
        len(summary["steps"]),
        bundle["report_sha256"][:16] + "...",
    )
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
