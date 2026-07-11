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


def _split_bridge_args(argv: list[str]) -> tuple[Path | None, Path | None, list[str]]:
    repo_dir: Path | None = None
    env_file: Path | None = None
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
        if arg == "--env-file":
            if idx + 1 >= len(argv):
                raise ValueError("--env-file requires a value")
            env_file = Path(argv[idx + 1])
            idx += 2
            continue
        if arg.startswith("--env-file="):
            env_file = Path(arg.split("=", 1)[1])
            idx += 1
            continue
        runner_args.append(arg)
        idx += 1
    return repo_dir, env_file, runner_args


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
    live_bridge.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="optional .env file loaded before delegating to live.runner",
    )
    live_bridge.add_argument("runner_args", nargs=argparse.REMAINDER)

    daily_bridge = sub.add_parser(
        "daily-bridge",
        help="daily-flavored pinned subrepo bridge for scheduled full runs",
    )
    daily_bridge.add_argument("--repo-dir", type=Path, default=None)
    daily_bridge.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="optional .env file loaded before delegating to live.runner",
    )
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
    gate_value = sub.add_parser(
        "gate-value",
        help="per-gate outcome summary from the forward-outcome observation scaffold",
    )
    gate_value.add_argument("--db", default=None, help="ledger DB path")
    gate_value.add_argument("--horizon", type=int, default=20, choices=[5, 20, 60])
    gate_value.add_argument("--gate", default=None, help="filter to a single gate")
    gate_value.add_argument("--start-date", default=None)
    gate_value.add_argument("--end-date", default=None)

    scheduled_health = sub.add_parser(
        "scheduled-health",
        help="emit scheduled-job last-exit health as JSON",
    )
    scheduled_health.add_argument(
        "--status-json",
        default=None,
        help="optional JSON file with per-job last_exit/last_log_path facts",
    )
    scheduled_health.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when any scheduled job is classified crash/reject",
    )

    signal_pipeline = sub.add_parser(
        "signal-pipeline",
        help="show signal pipeline configuration and readiness status (106 flag-off)",
    )
    signal_pipeline.add_argument(
        "--config", default=None,
        help="path to signal pipeline config JSON (default: built-in defaults)",
    )
    signal_pipeline.add_argument(
        "--data-root", default=None,
        help="data root for readiness check",
    )
    signal_pipeline.add_argument(
        "--json", action="store_true", dest="signal_json",
        help="output as JSON",
    )

    model_fresh = sub.add_parser(
        "model-freshness",
        help="check model freshness across all populations (prod/shadow/tournament)",
    )
    model_fresh.add_argument("freshness_args", nargs=argparse.REMAINDER)

    model_enforce = sub.add_parser(
        "model-freshness-enforce",
        help="check prod panel freshness and recommend fallback if stale",
    )
    model_enforce.add_argument("enforce_args", nargs=argparse.REMAINDER)

    ledger_q = sub.add_parser(
        "ledger-query",
        help="query the decision ledger for gate verdicts by date and scope",
    )
    ledger_q.add_argument("--date", default=None, help="YYYY-MM-DD (default today)")
    ledger_q.add_argument("--scope", default="daily", help="scope filter (default 'daily')")
    ledger_q.add_argument("--db", default=None, help="ledger DB path (default ~/renquant-data/decision_ledger.db)")
    ledger_q.add_argument("--verdict", default=None, choices=("allow", "halve", "block"),
                          help="filter by verdict")
    ledger_q.add_argument("--gate", default=None, help="filter by gate name (substring match)")
    ledger_q.add_argument("--days", type=int, default=None,
                          help="show last N days instead of a single date")
    ledger_q.add_argument("--summary", action="store_true",
                          help="print per-gate verdict counts instead of individual rows")

    weekly_promote = sub.add_parser(
        "weekly-promote-health",
        help="emit weekly model-promote chain liveness/health as JSON and alert on stale/errored runs",
    )
    weekly_promote.add_argument(
        "--prod-artifacts-dir",
        default=None,
        help="override artifacts/prod dir; default <repo-root>/backtesting/renquant_104/artifacts/prod",
    )
    weekly_promote.add_argument(
        "--promote-log-dir",
        default=None,
        help="override promote-log dir; default <repo-root>/logs/weekly_wf_promote",
    )
    weekly_promote.add_argument(
        "--stale-after-days",
        type=int,
        default=None,
        help="staleness tolerance in days; default STALE_AFTER_DAYS",
    )
    weekly_promote.add_argument("--topic", default=None, help="ntfy topic for alerts")
    weekly_promote.add_argument(
        "--quiet",
        action="store_true",
        help="compute and emit the health record but do not post an ntfy alert",
    )

    trading_health = sub.add_parser(
        "daily-trading-health",
        help="emit + persist a read-only daily trading-health record (account "
        "trading / model health / cash deployment) and alert on a bad day",
    )
    trading_health.add_argument("--run-id", default=None)
    trading_health.add_argument(
        "--as-of", default=None, help="YYYY-MM-DD; defaults to today (UTC)"
    )
    trading_health.add_argument("--broker-name", default="readonly-alpaca")
    trading_health.add_argument(
        "--run-bundle", default=None, help="path to a daily run_bundle.json"
    )
    trading_health.add_argument(
        "--account-snapshot", default=None, help="path to an account snapshot JSON"
    )
    trading_health.add_argument(
        "--artifact-path", default=None, help="path to the live scorer artifact"
    )
    trading_health.add_argument("--ledger-db", default=None)
    trading_health.add_argument(
        "--no-persist", action="store_true", help="skip writing to the decision ledger"
    )
    trading_health.add_argument(
        "--quiet", action="store_true", help="never send the ntfy alert"
    )

    engineering_census = sub.add_parser(
        "engineering-census",
        help="emit reproducible engineering census metrics for docs/CI",
    )
    engineering_census.add_argument(
        "--github-root",
        type=Path,
        default=None,
        help="checkout parent containing renquant-* repos; default RENQUANT_GITHUB_ROOT or sibling root",
    )
    engineering_census.add_argument(
        "--pipeline-src",
        type=Path,
        default=None,
        help="override renquant-pipeline/src for isolated tests or branch audits",
    )
    engineering_census.add_argument(
        "--strategy-config",
        action="append",
        type=Path,
        default=None,
        help="strategy_config.json path to census; may be passed more than once",
    )
    engineering_census.add_argument(
        "--expect-buy-blocked-writers",
        type=int,
        default=None,
        help="optional fail-closed expectation for AST-counted buy_blocked=True writers",
    )
    engineering_census.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when required paths are missing or expectations fail",
    )

    parity = sub.add_parser(
        "live-parity-fixture",
        help="compare umbrella-bridge and native live run bundles for offboard parity",
    )
    parity.add_argument("--bridge-bundle", required=True)
    parity.add_argument("--native-bundle", required=True)
    parity.add_argument("--output-json", default=None)
    parity.add_argument("--fail-on-diff", action="store_true")

    parity_payloads = sub.add_parser(
        "live-parity-from-payloads",
        help="build a native live bundle from payloads and compare it to a bridge bundle",
    )
    parity_payloads.add_argument("--bridge-bundle", required=True)
    parity_payloads.add_argument("--inference-json", required=True)
    parity_payloads.add_argument("--execution-json", default=None)
    parity_payloads.add_argument("--metadata-json", default=None)
    parity_payloads.add_argument("--native-bundle-output", required=True)
    parity_payloads.add_argument("--output-json", default=None)
    parity_payloads.add_argument("--fail-on-diff", action="store_true")

    native_bundle = sub.add_parser(
        "native-live-bundle",
        help="build a native live run bundle for live.runner offboard parity",
    )
    native_bundle.add_argument("--inference-json", required=True)
    native_bundle.add_argument("--execution-json", default=None)
    native_bundle.add_argument("--metadata-json", default=None)
    native_bundle.add_argument("--output-json", required=True)

    native_execution = sub.add_parser(
        "native-execution-payload",
        help="build a readonly native execution payload from a native inference payload",
    )
    native_execution.add_argument("--inference-json", required=True)
    native_execution.add_argument("--output-json", required=True)
    native_execution.add_argument("--broker-name", default="readonly-native")

    native_inference = sub.add_parser(
        "native-live-inference",
        help="build a native live inference payload from an already-hydrated context",
    )
    native_inference.add_argument("--context-json", required=True)
    native_inference.add_argument("--output-json", required=True)
    native_inference.add_argument("--metadata-json", default=None)
    native_inference.add_argument("--sell-only", action="store_true")
    # §2a arm path (emitted by shadow_ab_runner.build_arm_plan): hydrate the
    # pinned pipeline's REAL InferenceContext before InferencePipeline.run —
    # the 2026-07-10 first real session proved a bare namespace cannot drive
    # the pinned pipeline (ctx.today AttributeError, pp_inference.py:307).
    native_inference.add_argument("--hydrate-pipeline-context", action="store_true")
    native_inference.add_argument("--session-date", default=None)
    native_inference.add_argument("--broker-name", default=None)
    native_inference.add_argument("--strategy-dir", default=None)
    native_inference.add_argument("--repo-root", default=None)
    native_inference.add_argument("--artifact-store", default=None)
    native_inference.add_argument("--log-containment-dir", default=None)
    native_inference.add_argument("--ohlcv-dir", default=None)
    native_inference.add_argument("--data-revision", default=None)

    native_context = sub.add_parser(
        "native-live-context",
        help="build a native live context fixture from config/market/account snapshots",
    )
    native_context.add_argument("--strategy-config-json", required=True)
    native_context.add_argument("--market-snapshot-json", required=True)
    native_context.add_argument("--account-snapshot-json", required=True)
    native_context.add_argument("--metadata-json", default=None)
    native_context.add_argument("--output-json", required=True)
    # §2a paired-world verification args (optional; emitted by the shadow-ab
    # runner's build_arm_plan): the module main() accepted these but this
    # subparser never did, so the first REAL two-arm session died with
    # "unrecognized arguments" + paired invalidation (2026-07-10 session
    # bundle). Keep this surface in lockstep with what build_arm_plan emits.
    native_context.add_argument("--decision-snapshot-digest", default=None)
    native_context.add_argument("--model-content-sha256", default=None)
    native_context.add_argument("--calibrator-content-sha256", default=None)
    native_context.add_argument("--session-date", default=None)
    native_context.add_argument("--strategy-dir", default=None)
    native_context.add_argument("--repo-root", default=None)
    native_context.add_argument("--artifact-store", default=None)

    native_run = sub.add_parser(
        "native-live-run",
        help="build a readonly native live run bundle (§2a shadow-ab arm step)",
    )
    # Exactly the surface the shadow-ab runner's build_arm_plan emits — no
    # more (the module's live-commit flags stay off the top-level CLI); this
    # subcommand did not exist at all, which was the second latent break on
    # the two-arm session path.
    native_run.add_argument("--inference-json", required=True)
    native_run.add_argument("--execution-output-json", default=None)
    native_run.add_argument("--output-json", required=True)
    native_run.add_argument("--broker-name", default="readonly-native")
    native_run.add_argument("--run-id", default=None)
    native_run.add_argument("--strategy-dir", default=None)
    native_run.add_argument("--runs-db", default=None)
    native_run.add_argument("--live-state-broker-name", default=None)
    native_run.add_argument("--live-state-contract-output-json", default=None)

    account_snapshot = sub.add_parser(
        "native-live-account-snapshot",
        help="build a readonly native account snapshot from broker read APIs",
    )
    account_snapshot.add_argument("--broker-name", default="readonly-alpaca")
    account_snapshot.add_argument("--metadata-json", default=None)
    account_snapshot.add_argument("--output-json", required=True)

    market_snapshot = sub.add_parser(
        "native-live-market-snapshot",
        help="build a native market snapshot from explicit price inputs",
    )
    market_snapshot.add_argument("--as-of", required=True)
    market_snapshot.add_argument("--prices-json", required=True)
    market_snapshot.add_argument("--metadata-json", default=None)
    market_snapshot.add_argument("--output-json", required=True)

    rehearsal = sub.add_parser(
        "live-rehearsal-plan",
        help="emit the readonly live offboard rehearsal command plan as JSON",
    )
    rehearsal.add_argument("--mode", choices=("live", "daily"), default="live")
    rehearsal.add_argument("--broker", default="readonly-alpaca")
    rehearsal.add_argument("--output-dir", default="/tmp/renquant-live-rehearsal")
    rehearsal.add_argument(
        "--env-file",
        default=None,
        help="optional .env file used only to check required credential presence",
    )
    rehearsal.add_argument(
        "--no-execution-payload",
        action="store_true",
        help="omit the execution payload input from the native parity command",
    )
    rehearsal.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when the rehearsal preflight is not ready",
    )

    offboard_status = sub.add_parser(
        "live-offboard-status",
        help="emit live bridge offboard readiness as JSON",
    )
    offboard_status.add_argument("--mode", choices=("live", "daily"), default="live")
    offboard_status.add_argument("--broker", default="readonly-alpaca")
    offboard_status.add_argument("--output-dir", default="/tmp/renquant-live-rehearsal")
    offboard_status.add_argument(
        "--env-file",
        default=None,
        help="optional .env file used only to check required credential presence",
    )
    offboard_status.add_argument(
        "--no-execution-payload",
        action="store_true",
        help="omit the execution payload input from the native parity command",
    )
    offboard_status.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero until the live bridge offboard status is ready",
    )
    offboard_status.add_argument(
        "--scheduled-health-json",
        default=None,
        help="optional scheduled-health status source folded into the offboard JSON",
    )
    offboard_rehearsal = sub.add_parser(
        "live-offboard-rehearsal",
        help="run the readonly live offboard bridge/native/parity evidence chain",
    )
    offboard_rehearsal.add_argument("--mode", choices=("live", "daily"), default="live")
    offboard_rehearsal.add_argument("--broker", default="readonly-alpaca")
    offboard_rehearsal.add_argument("--output-dir", default="/tmp/renquant-live-rehearsal")
    offboard_rehearsal.add_argument("--env-file", default=None)
    offboard_rehearsal.add_argument("--no-execution-payload", action="store_true")
    offboard_rehearsal.add_argument("--continue-on-failure", action="store_true")
    offboard_rehearsal.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero until readonly bridge/native/parity rehearsal is green",
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

    wf_triage = sub.add_parser(
        "wf-promote-triage",
        help="classify weekly WF promote log failures as JSON",
    )
    wf_triage.add_argument("--log-dir", required=True)
    wf_triage.add_argument(
        "--since",
        default=None,
        help="only include logs whose filename date is >= YYYY-MM-DD",
    )
    wf_triage.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when any included log failed or could not be classified",
    )

    decision_validate = sub.add_parser(
        "decision-validate",
        help="validate gate accuracy against realized forward outcomes",
    )
    decision_validate.add_argument(
        "decision_validate_args", nargs=argparse.REMAINDER,
        help="pass-through args to decision_outcome_validator.main",
    )

    sign_launder = sub.add_parser(
        "sign-laundering",
        help="measure sign laundering in scorer/calibrator artifacts",
    )
    sign_launder.add_argument(
        "sign_launder_args", nargs=argparse.REMAINDER,
        help="pass-through args to sign_laundering_harness.main",
    )

    gate_cal = sub.add_parser(
        "gate-calibration",
        help="gate threshold calibration diagnostic — are gates achievable?",
    )
    gate_cal.add_argument(
        "gate_cal_args", nargs=argparse.REMAINDER,
        help="pass-through args to gate_calibration_diagnostic.main",
    )

    outcome_bf = sub.add_parser(
        "outcome-backfill",
        help="backfill decision_outcomes from candidate_scores + forward returns",
    )
    outcome_bf.add_argument(
        "outcome_backfill_args", nargs=argparse.REMAINDER,
        help="pass-through args to outcome_backfiller.main",
    )

    observe = sub.add_parser(
        "observe-outcomes",
        help="S5 Path B: populate decision_outcomes from forward returns",
    )
    observe.add_argument(
        "observe_args", nargs=argparse.REMAINDER,
        help="pass-through args to outcome_observer.main",
    )

    decision_pnl = sub.add_parser(
        "decision-pnl",
        help="per-decision P&L attribution from candidate_scores + forward returns",
    )
    decision_pnl.add_argument(
        "--db", default=None,
        help="run DB path (default: runs.alpaca.db)",
    )

    parking = sub.add_parser(
        "parking-sleeve",
        help="compute shadow parking-sleeve allocation (S7, observe-only)",
    )
    parking.add_argument(
        "parking_args", nargs=argparse.REMAINDER,
        help="pass-through args to parking_sleeve.main",
    )

    tc = sub.add_parser(
        "transfer-coefficient",
        help="measure transfer coefficient (TC) from the run DB (S-TC)",
    )
    tc.add_argument(
        "tc_args", nargs=argparse.REMAINDER,
        help="pass-through args to transfer_coefficient.main",
    )

    shadow_ab = sub.add_parser(
        "shadow-ab",
        help="two-arm shadow A/B session runner (D6-§2a P-2; uninvoked prerequisite)",
    )
    shadow_ab.add_argument(
        "shadow_ab_args", nargs=argparse.REMAINDER,
        help="pass-through args to shadow_ab_runner.main",
    )

    deploy_pin = sub.add_parser(
        "deploy-pin",
        help=(
            "R-PIN deployment-pin authority CLI (Stage 1: capture the "
            "deployed truth into the neutral state root; dry-run default)"
        ),
    )
    deploy_pin.add_argument(
        "deploy_pin_args", nargs=argparse.REMAINDER,
        help="pass-through args to deploy_pin.main",
    )

    readiness = sub.add_parser(
        "readiness-monitor",
        help="data-accumulation readiness dashboard — check all gates and "
             "report progress toward the unified master plan (#231)",
    )
    readiness.add_argument(
        "readiness_args", nargs=argparse.REMAINDER,
        help="pass-through args to readiness_monitor.main",
    )

    outage = sub.add_parser(
        "outage-monitor",
        help="render a run bundle's funnel_integrity/data_availability blocks "
             "into the OUTAGE/DEGRADED/NO-TRADE/TRADE ntfy session page "
             "(pipeline #186/#187 consumer; DARK — no scheduled job yet)",
    )
    outage.add_argument(
        "outage_args", nargs=argparse.REMAINDER,
        help="pass-through args to outage_monitor.main",
    )

    tripwire = sub.add_parser(
        "identity-tripwire",
        help="compare the latest run bundle's model identity against the "
             "previous session's and the deployment manifest; page OUTAGE "
             "on an unexplained model swap (#484 §7.2a consumer; DARK — no "
             "scheduled job yet)",
    )
    tripwire.add_argument(
        "tripwire_args", nargs=argparse.REMAINDER,
        help="pass-through args to model_identity_tripwire.main",
    )

    edgar = sub.add_parser(
        "edgar-harvest",
        help="schedule a SEC EDGAR companyfacts harvest (N3 data collection)",
    )
    edgar.add_argument(
        "edgar_args", nargs=argparse.REMAINDER,
        help="pass-through args to sec_edgar_harvester.main",
    )

    entry_timing = sub.add_parser(
        "entry-timing",
        help="renquant105 entry-timing policy shadow evaluation: report + replay",
    )
    entry_timing.add_argument(
        "entry_timing_args", nargs=argparse.REMAINDER,
        help="pass-through args to entry_timing_policy.main",
    )

    train_gbdt_p = sub.add_parser(
        "train-gbdt",
        help="run the self-contained GBDT panel-LTR training pipeline",
    )
    train_gbdt_p.add_argument(
        "train_gbdt_args", nargs=argparse.REMAINDER,
        help="pass-through args to train_gbdt.main",
    )

    patchtst_cutoff = sub.add_parser(
        "patchtst-cutoff",
        help="derive the weekly PatchTST retrain cutoff from the training-corpus frontier",
    )
    patchtst_cutoff.add_argument(
        "patchtst_cutoff_args", nargs=argparse.REMAINDER,
        help="pass-through args to patchtst_weekly_cutoff.main",
    )

    replay_audit = sub.add_parser(
        "replay-audit",
        help="replay a recorded 105 shadow session and audit decision "
             "reproducibility (RFC #208 §6/§9)",
    )
    replay_audit.add_argument(
        "replay_audit_args", nargs=argparse.REMAINDER,
        help="pass-through args to intraday_replay_audit.main",
    )

    risk_budget_rpt = sub.add_parser(
        "risk-budget-report",
        help="observe-only risk-budget statement (read-only over the run DB)",
    )
    risk_budget_rpt.add_argument(
        "risk_budget_args", nargs=argparse.REMAINDER,
        help="pass-through args to risk_budget.report.main",
    )

    roadmap = sub.add_parser(
        "roadmap",
        help="roadmap implementation driver: emit the next backlog item as an "
             "agent task (the 'implement' half the agent-pr-loop was missing)",
    )
    roadmap.add_argument("roadmap_action", choices=["status", "next", "mark"])
    roadmap.add_argument("item_id", nargs="?")
    roadmap.add_argument("new_status", nargs="?")
    roadmap.add_argument("--backlog", default=None,
                         help="backlog json (default: doc/roadmap-backlog.json)")
    roadmap.add_argument("--allow-consequential", action="store_true",
                         help="let 'next' pick operator-only (GPU/deploy/live) items")

    prune = sub.add_parser(
        "prune-artifacts",
        help="prune stale promote-pipeline staging/rollback/backup artifacts (dry-run by default)",
    )
    prune.add_argument(
        "--execute",
        action="store_true",
        help="actually delete files (default: dry-run, list only)",
    )
    prune.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="umbrella repo root; default: /Users/renhao/git/github/RenQuant",
    )
    prune.add_argument(
        "--json",
        action="store_true",
        dest="prune_json",
        help="emit machine-readable JSON instead of human summary",
    )

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

    autoloop = sub.add_parser(
        "agent-automation",
        help="deterministic agent-automation control plane: replay events "
             "through the atomic state/lease store + state machine (design #209 "
             "Phase-0/1). No merge, no push, sandbox executor stubbed.",
    )
    autoloop.add_argument("--config", required=True,
                          help="poller config JSON (tracked_repos/tracked_prs/…)")
    autoloop.add_argument("--events", default=None,
                          help="optional recorded-event JSON to replay (shadow harness)")
    autoloop.add_argument("--db", default=":memory:",
                          help="SQLite state-store path; default in-memory")
    autoloop.add_argument("--dry-run", action="store_true",
                          help="force dry-run: never invoke the (stubbed) sandbox executor")
    autoloop.add_argument(
        "--poll-interval-seconds", type=float, default=None,
        help="run the live durable-inbox recovery loop (run_poll_loop): call "
             "AutomationPoller.tick every N seconds, after any --events "
             "replay, for as long as this process stays up. Unset = one-shot "
             "(default). With --poll-max-iterations unset this blocks forever.",
    )
    autoloop.add_argument(
        "--poll-max-iterations", type=int, default=None,
        help="bound --poll-interval-seconds to N ticks and return (CI/tests); "
             "default runs forever",
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

    m4b_replay = sub.add_parser(
        "conviction-replay",
        help="M4-b matched-breadth conviction-floor replay harness",
    )
    m4b_replay.add_argument(
        "m4b_args", nargs=argparse.REMAINDER,
        help="pass-through args to m4b_conviction_replay.main",
    )

    m6_restamp_p = sub.add_parser(
        "m6-restamp",
        help="M6 fingerprint re-stamp tool (dry-run by default)",
    )
    m6_restamp_p.add_argument(
        "m6_args", nargs=argparse.REMAINDER,
        help="pass-through args to m6_restamp.main",
    )

    merge_audit = sub.add_parser(
        "merge-audit",
        help="audit recent merged PRs for pre-merge `merged by` comments",
    )
    merge_audit.add_argument("--repo", default="hallovorld/RenQuant")
    merge_audit.add_argument("--limit", type=int, default=50)
    merge_audit.add_argument("--token", default=None)
    merge_audit.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when any audited PR lacks a pre-merge audit comment",
    )

    # The single cross-repo control-plane entrypoint (design PR #23).
    repos_p = sub.add_parser(
        "repos",
        help="cross-repo control plane (list/status/sync/prs/exec/agent) "
             "driven by subrepos.lock.json",
    )
    repos_p.add_argument("repos_action",
                         choices=("list", "status", "sync", "prs", "merge-audit", "exec", "agent"))
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
    repos_p.add_argument("--limit", type=int, default=50,
                         help="for action=merge-audit: merged PRs to audit per repo")
    repos_p.add_argument(
        "--strict",
        dest="repos_strict",
        action="store_true",
        help="for action=merge-audit: return non-zero on missing pre-merge markers",
    )

    # `repos exec` takes its command after a literal `--`. Split it off
    # BEFORE argparse so it can't swallow this command's own flags
    # (REMAINDER is too greedy and ate --as/--workflow). Mirrors the
    # bridge arg-splitting pattern.
    repos_exec_cmd: list[str] = []
    if raw_argv and raw_argv[0] == "repos" and "--" in raw_argv:
        sep = raw_argv.index("--")
        repos_exec_cmd = raw_argv[sep + 1:]
        raw_argv = raw_argv[:sep]

    replay_audit_argv: list[str] = []
    if raw_argv and raw_argv[0] == "replay-audit":
        replay_audit_argv = raw_argv[1:]
        raw_argv = raw_argv[:1]

    args, unknown = parser.parse_known_args(raw_argv)
    _remainder_commands = {
        "live-bridge", "daily-bridge", "edgar-harvest", "parking-sleeve",
        "transfer-coefficient", "shadow-ab", "readiness-monitor", "entry-timing",
        "train-gbdt", "patchtst-cutoff", "risk-budget-report",
        "conviction-replay", "m6-restamp", "deploy-pin", "outage-monitor",
        "identity-tripwire",
    }
    if unknown and args.command not in _remainder_commands:
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
            repo_dir_arg, env_file_arg, runner_args = _split_bridge_args(raw_argv)
        except FileNotFoundError as exc:
            parser.error(str(exc))
        except ValueError as exc:
            parser.error(str(exc))
        if env_file_arg is not None:
            from .env_files import load_env_file

            try:
                load_env_file(env_file_arg)
            except FileNotFoundError as exc:
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
    if args.command == "gate-value":
        from .ledger_attribution import (
            connect_attribution,
            gate_information_value,
            gate_value_report,
        )

        conn = connect_attribution(args.db or None)
        if args.gate:
            result = gate_information_value(
                conn, args.gate, horizon=args.horizon,
                start_date=args.start_date, end_date=args.end_date,
            )
        else:
            result = gate_value_report(
                conn, horizon=args.horizon, gate=args.gate,
                start_date=args.start_date, end_date=args.end_date,
            )
        conn.close()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "signal-pipeline":
        from .signal_pipeline_config import main as spc_main

        spc_argv = []
        if args.config:
            spc_argv.extend(["--config", args.config])
        if args.data_root:
            spc_argv.extend(["--data-root", args.data_root])
        if args.signal_json:
            spc_argv.append("--json")
        return spc_main(spc_argv)
    if args.command == "model-freshness":
        from .model_freshness_monitor import main as mfm_main

        return mfm_main(args.freshness_args or None)
    if args.command == "model-freshness-enforce":
        from .model_freshness_enforcer import main as mfe_main

        return mfe_main(args.enforce_args or None)
    if args.command == "ledger-query":
        from .decision_ledger import connect, verdicts_for

        db_path = args.db or None
        conn = connect(db_path)
        today = dt.date.today().isoformat()
        if args.days:
            base = dt.date.fromisoformat(args.date or today)
            dates = [(base - dt.timedelta(days=i)).isoformat() for i in range(args.days)]
        else:
            dates = [args.date or today]

        all_rows: list[dict] = []
        for d in dates:
            rows = verdicts_for(conn, d, args.scope)
            for r in rows:
                r["date"] = d
            all_rows.extend(rows)
        conn.close()

        if args.verdict:
            all_rows = [r for r in all_rows if r["verdict"] == args.verdict]
        if args.gate:
            all_rows = [r for r in all_rows if args.gate in r["gate"]]

        if args.summary:
            counts: dict[str, dict[str, int]] = {}
            for r in all_rows:
                g = r["gate"]
                v = r["verdict"]
                counts.setdefault(g, {"allow": 0, "halve": 0, "block": 0})[v] += 1
            print(json.dumps(counts, indent=2, sort_keys=True))
        else:
            print(json.dumps(all_rows, indent=2, sort_keys=True))
        return 0
    if args.command == "scheduled-health":
        from .scheduled_health import build_scheduled_health

        health = build_scheduled_health(status_json=args.status_json)
        print(json.dumps(health, indent=2, sort_keys=True))
        if args.strict and health["summary"]["red_job_count"]:
            return 2
        return 0
    if args.command == "weekly-promote-health":
        from .weekly_promote_monitor import (
            DEFAULT_NTFY_TOPIC,
            STALE_AFTER_DAYS,
            build_weekly_promote_health,
            emit_alert,
        )

        health = build_weekly_promote_health(
            prod_artifacts_dir=args.prod_artifacts_dir,
            promote_log_dir=args.promote_log_dir,
            stale_after_days=(
                args.stale_after_days if args.stale_after_days is not None else STALE_AFTER_DAYS
            ),
        )
        emit_alert(health, topic=args.topic or DEFAULT_NTFY_TOPIC, quiet=args.quiet)
        print(json.dumps(health, indent=2, sort_keys=True))
        return 2 if health["alert"] else 0

    if args.command == "daily-trading-health":
        from .daily_trading_health import main as trading_health_main

        trading_health_argv = ["--broker-name", args.broker_name]
        if args.run_id:
            trading_health_argv.extend(["--run-id", args.run_id])
        if args.as_of:
            trading_health_argv.extend(["--as-of", args.as_of])
        if args.run_bundle:
            trading_health_argv.extend(["--run-bundle", args.run_bundle])
        if args.account_snapshot:
            trading_health_argv.extend(["--account-snapshot", args.account_snapshot])
        if args.artifact_path:
            trading_health_argv.extend(["--artifact-path", args.artifact_path])
        if args.ledger_db:
            trading_health_argv.extend(["--ledger-db", args.ledger_db])
        if args.no_persist:
            trading_health_argv.append("--no-persist")
        if args.quiet:
            trading_health_argv.append("--quiet")
        return trading_health_main(trading_health_argv)
    if args.command == "engineering-census":
        from .engineering_census import build_engineering_census

        payload = build_engineering_census(
            github_root=args.github_root,
            pipeline_src=args.pipeline_src,
            strategy_configs=args.strategy_config,
            expect_buy_blocked_writers=args.expect_buy_blocked_writers,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] or not args.strict else 2
    if args.command == "live-parity-fixture":
        from .live_parity import main as parity_main

        parity_argv = [
            "--bridge-bundle",
            args.bridge_bundle,
            "--native-bundle",
            args.native_bundle,
        ]
        if args.output_json:
            parity_argv.extend(["--output-json", args.output_json])
        if args.fail_on_diff:
            parity_argv.append("--fail-on-diff")
        return parity_main(parity_argv)
    if args.command == "live-parity-from-payloads":
        from .live_parity_payloads import main as parity_payloads_main

        parity_payloads_argv = [
            "--bridge-bundle",
            args.bridge_bundle,
            "--inference-json",
            args.inference_json,
            "--native-bundle-output",
            args.native_bundle_output,
        ]
        if args.execution_json:
            parity_payloads_argv.extend(["--execution-json", args.execution_json])
        if args.metadata_json:
            parity_payloads_argv.extend(["--metadata-json", args.metadata_json])
        if args.output_json:
            parity_payloads_argv.extend(["--output-json", args.output_json])
        if args.fail_on_diff:
            parity_payloads_argv.append("--fail-on-diff")
        return parity_payloads_main(parity_payloads_argv)
    if args.command == "native-live-bundle":
        from .native_live_bundle import main as native_bundle_main

        native_bundle_argv = [
            "--inference-json",
            args.inference_json,
            "--output-json",
            args.output_json,
        ]
        if args.execution_json:
            native_bundle_argv.extend(["--execution-json", args.execution_json])
        if args.metadata_json:
            native_bundle_argv.extend(["--metadata-json", args.metadata_json])
        return native_bundle_main(native_bundle_argv)
    if args.command == "native-execution-payload":
        from .native_execution_payload import main as native_execution_main

        return native_execution_main([
            "--inference-json",
            args.inference_json,
            "--output-json",
            args.output_json,
            "--broker-name",
            args.broker_name,
        ])
    if args.command == "native-live-inference":
        from .native_live_inference import main as native_inference_main

        native_inference_argv = [
            "--context-json",
            args.context_json,
            "--output-json",
            args.output_json,
        ]
        if args.metadata_json:
            native_inference_argv.extend(["--metadata-json", args.metadata_json])
        if args.sell_only:
            native_inference_argv.append("--sell-only")
        if args.hydrate_pipeline_context:
            native_inference_argv.append("--hydrate-pipeline-context")
        for flag, value in (
            ("--session-date", args.session_date),
            ("--broker-name", args.broker_name),
            ("--strategy-dir", args.strategy_dir),
            ("--repo-root", args.repo_root),
            ("--ohlcv-dir", args.ohlcv_dir),
            ("--data-revision", args.data_revision),
            ("--artifact-store", args.artifact_store),
            ("--log-containment-dir", args.log_containment_dir),
        ):
            if value:
                native_inference_argv.extend([flag, value])
        return native_inference_main(native_inference_argv)
    if args.command == "native-live-context":
        from .native_live_context import main as native_context_main

        native_context_argv = [
            "--strategy-config-json",
            args.strategy_config_json,
            "--market-snapshot-json",
            args.market_snapshot_json,
            "--account-snapshot-json",
            args.account_snapshot_json,
            "--output-json",
            args.output_json,
        ]
        if args.metadata_json:
            native_context_argv.extend(["--metadata-json", args.metadata_json])
        if args.decision_snapshot_digest:
            native_context_argv.extend(
                ["--decision-snapshot-digest", args.decision_snapshot_digest]
            )
        if args.model_content_sha256:
            native_context_argv.extend(
                ["--model-content-sha256", args.model_content_sha256]
            )
        if args.calibrator_content_sha256:
            native_context_argv.extend(
                ["--calibrator-content-sha256", args.calibrator_content_sha256]
            )
        if args.session_date:
            native_context_argv.extend(["--session-date", args.session_date])
        if args.strategy_dir:
            native_context_argv.extend(["--strategy-dir", args.strategy_dir])
        if args.repo_root:
            native_context_argv.extend(["--repo-root", args.repo_root])
        if args.artifact_store:
            native_context_argv.extend(["--artifact-store", args.artifact_store])
        return native_context_main(native_context_argv)
    if args.command == "native-live-run":
        from .native_live_run import main as native_run_main

        native_run_argv = [
            "--inference-json",
            args.inference_json,
            "--output-json",
            args.output_json,
            "--broker-name",
            args.broker_name,
        ]
        for flag, value in (
            ("--execution-output-json", args.execution_output_json),
            ("--run-id", args.run_id),
            ("--strategy-dir", args.strategy_dir),
            ("--runs-db", args.runs_db),
            ("--live-state-broker-name", args.live_state_broker_name),
            (
                "--live-state-contract-output-json",
                args.live_state_contract_output_json,
            ),
        ):
            if value:
                native_run_argv.extend([flag, value])
        return native_run_main(native_run_argv)
    if args.command == "native-live-account-snapshot":
        from .native_live_snapshots import account_main

        account_argv = ["--broker-name", args.broker_name, "--output-json", args.output_json]
        if args.metadata_json:
            account_argv.extend(["--metadata-json", args.metadata_json])
        return account_main(account_argv)
    if args.command == "native-live-market-snapshot":
        from .native_live_snapshots import market_main

        market_argv = [
            "--as-of",
            args.as_of,
            "--prices-json",
            args.prices_json,
            "--output-json",
            args.output_json,
        ]
        if args.metadata_json:
            market_argv.extend(["--metadata-json", args.metadata_json])
        return market_main(market_argv)
    if args.command == "live-rehearsal-plan":
        from .live_rehearsal_plan import build_live_rehearsal_plan

        plan = build_live_rehearsal_plan(
            mode=args.mode,
            output_dir=args.output_dir,
            broker=args.broker,
            include_execution_payload=not args.no_execution_payload,
            env_file=args.env_file,
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0 if plan["ready"] or not args.strict else 2
    if args.command == "live-offboard-status":
        from .live_offboard_status import build_live_offboard_status

        status = build_live_offboard_status(
            mode=args.mode,
            output_dir=args.output_dir,
            broker=args.broker,
            include_execution_payload=not args.no_execution_payload,
            env_file=args.env_file,
            scheduled_health_json=args.scheduled_health_json,
        )
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0 if status["ready_for_live_offboard"] or not args.strict else 2
    if args.command == "live-offboard-rehearsal":
        from .live_offboard_rehearsal import run_live_offboard_rehearsal

        payload = run_live_offboard_rehearsal(
            mode=args.mode,
            output_dir=args.output_dir,
            broker=args.broker,
            env_file=args.env_file,
            include_execution_payload=not args.no_execution_payload,
            continue_on_failure=args.continue_on_failure,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] or not args.strict else 2
    if args.command == "run-job":
        from .job_runner import run_scheduled_job

        try:
            return run_scheduled_job(args.job_id, args.job_args)
        except ValueError as exc:
            parser.error(str(exc))
    if args.command == "wf-promote-triage":
        from .wf_promote_triage import triage_log_dir

        try:
            payload = triage_log_dir(Path(args.log_dir), since=args.since)
        except (FileNotFoundError, NotADirectoryError) as exc:
            parser.error(str(exc))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["summary"]["ok"] or not args.strict else 1
    if args.command == "decision-validate":
        from .decision_outcome_validator import main as dv_main

        return dv_main(args.decision_validate_args or None)
    if args.command == "sign-laundering":
        from .sign_laundering_harness import main as sl_main

        return sl_main(args.sign_launder_args or None)
    if args.command == "gate-calibration":
        from .gate_calibration_diagnostic import main as gc_main

        return gc_main(args.gate_cal_args or None)
    if args.command == "outcome-backfill":
        from .outcome_backfiller import main as ob_main

        return ob_main(args.outcome_backfill_args or None)
    if args.command == "observe-outcomes":
        from .outcome_observer import main as oo_main

        return oo_main(args.observe_args or None)
    if args.command == "decision-pnl":
        from .decision_pnl_attribution import (
            attribute_by_class,
            classify_decisions,
            connect as pnl_connect,
            load_decision_outcomes,
            selection_edge,
        )

        conn = pnl_connect(args.db or None)
        try:
            joined, ret_col = load_decision_outcomes(conn)
        finally:
            conn.close()
        classified = classify_decisions(joined)
        agg = attribute_by_class(classified, ret_col)
        edge = selection_edge(classified, ret_col)
        by_class = [
            {
                "class": cls_name,
                "count": int(row["count"]),
                "mean": float(row["mean"]),
                "median": float(row["median"]),
            }
            for cls_name, row in agg.iterrows()
        ]
        result = {
            "return_column": ret_col,
            "n_decisions": len(classified),
            "edge": edge,
            "by_class": by_class,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
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
            require_distinct_actor_tokens=args.workflow == "merge" and args.execute,
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 1 if plan.get("merge_blocked") else 0
    if args.command == "agent-automation":
        from .agent_automation_poller import run_cli

        summary = run_cli(
            config_path=args.config,
            events_path=args.events,
            db_path=args.db,
            dry_run=args.dry_run,
            poll_interval_seconds=args.poll_interval_seconds,
            poll_max_iterations=args.poll_max_iterations,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary.get("human_gate_wall_ok") else 1
    if args.command == "agent-identity":
        from .agent_workflows import agent_identity_health

        health = agent_identity_health(
            claude_token=args.claude_token,
            codex_token=args.codex_token,
            require_actor_tokens=args.strict,
        )
        print(json.dumps(health, indent=2, sort_keys=True))
        return 0 if health["ok"] or not args.strict else 1
    if args.command == "merge-audit":
        from .agent_workflows import audit_merged_prs

        audit = audit_merged_prs(args.repo, args.token, limit=args.limit)
        print(json.dumps(audit, indent=2, sort_keys=True))
        return 0 if audit["ok"] or not args.strict else 1
    if args.command == "prune-artifacts":
        from .retention_policy import main as prune_main

        prune_argv: list[str] = []
        if args.execute:
            prune_argv.append("--execute")
        if args.repo:
            prune_argv.extend(["--repo", str(args.repo)])
        if args.prune_json:
            prune_argv.append("--json")
        return prune_main(prune_argv)
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
                merge_audit_limit=args.limit,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, sort_keys=True))
        blocked = any(
            (repo.get("plan") or {}).get("merge_blocked")
            for repo in result.get("repos", [])
        )
        if args.repos_action == "merge-audit" and args.repos_strict and not result.get("ok"):
            return 1
        return 1 if blocked else 0
    if args.command == "roadmap":
        from pathlib import Path as _P

        from .roadmap_driver import (
            build_implementation_prompt,
            load_backlog,
            mark,
            next_item,
            save_backlog,
            status_table,
        )

        backlog_path = (_P(args.backlog) if args.backlog
                        else _P(__file__).resolve().parents[2] / "doc" / "roadmap-backlog.json")
        items = load_backlog(backlog_path)
        if args.roadmap_action == "status":
            print(status_table(items))
            return 0
        if args.roadmap_action == "next":
            nxt = next_item(items, allow_consequential=args.allow_consequential)
            if nxt is None:
                print("no actionable roadmap item")
                return 1
            print(build_implementation_prompt(nxt))
            return 0
        if args.roadmap_action == "mark":
            if not args.item_id or not args.new_status:
                parser.error("roadmap mark requires <id> <status>")
            mark(items, args.item_id, args.new_status)
            save_backlog(backlog_path, items)
            print(f"marked {args.item_id} -> {args.new_status}")
            return 0
    if args.command == "parking-sleeve":
        from .parking_sleeve import main as ps_main

        ps_argv = unknown + (args.parking_args or [])
        return ps_main(ps_argv or None)
    if args.command == "transfer-coefficient":
        from .transfer_coefficient import main as tc_main

        tc_argv = unknown + (args.tc_args or [])
        return tc_main(tc_argv or None)
    if args.command == "shadow-ab":
        from .shadow_ab_runner import main as shadow_ab_main

        shadow_ab_argv = unknown + (args.shadow_ab_args or [])
        return shadow_ab_main(shadow_ab_argv or None)
    if args.command == "deploy-pin":
        from .deploy_pin import main as deploy_pin_main

        deploy_pin_argv = unknown + (args.deploy_pin_args or [])
        return deploy_pin_main(deploy_pin_argv or None)
    if args.command == "readiness-monitor":
        from .readiness_monitor import main as rm_main

        rm_argv = unknown + (args.readiness_args or [])
        return rm_main(rm_argv or None)
    if args.command == "outage-monitor":
        from .outage_monitor import main as outage_main

        outage_argv = unknown + (args.outage_args or [])
        return outage_main(outage_argv or None)
    if args.command == "identity-tripwire":
        from .model_identity_tripwire import main as tripwire_main

        tripwire_argv = unknown + (args.tripwire_args or [])
        return tripwire_main(tripwire_argv or None)
    if args.command == "edgar-harvest":
        from .sec_edgar_harvester import main as edgar_main

        edgar_argv = unknown + (args.edgar_args or [])
        return edgar_main(edgar_argv or None)
    if args.command == "entry-timing":
        from .entry_timing_policy import main as et_main

        et_argv = unknown + (args.entry_timing_args or [])
        return et_main(et_argv or None)
    if args.command == "train-gbdt":
        from .train_gbdt import main as tg_main

        tg_argv = unknown + (args.train_gbdt_args or [])
        return tg_main(tg_argv or None)
    if args.command == "patchtst-cutoff":
        from .patchtst_weekly_cutoff import main as pwc_main

        pwc_argv = unknown + (args.patchtst_cutoff_args or [])
        return pwc_main(pwc_argv or None)
    if args.command == "replay-audit":
        from .intraday_replay_audit import main as ra_main

        return ra_main(replay_audit_argv or None)
    if args.command == "risk-budget-report":
        from .risk_budget.report import main as rb_main

        rb_argv = unknown + (args.risk_budget_args or [])
        return rb_main(rb_argv or None)
    if args.command == "conviction-replay":
        from .m4b_conviction_replay import main as m4b_main

        m4b_argv = unknown + (args.m4b_args or [])
        return m4b_main(m4b_argv or None)
    if args.command == "m6-restamp":
        from .m6_restamp import main as m6_main

        m6_argv = unknown + (args.m6_args or [])
        return m6_main(m6_argv or None)
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
