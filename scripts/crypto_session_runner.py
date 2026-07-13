#!/usr/bin/env python3
"""Crypto session runner — evaluates one or more scheduler ticks (D-C11).

Thin CLI wrapper around ``renquant_orchestrator.crypto_session.evaluate_tick``.
Runs one tick (``--once``, default) or loops at a configurable interval
(``--loop --interval N``). Each tick result is logged as JSON to stdout and
appended to a session log file under ``data/crypto/session_logs/``.

Usage::

    # Single tick with default paper config:
    python scripts/crypto_session_runner.py --once

    # Daemon mode, tick every 900s:
    python scripts/crypto_session_runner.py --loop --interval 900

    # With explicit config file:
    python scripts/crypto_session_runner.py --once --config crypto_config.json

Design reference: crypto RFC §3.5 (orchestrator PR #453).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path

from renquant_orchestrator.crypto_session import (
    CryptoSessionConfig,
    DEFAULT_STOP_COVERAGE_RELPATH,
    DEFAULT_TICK_CADENCE_SECONDS,
    evaluate_tick,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("crypto_session_runner")

DEFAULT_LOG_DIR = Path("data/crypto/session_logs")


def _load_config(config_path: str | None) -> CryptoSessionConfig:
    if config_path is None:
        return CryptoSessionConfig(enabled=True, mode="paper")
    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CryptoSessionConfig.from_dict(raw)


def _log_dir(base: Path | None) -> Path:
    d = base if base is not None else DEFAULT_LOG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_one_tick(
    config: CryptoSessionConfig,
    log_dir: Path,
    stop_coverage_path: Path | None = None,
) -> dict:
    now_utc = dt.datetime.now(dt.timezone.utc)
    result = evaluate_tick(
        config=config,
        now_utc=now_utc,
        signal_snapshot=None,
        artifact_ref_path=None,
        stop_coverage_path=stop_coverage_path,
    )
    payload = result.to_jsonable()
    payload["runner_version"] = "1"

    json_line = json.dumps(payload, default=str)
    print(json_line, flush=True)

    date_str = now_utc.strftime("%Y-%m-%d")
    log_file = log_dir / f"session_{date_str}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json_line + "\n")

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crypto session runner (D-C11)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--once", action="store_true", default=True,
        help="Run a single tick and exit (default)",
    )
    group.add_argument(
        "--loop", action="store_true",
        help="Run ticks in a loop at --interval cadence",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_TICK_CADENCE_SECONDS,
        help=f"Tick interval in seconds for --loop mode (default: {DEFAULT_TICK_CADENCE_SECONDS})",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to JSON config file (default: paper mode with enabled=True)",
    )
    parser.add_argument(
        "--log-dir", type=str, default=None,
        help=f"Directory for session log files (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--stop-coverage-path", type=str, default=None,
        help=f"Path to stop-coverage report (default: {DEFAULT_STOP_COVERAGE_RELPATH})",
    )
    args = parser.parse_args(argv)

    try:
        config = _load_config(args.config)
    except Exception as exc:
        log.error("failed to load config: %s", exc)
        return 1

    ld = _log_dir(Path(args.log_dir) if args.log_dir else None)
    stop_path = Path(args.stop_coverage_path) if args.stop_coverage_path else None

    if args.loop:
        log.info("starting loop mode, interval=%ds", args.interval)
        while True:
            try:
                run_one_tick(config, ld, stop_coverage_path=stop_path)
            except Exception:
                log.exception("tick failed")
            time.sleep(args.interval)
    else:
        try:
            run_one_tick(config, ld, stop_coverage_path=stop_path)
        except Exception:
            log.exception("tick failed")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
