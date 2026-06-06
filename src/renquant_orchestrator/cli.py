"""Command-line entry points for RenQuant orchestration."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Sequence

# NOTE: contract_fixture (and the bridges) pull in heavy multirepo deps
# (renquant_execution, …). They are imported lazily inside their command
# branches so the lightweight `agent-workflow` / `repos` control-plane
# commands run in a bare environment (operator skills / CI) without the
# full assembled subrepo runtime.


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

    scheduled_jobs = sub.add_parser(
        "scheduled-jobs",
        help="emit the scheduled-job migration inventory as JSON",
    )
    scheduled_jobs.add_argument(
        "--fail-on-umbrella-bridge",
        action="store_true",
        help="return non-zero when any scheduled job still depends on umbrella code",
    )

    run_job = sub.add_parser(
        "run-job",
        help="run one scheduled job by stable inventory id",
    )
    from .scheduled_jobs import scheduled_jobs as _scheduled_jobs

    run_job.add_argument(
        "job_id",
        choices=[job.job_id for job in _scheduled_jobs()],
        help="scheduled job id from `scheduled-jobs` inventory",
    )
    run_job.add_argument("job_args", nargs=argparse.REMAINDER)

    agentwf = sub.add_parser(
        "agent-workflow",
        help="resolve a per-agent PR workflow queue (review/fix/merge); "
             "merge executes, review/fix emit a worklist for the agent",
    )
    agentwf.add_argument("--as", dest="agent", required=True,
                         choices=("claude", "codex"),
                         help="which agent (selects its gh token + identity)")
    agentwf.add_argument("--workflow", required=True,
                         choices=("review", "fix", "merge"))
    agentwf.add_argument("--repo", default="hallovorld/RenQuant",
                         help="owner/repo to operate on")
    agentwf.add_argument("--token", default=None,
                         help="gh token override; else RENQUANT_<AGENT>_GH_TOKEN / GH_TOKEN")
    agentwf.add_argument("--merge-strategy", default="merge",
                         choices=("merge", "squash", "rebase"))
    agentwf.add_argument("--execute", action="store_true",
                         help="for merge: actually merge the queued PRs")
    agentwf.add_argument(
        "--allow-no-checks",
        action="store_true",
        help="for merge: allow PRs with no status checks; default fails closed",
    )

    identity = sub.add_parser(
        "agent-identity",
        help="verify Claude/Codex gh tokens resolve to distinct GitHub actors",
    )
    identity.add_argument("--claude-token", default=None)
    identity.add_argument("--codex-token", default=None)
    identity.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when either token is missing, invalid, or shared",
    )

    # The single cross-repo control-plane entrypoint (design PR #23).
    repos_p = sub.add_parser(
        "repos",
        help="cross-repo control plane (list/status/sync/prs/exec/agent) "
             "driven by subrepos.lock.json",
    )
    repos_p.add_argument("repos_action",
                         choices=("list", "status", "sync", "prs", "exec", "agent"))
    repos_p.add_argument("--repo", default="all",
                         help="repo name or owner/repo; default 'all' (whole manifest)")
    repos_p.add_argument("--manifest", type=Path, default=None,
                         help="manifest path; default RenQuant/subrepos.lock.json")
    repos_p.add_argument("--token", default=None)
    repos_p.add_argument("--as", dest="agent", choices=("claude", "codex"),
                         help="for action=agent: which agent")
    repos_p.add_argument("--workflow", choices=("review", "fix", "merge"),
                         help="for action=agent: which workflow")
    repos_p.add_argument("--merge-strategy", default="merge",
                         choices=("merge", "squash", "rebase"))
    repos_p.add_argument("--execute", dest="repos_execute", action="store_true",
                         help="for action=agent merge: actually merge")
    repos_p.add_argument("--allow-no-checks", action="store_true",
                         help="for action=agent merge: allow PRs with no checks")
    repos_p.add_argument("--allow-all", action="store_true",
                         help="for action=agent merge --repo all --execute: opt into "
                              "cross-repo merge fan-out (bounded by --max-merges)")
    repos_p.add_argument("--max-merges", type=int, default=0,
                         help="cap on total merges in a cross-repo merge sweep")

    # `repos exec` takes its command after a literal `--`. Split it off
    # BEFORE argparse so it can't swallow this command's own flags
    # (REMAINDER is too greedy and ate --as/--workflow). Mirrors the
    # bridge arg-splitting pattern.
    repos_exec_cmd: list[str] = []
    if raw_argv and raw_argv[0] == "repos" and "--" in raw_argv:
        sep = raw_argv.index("--")
        repos_exec_cmd = raw_argv[sep + 1:]
        raw_argv = raw_argv[:sep]

    args, unknown = parser.parse_known_args(raw_argv)
    if unknown and args.command not in {"live-bridge", "daily-bridge"}:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    if args.command == "daily-contract":
        from .contract_fixture import run_contract_fixture

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
    if args.command == "scheduled-jobs":
        from .scheduled_jobs import inventory_payload

        payload = inventory_payload()
        print(json.dumps(payload, indent=2, sort_keys=True))
        if args.fail_on_umbrella_bridge and payload["summary"]["umbrella_bridge"]:
            return 2
        return 0
    if args.command == "run-job":
        from .job_runner import run_scheduled_job

        try:
            return run_scheduled_job(args.job_id, args.job_args)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "agent-workflow":
        from .agent_workflows import resolve_token, run_agent_workflow

        token = resolve_token(args.agent, args.token)
        plan = run_agent_workflow(
            agent=args.agent,
            workflow=args.workflow,
            repo=args.repo,
            token=token,
            execute=args.execute,
            merge_strategy=args.merge_strategy,
            allow_no_checks=args.allow_no_checks,
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.command == "agent-identity":
        from .agent_workflows import agent_identity_health

        health = agent_identity_health(
            claude_token=args.claude_token,
            codex_token=args.codex_token,
            require_actor_tokens=args.strict,
        )
        print(json.dumps(health, indent=2, sort_keys=True))
        return 0 if health["ok"] or not args.strict else 1
    if args.command == "repos":
        from .repos import DEFAULT_MANIFEST, run_repos

        try:
            result = run_repos(
                action=args.repos_action,
                repo=args.repo,
                manifest=args.manifest or DEFAULT_MANIFEST,
                exec_cmd=repos_exec_cmd or None,
                agent=args.agent,
                workflow=args.workflow,
                execute=args.repos_execute,
                merge_strategy=args.merge_strategy,
                allow_no_checks=args.allow_no_checks,
                allow_all=args.allow_all,
                max_merges=args.max_merges,
                token=args.token,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
