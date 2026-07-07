"""Modal cloud backend for the BacktestExecutor protocol."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
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
        import modal

        from .modal_app import VOLUME_NAME, app, build_image, data_volume

        image = build_image(self._bundle_dir)
        volume = modal.Volume.from_name(self._volume_name, create_if_missing=True)

        @app.function(
            image=image,
            volumes={"/data": volume},
            cpu=WORKER_CORES * 2,  # vCPUs
            memory=WORKER_MEM_GIB * 1024,
            timeout=self._timeout,
            retries=self._retries,
        )
        def run_variant_remote(request_json: str) -> str:
            return _remote_worker(request_json)

        t0 = time.monotonic()
        summary = BatchSummary()

        request_jsons = [json.dumps(_request_to_dict(r)) for r in requests]

        with app.run():
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

        projected = len(data_manifest.files) * 0.04
        checks["cost_reasonable"] = projected < 20.0

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


def _remote_worker(request_json: str) -> str:
    """Execute one variant backtest on a Modal worker.

    This function runs INSIDE the Modal container. It has access to:
    - /app/ — bundled subrepo code (in PYTHONPATH)
    - /data/ — Modal Volume with OHLCV + artifacts
    """
    import json
    import hashlib
    import os
    import time
    import resource
    import base64
    import gzip
    import io
    from datetime import datetime, timezone
    from pathlib import Path

    request = json.loads(request_json)
    t0 = time.time()

    import sys
    sys.path.insert(0, "/app/kernel")
    sys.path.insert(0, "/app/sim")
    sys.path.insert(0, "/app/scripts")

    config = json.loads(request["config_json"])
    config["_strategy_dir"] = "/app/kernel"
    config["_strategy_config_name"] = f"remote_{request['variant_name']}"
    config["initial_cash"] = float(request["initial_cash"])
    config["backtest_start"] = request["start"]
    config["backtest_end"] = request["end"]
    config["persistence"] = {"enabled": False}
    config.setdefault("data_freshness", {})["enabled"] = False

    ohlcv_dir = Path("/data/ohlcv")
    ohlcv = {}
    if ohlcv_dir.is_dir():
        import pandas as pd
        # Layout: ohlcv/{SYMBOL}/1d.parquet (directory-per-symbol)
        for symbol_dir in sorted(ohlcv_dir.iterdir()):
            if not symbol_dir.is_dir():
                continue
            pq = symbol_dir / "1d.parquet"
            if pq.exists():
                ohlcv[symbol_dir.name] = pd.read_parquet(pq)

    benchmark = config.get("benchmark", "SPY")
    spy_df = ohlcv.get(benchmark)
    etf_map = config.get("sector_etf_map", {})

    manifest_rel = config.get("walkforward", {}).get("manifest_path", "")
    if manifest_rel:
        vol_manifest = Path("/data/artifacts") / Path(manifest_rel).name
        if vol_manifest.exists():
            config["walkforward"]["manifest_path"] = str(vol_manifest)

    from sim.runner import run_backtest_multi_seed

    seeds = request["seeds"]
    strategy_dir = Path("/app/kernel")

    result = run_backtest_multi_seed(
        seeds=seeds, parallel=False, config=config,
        strategy_dir=strategy_dir, ohlcv=ohlcv, spy_df=spy_df,
        sector_etf_map=etf_map, initial_cash=float(request["initial_cash"]),
        backtest_start=request["start"], backtest_end=request["end"],
        snapshot=False,
    )

    per_seed = []
    equity_curves = {}
    trade_logs = {}

    for seed, seed_result in zip(result.seeds, result.per_seed_results):
        eq_df = getattr(seed_result, "equity_df", None)
        n_days = int(len(eq_df)) if eq_df is not None else 0
        trade_log = getattr(seed_result, "trade_log", None) or []

        from scripts.run_concentration_cap_sweep import (
            per_regime_metrics,
            compute_turnover_fills_cost,
            compute_winner_continuation,
            REQUIRED_REGIMES,
            _finite,
        )

        turnover = compute_turnover_fills_cost(
            trade_log, n_days=n_days,
            incumbent_turnover_annualized=request.get("incumbent_turnover"),
        )
        daily_cost_drag = float(turnover.get("daily_modeled_cost_frac") or 0.0)
        regimes = per_regime_metrics(
            eq_df, REQUIRED_REGIMES, daily_cost_drag=daily_cost_drag,
        )
        winner_cont = compute_winner_continuation(
            trade_log,
            entry_cap=config.get("ranking", {}).get("kelly_sizing", {}).get(
                "max_concentration", 0.12
            ),
        )

        seed_data = {
            "seed": seed,
            "apy": _finite(seed_result.apy),
            "sharpe": _finite(seed_result.sharpe),
            "max_dd": _finite(seed_result.max_dd),
            "calmar": _finite(seed_result.calmar),
            "per_regime": regimes,
            "turnover": turnover,
            "winner_continuation": winner_cont,
        }
        per_seed.append(seed_data)

        if eq_df is not None and not getattr(eq_df, "empty", True):
            buf = io.BytesIO()
            eq_df.to_csv(buf, index=True)
            equity_curves[seed] = base64.b64encode(
                gzip.compress(buf.getvalue())
            ).decode()

        if trade_log:
            tl_json = "\n".join(json.dumps(t, default=str) for t in trade_log)
            trade_logs[seed] = base64.b64encode(
                gzip.compress(tl_json.encode())
            ).decode()

    peak_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        peak_mem /= 1024 * 1024  # bytes → MB on macOS
    else:
        peak_mem /= 1024  # KB → MB on Linux

    result_obj = {
        "variant_name": request["variant_name"],
        "role": request.get("role", "candidate"),
        "config_fingerprint": hashlib.sha256(
            request["config_json"].encode()
        ).hexdigest(),
        "worker_id": os.environ.get("MODAL_TASK_ID", "unknown"),
        "volume_commit_id": request.get("volume_commit_id"),
        "code_image_id": os.environ.get("MODAL_IMAGE_ID", "unknown"),
        "started_at": datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.time() - t0,
        "peak_memory_mb": peak_mem,
        "seeds": seeds,
        "per_seed": per_seed,
        "equity_curves": equity_curves or None,
        "trade_logs": trade_logs or None,
    }

    canonical = json.dumps(
        {k: v for k, v in result_obj.items() if k != "result_checksum"},
        sort_keys=True, default=str,
    )
    result_obj["result_checksum"] = hashlib.sha256(canonical.encode()).hexdigest()

    return json.dumps(result_obj, default=str)
