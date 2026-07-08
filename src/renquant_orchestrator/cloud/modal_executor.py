"""Modal cloud backend for the BacktestExecutor protocol."""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from .executor import (
    BacktestRequest,
    BacktestResult,
    BatchSummary,
    DataManifest,
    PreflightReport,
)

log = logging.getLogger(__name__)

MODAL_CPU_RATE = 0.0000131  # $/physical-core-sec
MODAL_MEM_RATE = 0.00000222  # $/GiB-sec
WORKER_CORES = 1  # physical cores (= 2 vCPU)
WORKER_MEM_GIB = 4


def _estimate_cost_usd(elapsed_seconds: float) -> float:
    return elapsed_seconds * (
        WORKER_CORES * MODAL_CPU_RATE + WORKER_MEM_GIB * MODAL_MEM_RATE
    )


class ModalExecutor:
    """Modal cloud backend — dispatches sweep variants to remote workers."""

    def __init__(
        self,
        bundle_dir: str,
        volume_name: str = "renquant-sweep-data",
        timeout: int = 3600,
        retries: int = 1,
    ):
        self._bundle_dir = bundle_dir
        self._volume_name = volume_name
        self._timeout = timeout
        self._retries = retries

    def execute_batch(
        self,
        requests: list[BacktestRequest],
        *,
        on_result: Callable[[BacktestResult], None],
        on_error: Callable[[str, Exception], None],
        max_concurrent: int = 100,
    ) -> BatchSummary:
        from .modal_app import app, run_variant_remote

        t0 = time.monotonic()
        summary = BatchSummary()

        request_jsons = [json.dumps(_request_to_dict(r)) for r in requests]

        log.info("Starting Modal app (first run builds image ~3-5min, cached after)...")
        with app.run():
            log.info("Modal app running, dispatching %d variants...", len(request_jsons))
            for result_json in run_variant_remote.map(
                request_jsons,
                kwargs={},
            ):
                try:
                    result_dict = json.loads(result_json)

                    equity_curves = None
                    if result_dict.get("equity_curves"):
                        equity_curves = {
                            int(k): base64.b64decode(v)
                            for k, v in result_dict["equity_curves"].items()
                        }

                    trade_logs = None
                    if result_dict.get("trade_logs"):
                        trade_logs = {
                            int(k): base64.b64decode(v)
                            for k, v in result_dict["trade_logs"].items()
                        }

                    result = BacktestResult(
                        variant_name=result_dict["variant_name"],
                        role=result_dict.get("role", "candidate"),
                        config_fingerprint=result_dict.get("config_fingerprint", ""),
                        worker_id=result_dict.get("worker_id", "modal"),
                        volume_commit_id=result_dict.get("volume_commit_id"),
                        code_image_id=result_dict.get("code_image_id"),
                        started_at=result_dict.get("started_at", ""),
                        finished_at=result_dict.get("finished_at", ""),
                        elapsed_seconds=result_dict.get("elapsed_seconds", 0.0),
                        peak_memory_mb=result_dict.get("peak_memory_mb", 0.0),
                        seeds=result_dict.get("seeds", []),
                        per_seed=result_dict.get("per_seed", []),
                        equity_curves=equity_curves,
                        trade_logs=trade_logs,
                        result_checksum=result_dict.get("result_checksum", ""),
                    )
                    on_result(result)
                    summary.n_completed += 1
                    summary.cost_usd += _estimate_cost_usd(result.elapsed_seconds)
                except Exception as exc:
                    vname = "unknown"
                    try:
                        vname = json.loads(result_json).get("variant_name", "unknown")
                    except Exception:
                        pass
                    on_error(vname, exc)
                    summary.n_failed += 1

        summary.total_seconds = time.monotonic() - t0
        return summary

    def preflight(self, data_manifest: DataManifest) -> PreflightReport:
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}

        checks["volume_has_data"] = bool(data_manifest.files)
        if not checks["volume_has_data"]:
            details["volume_has_data"] = "No files in data manifest"

        checks["bundle_exists"] = Path(self._bundle_dir).is_dir()
        if not checks["bundle_exists"]:
            details["bundle_exists"] = f"Bundle dir not found: {self._bundle_dir}"

        try:
            import modal
            checks["modal_sdk"] = True
        except ImportError:
            checks["modal_sdk"] = False
            details["modal_sdk"] = "modal package not installed"

        projected = _estimate_cost_usd(30.0) * 75
        checks["cost_reasonable"] = projected < 20.0
        if not checks["cost_reasonable"]:
            details["cost_reasonable"] = f"Projected: ${projected:.2f} (75 variants × 30s)"

        return PreflightReport(
            passed=all(checks.values()),
            checks=checks,
            details=details,
        )

    def sync_data(self, local_paths: dict[str, str]) -> DataManifest:
        from .sync_data import sync_to_modal_volume

        path_map = {k: Path(v) for k, v in local_paths.items()}
        return sync_to_modal_volume(path_map, volume_name=self._volume_name)


def _request_to_dict(req: BacktestRequest) -> dict[str, Any]:
    return {
        "variant_name": req.variant_name,
        "role": req.role,
        "config_json": req.config_json,
        "volume_commit_id": req.volume_commit_id,
        "seeds": req.seeds,
        "start": req.start,
        "end": req.end,
        "initial_cash": req.initial_cash,
        "incumbent_turnover": req.incumbent_turnover,
    }


