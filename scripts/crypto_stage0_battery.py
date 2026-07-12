#!/usr/bin/env python3
"""Stage-0 paper battery for crypto trading capability (RFC D-C12).

Verifies Alpaca crypto prerequisites empirically on the PAPER account:
  1. crypto_status == ACTIVE
  2. Pair list + increment snapshot (min_order_size, min_trade_increment, price_increment)
  3. GTC/IOC order acceptance per pair subset
  4. GTC stop_limit acceptance per pair subset
  5. Fee schedule from fill receipts
  6. Non-marginable buying power behavior
  7. Two-source data parity check (Alpaca vs yfinance daily close)

Outputs a JSON report with PASS/FAIL/SKIP per step.

Usage::

    # Dry-run (no orders placed, only account + asset checks):
    python scripts/crypto_stage0_battery.py --paper --dry-run

    # Full battery (places + cancels small test orders on paper):
    python scripts/crypto_stage0_battery.py --paper --output battery_report.json

Design reference: doc/design/2026-07-10-crypto-trading-rfc.md §6 Stage 0.

Ownership (2026-07-12 — see doc/progress/2026-07-12-crypto-stage0-battery.md):
this script is a THIN CLI/orchestration consumer. The 7 broker-facing step
checks (and the Alpaca client factories they need) moved to
``renquant-execution`` (``renquant_execution.crypto_stage0_checks``,
renquant-execution#32) — this repo's own ``CLAUDE.md`` hard-boundaries
"do not implement broker adapters here," and orchestrator's CI does not
install ``alpaca-py`` (see that module's docstring for the full CI-red +
architecture-boundary rationale). This script owns only: CLI argument
parsing, constructing the trading client via the execution-repo factory,
aggregating the 7 ``StepResult``s into a ``BatteryReport``, JSON report
writing, and exit-code handling. It must not import anything from
``alpaca.*`` directly — see the module import list below, none do.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from renquant_execution.crypto_stage0_checks import (
    StepResult,
    get_trading_client,
    step_buying_power,
    step_crypto_status,
    step_data_parity,
    step_fee_from_fill,
    step_order_acceptance,
    step_pair_snapshot,
    step_stop_limit_acceptance,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("crypto_stage0")


@dataclass
class BatteryReport:
    timestamp_utc: str = ""
    account_id: str = ""
    environment: str = "paper"
    dry_run: bool = False
    steps: list[StepResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.steps if s.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if s.status == "FAIL")

    def summary(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "account_id": self.account_id,
            "environment": self.environment,
            "dry_run": self.dry_run,
            "total": len(self.steps),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": sum(1 for s in self.steps if s.status == "SKIP"),
            "errors": sum(1 for s in self.steps if s.status == "ERROR"),
            "steps": [asdict(s) for s in self.steps],
        }


def run_battery(*, paper: bool, dry_run: bool) -> BatteryReport:
    """Run the full Stage-0 battery.

    The 7 step checks themselves (imported from
    ``renquant_execution.crypto_stage0_checks``) are broker-adapter logic
    and live in renquant-execution; this function only orchestrates and
    aggregates them into one report.
    """
    report = BatteryReport(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
        environment="paper" if paper else "LIVE-BLOCKED",
    )

    if not paper:
        report.steps.append(
            StepResult("safety", "FAIL", "Battery requires --paper flag")
        )
        return report

    client = get_trading_client(paper=True)

    log.info("Step 1/7: crypto_status")
    r1 = step_crypto_status(client)
    report.steps.append(r1)
    report.account_id = r1.data.get("account_id", "")

    log.info("Step 2/7: pair_snapshot")
    report.steps.append(step_pair_snapshot(client))

    log.info("Step 3/7: order_acceptance (GTC limit)")
    report.steps.append(step_order_acceptance(client, dry_run=dry_run))

    log.info("Step 4/7: stop_limit_acceptance (GTC stop-limit)")
    report.steps.append(step_stop_limit_acceptance(client, dry_run=dry_run))

    log.info("Step 5/7: fee_from_fill (market buy)")
    report.steps.append(step_fee_from_fill(client, dry_run=dry_run))

    log.info("Step 6/7: buying_power")
    report.steps.append(step_buying_power(client))

    log.info("Step 7/7: data_parity")
    report.steps.append(step_data_parity(dry_run=dry_run))

    return report


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
        help="Skip order-placement steps (only check account + assets + data)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON report to file (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = run_battery(paper=args.paper, dry_run=args.dry_run)

    summary = report.summary()
    output_str = json.dumps(summary, indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        log.info("Report written to %s", args.output)
    else:
        print(output_str)

    log.info(
        "Battery complete: %d passed, %d failed, %d skipped, %d errors",
        summary["passed"],
        summary["failed"],
        summary["skipped"],
        summary["errors"],
    )
    return 1 if report.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
