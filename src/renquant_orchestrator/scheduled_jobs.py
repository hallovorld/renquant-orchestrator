"""Machine-readable scheduled-job inventory for the multirepo migration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Literal


JobKind = Literal["training", "inference", "trading", "ops", "control"]
MigrationState = Literal["native_multirepo", "umbrella_bridge"]


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    kind: JobKind
    cadence: str
    command: list[str]
    owner_repo: str
    migration_state: MigrationState
    production_safe: bool
    umbrella_code_dependency: str | None = None
    umbrella_state_dependency: str | None = None

    @property
    def uses_umbrella_code(self) -> bool:
        return self.umbrella_code_dependency is not None

    def to_jsonable(self) -> dict[str, object]:
        payload = asdict(self)
        payload["uses_umbrella_code"] = self.uses_umbrella_code
        return payload


_JOBS: tuple[ScheduledJob, ...] = (
    ScheduledJob(
        job_id="weekly_alpha158_fund_retrain",
        kind="training",
        cadence="weekly",
        command=[
            "python",
            "-m",
            "renquant_orchestrator.retrain_alpha158_fund",
            "--staged",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant/data and RenQuant/backtesting/renquant_104/artifacts/prod staging paths",
    ),
    ScheduledJob(
        job_id="daily_alpha158_linear_retrain",
        kind="training",
        cadence="daily",
        command=[
            "python",
            "-m",
            "renquant_orchestrator.retrain_alpha158_linear",
            "--staged",
        ],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=False,
        umbrella_state_dependency="RenQuant/data and RenQuant/backtesting/renquant_104/artifacts staging paths",
    ),
    ScheduledJob(
        job_id="market_anomaly_retrain_trigger",
        kind="control",
        cadence="scheduled",
        command=["python", "-m", "renquant_orchestrator.anomaly_triggers"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
    ),
    ScheduledJob(
        job_id="daily_contract_fixture",
        kind="control",
        cadence="daily",
        command=["python", "-m", "renquant_orchestrator", "daily-contract"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
    ),
    ScheduledJob(
        job_id="daily_live_runner_bridge",
        kind="trading",
        cadence="daily",
        command=["python", "-m", "renquant_orchestrator", "daily-bridge"],
        owner_repo="renquant-orchestrator",
        migration_state="umbrella_bridge",
        production_safe=True,
        umbrella_code_dependency="RenQuant live.runner execution handoff",
        umbrella_state_dependency="RenQuant checkout for data, live_state, and runtime artifacts",
    ),
    ScheduledJob(
        job_id="live_runner_bridge",
        kind="inference",
        cadence="manual_or_scheduled",
        command=["python", "-m", "renquant_orchestrator", "live-bridge"],
        owner_repo="renquant-orchestrator",
        migration_state="umbrella_bridge",
        production_safe=True,
        umbrella_code_dependency="RenQuant live.runner execution handoff",
        umbrella_state_dependency="RenQuant checkout for data, live_state, and runtime artifacts",
    ),
    ScheduledJob(
        job_id="weekly_apy_monitor",
        kind="ops",
        cadence="weekly",
        command=["python", "-m", "renquant_orchestrator.weekly_apy_monitor"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency="RenQuant live_state and trade logs",
    ),
    ScheduledJob(
        job_id="state_backup",
        kind="ops",
        cadence="scheduled",
        command=["python", "-m", "renquant_orchestrator.state_backup"],
        owner_repo="renquant-orchestrator",
        migration_state="native_multirepo",
        production_safe=True,
        umbrella_state_dependency="RenQuant data and live_state backup source",
    ),
)


def scheduled_jobs() -> tuple[ScheduledJob, ...]:
    return _JOBS


def inventory_payload() -> dict[str, object]:
    jobs = [job.to_jsonable() for job in scheduled_jobs()]
    umbrella_bridge_jobs = [
        job.job_id for job in scheduled_jobs() if job.migration_state == "umbrella_bridge"
    ]
    return {
        "schema_version": 1,
        "owner_repo": "renquant-orchestrator",
        "jobs": jobs,
        "summary": {
            "total": len(jobs),
            "native_multirepo": sum(job.migration_state == "native_multirepo" for job in scheduled_jobs()),
            "umbrella_bridge": len(umbrella_bridge_jobs),
            "umbrella_bridge_jobs": umbrella_bridge_jobs,
        },
    }


def inventory_json(*, indent: int | None = 2) -> str:
    return json.dumps(inventory_payload(), indent=indent, sort_keys=True)
