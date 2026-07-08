"""Modal app definition for remote sweep execution.

The @app.function-decorated worker lives here at module scope so Modal can
reference it by name instead of pickling it — which avoids the
DeserializationError when the local-only ``renquant_orchestrator`` package
is not installed in the container image.
"""
from __future__ import annotations

import os

import modal

VOLUME_NAME = "renquant-sweep-data"
APP_NAME = "renquant-sweep"

# @app.function's timeout/retries are decorator-time-only — Modal has no
# per-call override for a module-scope function (verified against the
# installed modal SDK: no with_options()/options() on modal.Function, and
# app.function()'s signature takes timeout/retries as plain kwargs, not
# something reconfigurable via .map()/.remote()). ModalExecutor sets these
# env vars before importing this module (its only import site) so the
# caller's requested values are still what gets baked into the decorator.
DEFAULT_TIMEOUT_SECONDS = 3600
DEFAULT_RETRIES = 1
WORKER_TIMEOUT_SECONDS = int(
    os.environ.get("RENQUANT_MODAL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
)
WORKER_RETRIES = int(os.environ.get("RENQUANT_MODAL_RETRIES", DEFAULT_RETRIES))

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

_BASE_IMAGE = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "pandas>=2.0",
        "numpy>=1.24",
        "scipy>=1.10",
        "scikit-learn>=1.2",
        "xgboost>=1.7",
        "pyarrow>=12.0",
        "joblib>=1.2",
        "pyyaml>=6.0",
        "cvxpy>=1.3",
        "pydantic>=2.0",
        "ngboost>=0.4",
        "lightgbm>=3.3",
    )
    .run_commands(
        "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    )
)

WORKER_CORES = 1
WORKER_MEM_GIB = 4


@app.function(
    image=_BASE_IMAGE,
    volumes={"/data": data_volume},
    cpu=WORKER_CORES * 2,
    memory=WORKER_MEM_GIB * 1024,
    timeout=WORKER_TIMEOUT_SECONDS,
    retries=WORKER_RETRIES,
)
def run_variant_remote(request_json: str) -> str:
    """Execute one variant backtest on a Modal worker.

    Runs INSIDE the container with /data/ Volume mounted.
    All imports happen at runtime from /data/app/ (the code bundle).
    """
    import json
    import hashlib
    import os
    import sys
    import time
    import resource
    import base64
    import gzip
    import io
    from datetime import datetime, timezone
    from pathlib import Path

    request = json.loads(request_json)
    t0 = time.time()

    app_root = "/data/app"
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    for sub in [
        "subrepos/renquant-common/src",
        "subrepos/renquant-base-data/src",
        "subrepos/renquant-artifacts/src",
        "subrepos/renquant-model/src",
        "subrepos/renquant-pipeline/src",
        "subrepos/renquant-execution/src",
        "subrepos/renquant-strategy-104/src",
        "subrepos/renquant-backtesting/src",
        "subrepos/renquant-orchestrator/src",
    ]:
        p = f"{app_root}/{sub}"
        if p not in sys.path:
            sys.path.insert(0, p)

    config = json.loads(request["config_json"])
    config["_strategy_dir"] = f"{app_root}/kernel"
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
        for symbol_dir in sorted(ohlcv_dir.iterdir()):
            if not symbol_dir.is_dir():
                continue
            pq = symbol_dir / "1d.parquet"
            if pq.exists():
                ohlcv[symbol_dir.name] = pd.read_parquet(pq)

    benchmark = config.get("benchmark", "SPY")
    spy_df = ohlcv.get(benchmark)
    etf_map = config.get("sector_etf_map", {})


    from sim.runner import run_backtest_multi_seed

    seeds = request["seeds"]
    strategy_dir = Path(f"{app_root}/kernel")

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

    from scripts.run_concentration_cap_sweep import (
        per_regime_metrics,
        compute_turnover_fills_cost,
        compute_winner_continuation,
        REQUIRED_REGIMES,
        _finite,
    )

    for seed, seed_result in zip(result.seeds, result.per_seed_results):
        eq_df = getattr(seed_result, "equity_df", None)
        n_days = int(len(eq_df)) if eq_df is not None else 0
        trade_log = getattr(seed_result, "trade_log", None) or []

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
        peak_mem /= 1024 * 1024
    else:
        peak_mem /= 1024

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


def build_image(bundle_dir: str) -> modal.Image:
    """Return the cached base image — code is loaded from Volume at runtime."""
    return _BASE_IMAGE
