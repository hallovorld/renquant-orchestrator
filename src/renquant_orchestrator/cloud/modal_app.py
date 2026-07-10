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
DEFAULT_TIMEOUT_SECONDS = 10800
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

WORKER_CORES = 4
WORKER_MEM_GIB = 16


@app.function(
    image=_BASE_IMAGE,
    volumes={"/data": data_volume},
    cpu=WORKER_CORES * 2,
    memory=WORKER_MEM_GIB * 1024,
    timeout=WORKER_TIMEOUT_SECONDS,
    retries=WORKER_RETRIES,
    max_containers=30,
)
def run_variant_remote(request_json: str) -> str:
    """Execute ONE (variant, seed) backtest on a Modal worker.

    Runs INSIDE the container with /data/ Volume mounted. All imports
    happen at runtime from /data/app/ (the code bundle). One task per
    seed (not per variant) — the executor fans out per-seed for max
    parallelism and aggregates results back to a per-variant view.
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
    # renquant_pipeline.kernel.panel_pipeline._data_root.data_root() resolves
    # the umbrella-checkout root via RENQUANT_DATA_ROOT first, else a chain of
    # local-machine fallbacks (sibling checkout / ~/git/github/RenQuant / the
    # pipeline package root itself) — none of which exist inside this
    # container, so it silently fails to find its own sentinel
    # (data/sec_fundamentals_daily.parquet) and the XGBoost-fund-feature path
    # in job_panel_scoring.py fail-closes as "panel_fundamentals_missing".
    # Pin it explicitly to where stage_panel_history() in run_sweep_modal.py
    # actually stages both fundamentals files (repo_root == strategy_dir's
    # grandparent == this Volume's mount point).
    os.environ.setdefault("RENQUANT_DATA_ROOT", "/data")

    # The kernel copy of job_panel_scoring.py uses
    #   Path(__file__).resolve().parents[4] / "data" / "sec_fundamentals..."
    # On Modal, /data is a Volume mount that .resolve() follows to the
    # underlying /__modal/volumes/<id> path, breaking parents[4] ancestry.
    # The subrepo copy uses _data_root_cached() (correct), but the strategy
    # kernel copy does not.  Place the fundamentals at BOTH the unresolved
    # AND the resolved ancestry so both code paths find them.
    _fund_names = ("sec_fundamentals_daily.parquet",
                   "alpha158_291_fundamental_dataset.parquet")
    _fund_src = {}
    for _name in _fund_names:
        for _src_dir in ("/data/data", "/data"):
            _src = f"{_src_dir}/{_name}"
            if os.path.exists(_src):
                _fund_src[_name] = _src
                break

    # Compute the RESOLVED parents[4] path that the kernel will actually use
    _kernel_scoring = Path(f"{app_root}/kernel/panel_pipeline/job_panel_scoring.py")
    _resolved_parents4 = (
        _kernel_scoring.resolve().parents[4] if _kernel_scoring.exists()
        else None
    )

    # Place files at every ancestor path the kernel might resolve to
    _target_dirs = [
        f"{app_root}/data",
        f"{app_root}/subrepos/renquant-pipeline/data",
    ]
    if _resolved_parents4:
        _target_dirs.append(str(_resolved_parents4 / "data"))

    for _td in _target_dirs:
        os.makedirs(_td, exist_ok=True)
        for _name, _src in _fund_src.items():
            _dst = f"{_td}/{_name}"
            if not os.path.exists(_dst):
                try:
                    os.symlink(_src, _dst)
                except OSError:
                    import shutil
                    shutil.copy2(_src, _dst)

    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    # app_root itself (not its subdirectories) must be on sys.path for
    # `from adapters.sim import ...` / `from sim.runner import ...` /
    # `from scripts.run_concentration_cap_sweep import ...` to resolve
    # `adapters`/`sim`/`scripts` as top-level packages under app_root.
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

    # Verify the remote data contract before importing backtest code.
    # This is the container-side half of the deterministic preflight: if any
    # required file is missing, fail immediately with a clear enumerated
    # report instead of discovering it mid-backtest via a fail-close.
    from renquant_orchestrator.cloud.data_contract import verify_remote
    _contract = verify_remote(app_root=app_root)
    if not _contract.passed:
        raise RuntimeError(
            f"Remote data contract FAILED — {len(_contract.failed)} "
            f"required file(s) missing:\n{_contract.summary()}"
        )

    config = json.loads(request["config_json"])
    config["_strategy_dir"] = f"{app_root}/kernel"
    config["_strategy_config_name"] = f"remote_{request['variant_name']}"
    config["initial_cash"] = float(request["initial_cash"])
    config["backtest_start"] = request["start"]
    config["backtest_end"] = request["end"]
    config["persistence"] = {"enabled": False}
    config.setdefault("data_freshness", {})["enabled"] = False

    # A walk-forward manifest path baked into the config is a LOCAL path
    # from wherever the sweep was launched — resolve it against the
    # Volume-mounted artifacts copy instead, by filename.
    manifest_rel = config.get("walkforward", {}).get("manifest_path", "")
    if manifest_rel:
        vol_manifest = Path("/data/artifacts") / Path(manifest_rel).name
        if vol_manifest.exists():
            config["walkforward"]["manifest_path"] = str(vol_manifest)

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

    from sim.runner import run_backtest

    # Each pod runs exactly ONE seed — fan-out across pods for parallelism.
    seeds = request["seeds"]
    seed = seeds[0] if isinstance(seeds, list) else seeds
    strategy_dir = Path(f"{app_root}/kernel")

    seed_result = run_backtest(
        config=config,
        strategy_dir=strategy_dir, ohlcv=ohlcv, spy_df=spy_df,
        sector_etf_map=etf_map, initial_cash=float(request["initial_cash"]),
        backtest_start=request["start"], backtest_end=request["end"],
        snapshot=False, seed=seed,
    )

    from scripts.run_concentration_cap_sweep import (
        per_regime_metrics,
        compute_turnover_fills_cost,
        compute_winner_continuation,
        REQUIRED_REGIMES,
        _finite,
    )

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

    equity_curves = {}
    trade_logs = {}
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
        peak_mem /= 1024 * 1024  # bytes -> MB on macOS
    else:
        peak_mem /= 1024  # KB -> MB on Linux

    pod_worker_id = os.environ.get("MODAL_TASK_ID", "unknown")
    pod_started_at = datetime.fromtimestamp(t0, tz=timezone.utc).isoformat()
    pod_finished_at = datetime.now(timezone.utc).isoformat()
    pod_elapsed_seconds = time.time() - t0

    # Each (variant, seed) pair runs on its own pod under the per-seed
    # fan-out design, so worker identity/timing/memory are genuinely
    # POD-level facts, not variant-level ones. Stamp them onto seed_data
    # so the executor can preserve per-pod provenance instead of collapsing
    # N pods' worth of facts into a single arbitrary value.
    seed_data["worker_id"] = pod_worker_id
    seed_data["started_at"] = pod_started_at
    seed_data["finished_at"] = pod_finished_at
    seed_data["elapsed_seconds"] = pod_elapsed_seconds
    seed_data["peak_memory_mb"] = peak_mem

    result_obj = {
        "variant_name": request["variant_name"],
        "role": request.get("role", "candidate"),
        "config_fingerprint": hashlib.sha256(
            request["config_json"].encode()
        ).hexdigest(),
        "worker_id": pod_worker_id,
        "volume_commit_id": request.get("volume_commit_id"),
        "code_image_id": os.environ.get("MODAL_IMAGE_ID", "unknown"),
        "started_at": pod_started_at,
        "finished_at": pod_finished_at,
        "elapsed_seconds": pod_elapsed_seconds,
        "peak_memory_mb": peak_mem,
        "seeds": [seed],
        "per_seed": [seed_data],
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
