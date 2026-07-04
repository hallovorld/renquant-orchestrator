"""Stable scheduled-job dispatcher for operator schedulers."""
from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Final


_MODULE_JOBS: Final[dict[str, str]] = {
    "weekly_alpha158_fund_retrain": "renquant_orchestrator.retrain_alpha158_fund",
    "weekly_patchtst_retrain": "renquant_orchestrator.retrain_patchtst",
    "daily_alpha158_linear_retrain": "renquant_orchestrator.retrain_alpha158_linear",
    "market_anomaly_retrain_trigger": "renquant_orchestrator.anomaly_triggers",
    "weekly_apy_monitor": "renquant_orchestrator.weekly_apy_monitor",
    "weekly_promote_monitor": "renquant_orchestrator.weekly_promote_monitor",
    "state_backup": "renquant_orchestrator.state_backup",
    "native_live_parity_fixture": "renquant_orchestrator.live_parity",
    "native_live_payload_parity_fixture": "renquant_orchestrator.live_parity_payloads",
    "native_live_execution_payload_fixture": "renquant_orchestrator.native_execution_payload",
    "native_live_bundle_fixture": "renquant_orchestrator.native_live_bundle",
    "native_live_account_snapshot_fixture": "renquant_orchestrator.native_live_account_snapshot",
    "native_live_context_fixture": "renquant_orchestrator.native_live_context",
    "native_live_inference_fixture": "renquant_orchestrator.native_live_inference",
    "native_live_market_snapshot_fixture": "renquant_orchestrator.native_live_market_snapshot",
    "native_live_run_candidate": "renquant_orchestrator.native_live_run",
    "build_wf_manifest": "renquant_orchestrator.build_wf_manifest",
    "build_patchtst_wf_manifest": "renquant_orchestrator.build_patchtst_wf_manifest",
    "daily_pit_revision_snapshot": "renquant_orchestrator.pit_revision_collector",
}


def _clean_args(argv: Sequence[str] | None) -> list[str]:
    args = list(argv or [])
    if args[:1] == ["--"]:
        return args[1:]
    return args


def _run_module_main(module_name: str, argv: list[str]) -> int:
    module = importlib.import_module(module_name)
    main = getattr(module, "main", None)
    if main is None:
        raise ValueError(f"scheduled job module has no main(argv): {module_name}")
    return int(main(argv) or 0)


def run_scheduled_job(job_id: str, argv: Sequence[str] | None = None) -> int:
    """Run one scheduled job by stable inventory id.

    Scheduler configs should depend on this job id, not on internal module names.
    Extra args are forwarded to the underlying job command unchanged.
    """
    forwarded = _clean_args(argv)
    if job_id == "daily_contract_fixture":
        from .cli import main

        return main(["daily-contract", *forwarded])
    if job_id == "daily_live_runner_bridge":
        from .cli import main

        return main(["daily-bridge", *forwarded])
    if job_id == "live_runner_bridge":
        from .cli import main

        return main(["live-bridge", *forwarded])
    module_name = _MODULE_JOBS.get(job_id)
    if module_name is None:
        raise ValueError(f"unknown scheduled job id: {job_id}")
    return _run_module_main(module_name, forwarded)
