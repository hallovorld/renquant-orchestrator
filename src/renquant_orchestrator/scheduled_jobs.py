"""Machine-readable scheduled-job inventory for the multirepo migration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Literal

from .runtime_paths import default_repo_root


JobKind = Literal["training", "inference", "trading", "ops", "control"]
MigrationState = Literal["native_multirepo", "umbrella_bridge"]
CANONICAL_REPO_ROOT = "/Users/renhao/git/github/RenQuant"


def _localize_repo_root(value: object, *, repo_root: str | None = None) -> object:
    """Rewrite canonical umbrella paths to the active runtime repo root."""
    root = repo_root or str(default_repo_root())
    if isinstance(value, str) and value.startswith(CANONICAL_REPO_ROOT):
        return root + value[len(CANONICAL_REPO_ROOT):]
    if isinstance(value, list):
        return [_localize_repo_root(item, repo_root=root) for item in value]
    return value


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    kind: JobKind
    cadence: str
    command: list[str]
    owner_repo: str
    migration_state: MigrationState
    production_safe: bool
    rehearsal_command: list[str] | None = None
    native_replacement_job_id: str | None = None
    native_cutover_command: list[str] | None = None
    umbrella_code_dependency: str | None = None
    umbrella_state_dependency: str | None = None
    launchd_label: str | None = None
    launchd_stdout_path: str | None = None
    launchd_stderr_path: str | None = None
    native_offboard_blockers: tuple[str, ...] = ()
    native_exit_criteria: tuple[str, ...] = ()

    @property
    def uses_umbrella_code(self) -> bool:
        return self.umbrella_code_dependency is not None

    def to_jsonable(self) -> dict[str, object]:
        payload = asdict(self)
        payload["native_offboard_blockers"] = list(self.native_offboard_blockers)
        payload["native_exit_criteria"] = list(self.native_exit_criteria)
        payload["uses_umbrella_code"] = self.uses_umbrella_code
        repo_root = str(default_repo_root())
        return {
            key: _localize_repo_root(value, repo_root=repo_root)
            for key, value in payload.items()
        }


_JOBS: tuple[ScheduledJob, ...] = (
    ScheduledJob(
        job_id="weekly_alpha158_fund_retrain",
        kind="training",
        cadence="weekly",
        command=[
            "renquant-orchestrator",
            "run-job",
            "weekly_alpha158_fund_retrain",
            "--staged",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant/data and RenQuant/backtesting/renquant_104/artifacts/prod staging paths",
        launchd_label="com.renquant.retrain-panel104",
        launchd_stdout_path="/Users/renhao/git/github/RenQuant/logs/retrain_panel/launchd_stdout.log",
        launchd_stderr_path="/Users/renhao/git/github/RenQuant/logs/retrain_panel/launchd_stderr.log",
    ),
    ScheduledJob(
        job_id="weekly_patchtst_retrain",
        kind="training",
        cadence="weekly",
        command=[
            "renquant-orchestrator",
            "run-job",
            "weekly_patchtst_retrain",
            "--staged",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency=(
            "RenQuant/data and RenQuant/backtesting/renquant_104/artifacts/patchtst_staging staging paths"
        ),
        launchd_label="com.renquant.retrain-patchtst",
        launchd_stdout_path="/Users/renhao/git/github/RenQuant/logs/retrain_patchtst/launchd_stdout.log",
        launchd_stderr_path="/Users/renhao/git/github/RenQuant/logs/retrain_patchtst/launchd_stderr.log",
    ),
    ScheduledJob(
        job_id="daily_alpha158_linear_retrain",
        kind="training",
        cadence="daily",
        command=[
            "renquant-orchestrator",
            "run-job",
            "daily_alpha158_linear_retrain",
            "--staged",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant/data and RenQuant/backtesting/renquant_104/artifacts staging paths",
        launchd_label="com.renquant.retrain-alpha158-linear",
        launchd_stdout_path="/Users/renhao/git/github/RenQuant/logs/retrain_alpha158_linear/launchd_stdout.log",
        launchd_stderr_path="/Users/renhao/git/github/RenQuant/logs/retrain_alpha158_linear/launchd_stderr.log",
    ),
    ScheduledJob(
        job_id="market_anomaly_retrain_trigger",
        kind="control",
        cadence="scheduled",
        command=["renquant-orchestrator", "run-job", "market_anomaly_retrain_trigger"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
    ),
    ScheduledJob(
        job_id="daily_contract_fixture",
        kind="control",
        cadence="daily",
        command=["renquant-orchestrator", "run-job", "daily_contract_fixture"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
    ),
    ScheduledJob(
        job_id="native_live_parity_fixture",
        kind="control",
        cadence="manual_or_scheduled",
        command=["renquant-orchestrator", "run-job", "native_live_parity_fixture"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency=(
            "Readonly bridge/native run bundles until live state is fully offboarded"
        ),
    ),
    ScheduledJob(
        job_id="native_live_bundle_fixture",
        kind="control",
        cadence="manual_or_scheduled",
        command=["renquant-orchestrator", "run-job", "native_live_bundle_fixture"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency=(
            "Readonly native inference/execution payloads until live state is fully offboarded"
        ),
    ),
    ScheduledJob(
        job_id="native_live_payload_parity_fixture",
        kind="control",
        cadence="manual_or_scheduled",
        command=[
            "renquant-orchestrator",
            "run-job",
            "native_live_payload_parity_fixture",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency=(
            "Readonly bridge bundle plus native inference/execution payloads until live state is fully offboarded"
        ),
    ),
    ScheduledJob(
        job_id="native_live_execution_payload_fixture",
        kind="control",
        cadence="manual_or_scheduled",
        command=[
            "renquant-orchestrator",
            "run-job",
            "native_live_execution_payload_fixture",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency=(
            "Readonly native inference payload until live state is fully offboarded"
        ),
    ),
    ScheduledJob(
        job_id="native_live_run_candidate",
        kind="trading",
        cadence="manual_or_scheduled",
        command=[
            "renquant-orchestrator",
            "run-job",
            "native_live_run_candidate",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency=(
            "Readonly native inference payload until live context/state adapters are fully offboarded"
        ),
        native_exit_criteria=(
            "Candidate consumes native inference payloads and emits parity-ready native live bundles without importing RenQuant live.runner.",
            "Candidate remains readonly until live execution commit semantics are ported into renquant-execution.",
        ),
    ),
    ScheduledJob(
        job_id="daily_live_runner_bridge",
        kind="trading",
        cadence="daily",
        command=["renquant-orchestrator", "run-job", "daily_live_runner_bridge"],
        owner_repo="renquant-orchestrator",
        migration_state="umbrella_bridge",
        production_safe=True,
        rehearsal_command=[
            "renquant-orchestrator",
            "run-job",
            "daily_live_runner_bridge",
            "--",
            "--broker",
            "readonly-alpaca",
            "--once",
            "--bridge-bundle-output",
            "/tmp/renquant-daily-bridge-bundle.json",
        ],
        native_replacement_job_id="native_live_run_candidate",
        native_cutover_command=[
            "renquant-orchestrator",
            "run-job",
            "native_live_run_candidate",
            "--",
            "--inference-json",
            "/tmp/renquant-live-rehearsal/daily-native-inference.json",
            "--execution-output-json",
            "/tmp/renquant-live-rehearsal/daily-native-execution.json",
            "--commit-plan-output-json",
            "/tmp/renquant-live-rehearsal/daily-native-commit-plan.json",
            "--output-json",
            "/tmp/renquant-live-rehearsal/daily-native-bundle.json",
            "--broker-name",
            "readonly-alpaca",
            "--strategy-dir",
            "/Users/renhao/git/github/RenQuant/backtesting/renquant_104",
            "--runs-db",
            "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db",
            "--live-state-broker-name",
            "alpaca",
            "--live-state-contract-output-json",
            "/tmp/renquant-live-rehearsal/daily-live-state-contract.json",
        ],
        umbrella_code_dependency="RenQuant live.runner execution handoff",
        umbrella_state_dependency="RenQuant checkout for data, live_state, and runtime artifacts",
        launchd_label="com.renquant.daily104",
        launchd_stdout_path="/Users/renhao/git/github/RenQuant/logs/daily_104/launchd_stdout.log",
        launchd_stderr_path="/Users/renhao/git/github/RenQuant/logs/daily_104/launchd_stderr.log",
        native_offboard_blockers=(
            "Lift the live.runner state machine into a native orchestrator live job.",
            "Prove the pipeline live_state/runs DB contract artifact matches the bridge state semantics.",
            "Prove buy/sell/sell-only parity against the current live.runner path on readonly-alpaca.",
        ),
        native_exit_criteria=(
            "native_live_parity_fixture passes on a readonly daily fixture comparing decision_trace, order_intents, and state mutations.",
            "daily_live_runner_bridge migration_state can change only after native live job emits the same order intents, ntfy decision reasons, and state mutations as live.runner on a readonly fixture.",
            "Production launchd daily104 command points at renquant-orchestrator run-job with no RenQuant live.runner import.",
        ),
    ),
    ScheduledJob(
        job_id="live_runner_bridge",
        kind="inference",
        cadence="manual_or_scheduled",
        command=["renquant-orchestrator", "run-job", "live_runner_bridge"],
        owner_repo="renquant-orchestrator",
        migration_state="umbrella_bridge",
        production_safe=True,
        rehearsal_command=[
            "renquant-orchestrator",
            "run-job",
            "live_runner_bridge",
            "--",
            "--broker",
            "readonly-alpaca",
            "--once",
            "--bridge-bundle-output",
            "/tmp/renquant-live-bridge-bundle.json",
        ],
        native_replacement_job_id="native_live_run_candidate",
        native_cutover_command=[
            "renquant-orchestrator",
            "run-job",
            "native_live_run_candidate",
            "--",
            "--inference-json",
            "/tmp/renquant-live-rehearsal/live-native-inference.json",
            "--execution-output-json",
            "/tmp/renquant-live-rehearsal/live-native-execution.json",
            "--commit-plan-output-json",
            "/tmp/renquant-live-rehearsal/live-native-commit-plan.json",
            "--output-json",
            "/tmp/renquant-live-rehearsal/live-native-bundle.json",
            "--broker-name",
            "readonly-alpaca",
            "--strategy-dir",
            "/Users/renhao/git/github/RenQuant/backtesting/renquant_104",
            "--runs-db",
            "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db",
            "--live-state-broker-name",
            "alpaca",
            "--live-state-contract-output-json",
            "/tmp/renquant-live-rehearsal/live-live-state-contract.json",
        ],
        umbrella_code_dependency="RenQuant live.runner execution handoff",
        umbrella_state_dependency="RenQuant checkout for data, live_state, and runtime artifacts",
        native_offboard_blockers=(
            "Lift live.runner inference, risk-exit, and order-intent assembly into renquant-pipeline/orchestrator contracts.",
            "Replace umbrella module aliases with direct subrepo imports for all production inference stages.",
            "Add a native shadow fixture that compares decision_trace and order_intents against live.runner.",
        ),
        native_exit_criteria=(
            "native_live_parity_fixture passes on prod and readonly-shadow fixtures comparing decision_trace, order_intents, and state mutations.",
            "live_runner_bridge migration_state can change only after the native inference path passes parity on prod and readonly shadow configs.",
            "No scheduled inference job imports RenQuant live.runner or kernel aliases from the umbrella checkout.",
        ),
    ),
    ScheduledJob(
        job_id="weekly_apy_monitor",
        kind="ops",
        cadence="weekly",
        command=["renquant-orchestrator", "run-job", "weekly_apy_monitor"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency="RenQuant live_state and trade logs",
    ),
    ScheduledJob(
        job_id="state_backup",
        kind="ops",
        cadence="scheduled",
        command=["renquant-orchestrator", "run-job", "state_backup"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency="RenQuant data and live_state backup source",
    ),
    ScheduledJob(
        job_id="build_wf_manifest",
        kind="training",
        cadence="manual_or_scheduled",
        command=["renquant-orchestrator", "run-job", "build_wf_manifest"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant data and artifact output paths",
    ),
    ScheduledJob(
        job_id="build_patchtst_wf_manifest",
        kind="training",
        cadence="manual_or_scheduled",
        command=["renquant-orchestrator", "run-job", "build_patchtst_wf_manifest"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant data and artifact output paths",
    ),
)


def scheduled_jobs() -> tuple[ScheduledJob, ...]:
    return _JOBS


def inventory_payload() -> dict[str, object]:
    scheduled = scheduled_jobs()
    jobs = [job.to_jsonable() for job in scheduled]
    umbrella_bridge_jobs = [
        job.job_id for job in scheduled if job.migration_state == "umbrella_bridge"
    ]
    umbrella_state_dependency_jobs = [
        job.job_id for job in scheduled if job.umbrella_state_dependency is not None
    ]
    native_cutover_candidates = {
        str(job["job_id"]): {
            "native_replacement_job_id": job["native_replacement_job_id"],
            "native_cutover_command": job["native_cutover_command"],
        }
        for job in jobs
        if job["migration_state"] == "umbrella_bridge"
        and job["native_replacement_job_id"]
        and job["native_cutover_command"]
    }
    return {
        "schema_version": 1,
        "owner_repo": "renquant-orchestrator",
        "jobs": jobs,
        "summary": {
            "total": len(jobs),
            "native_multirepo": sum(job.migration_state == "native_multirepo" for job in scheduled),
            "umbrella_bridge": len(umbrella_bridge_jobs),
            "umbrella_bridge_jobs": umbrella_bridge_jobs,
            "remaining_umbrella_bridge_jobs": umbrella_bridge_jobs,
            "remaining_umbrella_bridge_job_count": len(umbrella_bridge_jobs),
            "native_offboard_blocker_count": sum(
                len(job.native_offboard_blockers) for job in scheduled
            ),
            "native_exit_criteria_count": sum(
                len(job.native_exit_criteria) for job in scheduled
            ),
            "umbrella_state_dependency_job_count": len(umbrella_state_dependency_jobs),
            "umbrella_state_dependency_jobs": umbrella_state_dependency_jobs,
            "production_safe_umbrella_bridge_jobs": [
                job.job_id for job in scheduled
                if job.migration_state == "umbrella_bridge" and job.production_safe
            ],
            "native_cutover_candidate_count": len(native_cutover_candidates),
            "native_cutover_candidates": native_cutover_candidates,
        },
    }


def inventory_json(*, indent: int | None = 2) -> str:
    return json.dumps(inventory_payload(), indent=indent, sort_keys=True)
