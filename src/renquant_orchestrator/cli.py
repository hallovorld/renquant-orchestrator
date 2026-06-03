"""Command-line entry points for RenQuant orchestration."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Sequence

from .contract_fixture import run_contract_fixture


def _split_bridge_args(argv: list[str]) -> tuple[Path | None, list[str]]:
    repo_dir: Path | None = None
    runner_args: list[str] = []
    idx = 1
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--":
            runner_args.extend(argv[idx + 1 :])
            break
        if arg == "--repo-dir":
            if idx + 1 >= len(argv):
                raise ValueError("--repo-dir requires a value")
            repo_dir = Path(argv[idx + 1])
            idx += 2
            continue
        if arg.startswith("--repo-dir="):
            repo_dir = Path(arg.split("=", 1)[1])
            idx += 1
            continue
        runner_args.append(arg)
        idx += 1
    return repo_dir, runner_args


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="renquant-orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser(
        "daily-contract",
        help="run deterministic train->infer->execute->backtest contract fixture",
    )
    fixture.add_argument("--strategy-config", required=True)
    fixture.add_argument("--output-dir", required=True)
    fixture.add_argument("--run-id", default=None)
    fixture.add_argument("--as-of", default=None)
    fixture.add_argument("--code-commit", default="uncommitted")
    fixture.add_argument(
        "--broker-type",
        default="paper",
        help="execution broker mode: paper, alpaca-paper, alpaca-shadow, readonly-alpaca, alpaca",
    )
    fixture.add_argument("--broker-name", default=None)
    fixture.add_argument(
        "--execute",
        action="store_true",
        help="place real PaperBroker fills instead of dry-run confirmations",
    )

    live_bridge = sub.add_parser(
        "live-bridge",
        help="bootstrap pinned subrepos, then delegate to RenQuant live.runner",
    )
    live_bridge.add_argument("--repo-dir", type=Path, default=None)
    live_bridge.add_argument("runner_args", nargs=argparse.REMAINDER)

    daily_bridge = sub.add_parser(
        "daily-bridge",
        help="daily-flavored pinned subrepo bridge for scheduled full runs",
    )
    daily_bridge.add_argument("--repo-dir", type=Path, default=None)
    daily_bridge.add_argument("runner_args", nargs=argparse.REMAINDER)

    args, unknown = parser.parse_known_args(raw_argv)
    if unknown and args.command not in {"live-bridge", "daily-bridge"}:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    if args.command == "daily-contract":
        as_of = args.as_of or dt.date.today().isoformat()
        run_id = args.run_id or f"daily-contract-{as_of}"
        summary = run_contract_fixture(
            strategy_config_path=args.strategy_config,
            output_dir=Path(args.output_dir),
            run_id=run_id,
            as_of=as_of,
            code_commit=args.code_commit,
            broker_type=args.broker_type,
            broker_name=args.broker_name,
            dry_run=not args.execute,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command in {"live-bridge", "daily-bridge"}:
        from .live_bridge import DEFAULT_REPO_ROOT, run_bridge

        try:
            repo_dir_arg, runner_args = _split_bridge_args(raw_argv)
        except ValueError as exc:
            parser.error(str(exc))
        repo_dir = repo_dir_arg or DEFAULT_REPO_ROOT
        return run_bridge(
            runner_args,
            mode="daily" if args.command == "daily-bridge" else "live",
            repo_root=repo_dir.expanduser().resolve(),
        )
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
