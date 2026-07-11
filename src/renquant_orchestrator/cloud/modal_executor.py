"""Modal cloud backend for the BacktestExecutor protocol."""
from __future__ import annotations

import base64
import json
import logging
import os
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
WORKER_CORES = 4
WORKER_MEM_GIB = 16

# Conservative per-pod runtime estimate for the preflight cost gate, in
# seconds. The only real data point available is the pre-reconciliation
# smoke test's cached-run worker time (5558s / 93min) for ONE pod running
# ALL 3 seeds serially on the OLD architecture — see
# doc/progress/2026-07-08-modal-sweep-reconciled.md. Under the per-seed
# fan-out design each pod now runs exactly ONE seed, so the true per-pod
# time is very likely lower (perhaps close to 5558/3 if backtest compute
# dominates), but that has NOT been re-measured on the reconciled code, and
# fixed per-pod overhead (image pull, data load from the Volume) may not
# scale down linearly with fewer seeds. Using the full un-split figure is
# the conservative (non-optimistic) choice until a fresh bounded smoke test
# on THIS code produces a real per-seed-pod number to replace it.
DEFAULT_SECONDS_PER_POD_ESTIMATE = 5558.0


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
        timeout: int = int(os.environ.get("MODAL_TIMEOUT", "86400")),
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
        import sys

        module_name = "renquant_orchestrator.cloud.modal_app"
        if module_name in sys.modules:
            existing = sys.modules[module_name]
            if (
                existing.WORKER_TIMEOUT_SECONDS != self._timeout
                or existing.WORKER_RETRIES != self._retries
            ):
                raise RuntimeError(
                    "modal_app was already imported with timeout="
                    f"{existing.WORKER_TIMEOUT_SECONDS}, retries={existing.WORKER_RETRIES} "
                    f"(baked into the @app.function decorator at import time); this "
                    f"ModalExecutor requested timeout={self._timeout}, retries={self._retries}, "
                    "which cannot be honored without a fresh process. Modal's "
                    "@app.function timeout/retries are decorator-time-only, so a "
                    "second import in the same process would silently reuse the "
                    "first import's baked-in values. Run each distinct "
                    "timeout/retries combination in its own process."
                )
        else:
            os.environ["RENQUANT_MODAL_TIMEOUT_SECONDS"] = str(self._timeout)
            os.environ["RENQUANT_MODAL_RETRIES"] = str(self._retries)

        from .modal_app import app, run_variant_remote

        t0 = time.monotonic()
        summary = BatchSummary()

        # Fan out: one Modal task per (variant, seed) for max parallelism.
        per_seed_requests = []
        for r in requests:
            for seed in r.seeds:
                d = _request_to_dict(r)
                d["seeds"] = [seed]
                per_seed_requests.append(json.dumps(d))

        log.info("Starting Modal app (first run builds image ~3-5min, cached after)...")
        with app.run():
            n_tasks = len(per_seed_requests)
            n_variants = len(requests)
            log.info(
                "Dispatching %d tasks (%d variants × %d seeds)...",
                n_tasks, n_variants,
                n_tasks // n_variants if n_variants else 0,
            )

            variant_seeds: dict[str, list[dict]] = {}
            variant_meta: dict[str, dict] = {}

            n_received = 0
            for result_json in run_variant_remote.map(
                per_seed_requests,
                kwargs={},
                order_outputs=False,
                return_exceptions=True,
            ):
                n_received += 1
                if isinstance(result_json, Exception):
                    log.error(
                        "Pod %d/%d raised: %s", n_received, n_tasks, result_json
                    )
                    on_error("unknown", result_json)
                    summary.n_failed += 1
                    continue
                log.info("Pod %d/%d returned", n_received, n_tasks)
                try:
                    result_dict = json.loads(result_json)
                    vname = result_dict["variant_name"]

                    variant_seeds.setdefault(vname, []).extend(
                        result_dict.get("per_seed", [])
                    )
                    if vname not in variant_meta:
                        # Each (variant, seed) pod bills its own compute-seconds;
                        # seed the variant-level total from this pod's elapsed
                        # time rather than treating a single pod as the whole
                        # variant's cost.
                        prev = dict(result_dict)
                        prev["total_worker_seconds"] = result_dict.get(
                            "elapsed_seconds", 0.0
                        )
                        variant_meta[vname] = prev
                    else:
                        prev = variant_meta[vname]
                        # Cost is billed per pod-second across ALL dispatched
                        # pods for this variant (3 seeds = 3 separate pods
                        # under the per-seed fan-out design), so the variant's
                        # total compute-seconds is a SUM across pods, not the
                        # max of any single pod's wall-clock time. Using max()
                        # here would systematically undercount real spend by
                        # roughly (seeds_per_variant)x.
                        prev["total_worker_seconds"] = prev.get(
                            "total_worker_seconds", 0.0
                        ) + result_dict.get("elapsed_seconds", 0.0)
                        # peak_memory_mb IS legitimately a max: pods run on
                        # independent machines, so memory doesn't add across
                        # them — the worst single pod's footprint is what
                        # matters for right-sizing the resource envelope.
                        prev["peak_memory_mb"] = max(
                            prev.get("peak_memory_mb", 0),
                            result_dict.get("peak_memory_mb", 0),
                        )
                        for k in ("equity_curves", "trade_logs"):
                            if result_dict.get(k):
                                prev.setdefault(k, {}).update(result_dict[k])

                except Exception as exc:
                    vname = "unknown"
                    try:
                        vname = json.loads(result_json).get("variant_name", "unknown")
                    except Exception:
                        pass
                    on_error(vname, exc)
                    summary.n_failed += 1

            for vname, meta in variant_meta.items():
                try:
                    per_seed = variant_seeds.get(vname, [])
                    all_seeds = [s["seed"] for s in per_seed]

                    equity_curves = None
                    if meta.get("equity_curves"):
                        equity_curves = {
                            int(k): base64.b64decode(v)
                            for k, v in meta["equity_curves"].items()
                        }

                    trade_logs = None
                    if meta.get("trade_logs"):
                        trade_logs = {
                            int(k): base64.b64decode(v)
                            for k, v in meta["trade_logs"].items()
                        }

                    result = BacktestResult(
                        variant_name=vname,
                        role=meta.get("role", "candidate"),
                        config_fingerprint=meta.get("config_fingerprint", ""),
                        # worker_id/started_at/finished_at/result_checksum below
                        # are stamped from whichever pod's response happened to
                        # be aggregated first for this variant — they are NOT
                        # necessarily representative of every pod that ran a
                        # seed for this variant. Each per_seed[i] entry carries
                        # its own authoritative worker_id/started_at/
                        # finished_at/elapsed_seconds/peak_memory_mb — use those
                        # for genuine per-pod provenance.
                        worker_id=meta.get("worker_id", "modal"),
                        volume_commit_id=meta.get("volume_commit_id"),
                        code_image_id=meta.get("code_image_id"),
                        started_at=meta.get("started_at", ""),
                        finished_at=meta.get("finished_at", ""),
                        # elapsed_seconds at the variant level is the SUM of
                        # every dispatched pod's elapsed time for this variant
                        # (total billed compute-seconds), not any single pod's
                        # wall-clock duration — see the aggregation loop above.
                        elapsed_seconds=meta.get("total_worker_seconds", 0.0),
                        peak_memory_mb=meta.get("peak_memory_mb", 0.0),
                        seeds=all_seeds,
                        per_seed=per_seed,
                        equity_curves=equity_curves,
                        trade_logs=trade_logs,
                        result_checksum=meta.get("result_checksum", ""),
                    )
                    on_result(result)
                    summary.n_completed += 1
                    summary.cost_usd += _estimate_cost_usd(result.elapsed_seconds)
                except Exception as exc:
                    on_error(vname, exc)
                    summary.n_failed += 1

        summary.total_seconds = time.monotonic() - t0
        return summary

    def preflight(
        self,
        data_manifest: DataManifest,
        *,
        n_variants: int,
        n_seeds_per_variant: int,
        seconds_per_pod: float = DEFAULT_SECONDS_PER_POD_ESTIMATE,
    ) -> PreflightReport:
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

        # Under the per-seed fan-out design, one pod is dispatched per
        # (variant, seed) pair — the cost projection must scale with the
        # ACTUAL pod count, not a stale one-pod-per-variant assumption.
        n_pods = n_variants * n_seeds_per_variant
        projected = _estimate_cost_usd(seconds_per_pod) * n_pods
        checks["cost_reasonable"] = projected < 20.0
        if not checks["cost_reasonable"]:
            details["cost_reasonable"] = (
                f"Projected: ${projected:.2f} ({n_pods} pods = "
                f"{n_variants} variants × {n_seeds_per_variant} seeds, "
                f"{seconds_per_pod:.0f}s/pod estimate)"
            )

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


