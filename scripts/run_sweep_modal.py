#!/usr/bin/env python3
"""Run the concentration cap sweep on Modal cloud compute.

Orchestrator-specific wrapper around the existing sweep grid logic
(scripts/run_concentration_cap_sweep.py), adding:
  1. Bundle subrepo source code → container image
  2. Sync OHLCV + artifacts to Modal Volume
  3. Dispatch variants via Modal .map() with streaming callbacks
  4. Persist results to SQLite (crash-safe, resumable)

Usage::

    # Preflight check (no execution)
    python scripts/run_sweep_modal.py --preflight

    # Execute full 75-variant sweep on Modal
    python scripts/run_sweep_modal.py --execute

    # Resume a crashed/interrupted sweep
    python scripts/run_sweep_modal.py --execute --resume <sweep_id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renquant_orchestrator.runtime_paths import default_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resume", default=None, help="sweep_id to resume")
    parser.add_argument("--base-config", default="strategy_config.sim_kelly_ab_admoff.json")
    parser.add_argument("--manifest-path", default="artifacts/sim/walkforward_manifest_v2_20260602.json")
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2026-03-28")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--placebo-json", action="append", default=[])
    parser.add_argument("--volume-name", default="renquant-sweep-data")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)

    repo_root = default_repo_root()
    strat_dir = repo_root / "backtesting" / "renquant_104"

    base_config_path = Path(args.base_config)
    if not base_config_path.is_absolute():
        base_config_path = strat_dir / base_config_path
    if not base_config_path.exists():
        print(f"ERROR: base config not found: {base_config_path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir
        else strat_dir / "artifacts" / "diagnostics" / f"modal_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(strat_dir.parent.parent / "scripts"))
    from run_concentration_cap_sweep import (
        FROZEN_SEEDS,
        ENTRY_CAPS,
        DRIFT_BUFFERS,
        TOPUP_THRESHOLDS,
        build_grid_variants,
        build_aa_variant,
        load_placebo_evidence,
        bootstrap_subrepo_imports,
        unanimity_verdict,
    )

    subrepo_root = bootstrap_subrepo_imports(repo_root)

    # ── Step 1: Bundle subrepo source ──
    print("Step 1: Bundling subrepo source code...")
    from renquant_orchestrator.cloud.bundle import bundle_subrepos, compute_bundle_fingerprint

    bundle_dir = output_dir / "bundle"
    bundle_manifest = bundle_subrepos(subrepo_root, strat_dir, bundle_dir)
    bundle_fp = compute_bundle_fingerprint(bundle_manifest)
    print(f"  Bundled {len(bundle_manifest)} files, fingerprint={bundle_fp[:12]}")

    # ── Step 2: Sync data to Modal Volume ──
    print("Step 2: Syncing data to Modal Volume...")
    from renquant_orchestrator.cloud.modal_executor import ModalExecutor

    executor = ModalExecutor(
        bundle_dir=str(bundle_dir),
        volume_name=args.volume_name,
        timeout=args.timeout,
    )

    ohlcv_dir = repo_root / "data" / "ohlcv"
    artifacts_dir = strat_dir / "artifacts"
    model_dir = strat_dir / "models"

    base_config = json.loads(base_config_path.read_text())
    watchlist = set(base_config.get("watchlist", []))
    watchlist |= set(base_config.get("sector_etf_map", {}).values())
    watchlist.add(base_config.get("benchmark", "SPY"))

    ohlcv_staging = Path(tempfile.mkdtemp(prefix="ohlcv_sync_"))
    for sym in sorted(watchlist):
        src_pq = ohlcv_dir / sym / "1d.parquet"
        if src_pq.exists():
            dst = ohlcv_staging / sym
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_pq, dst / "1d.parquet")
    print(f"  Staged {len(list(ohlcv_staging.iterdir()))} symbols for sync")

    local_paths: dict[str, str] = {"ohlcv": str(ohlcv_staging)}
    if artifacts_dir.is_dir():
        local_paths["artifacts"] = str(artifacts_dir)
    if model_dir.is_dir():
        local_paths["models"] = str(model_dir)

    data_manifest = executor.sync_data(local_paths)
    data_manifest_fp = hashlib.sha256(
        json.dumps(data_manifest.files, sort_keys=True).encode()
    ).hexdigest()
    print(f"  Volume synced: {len(data_manifest.files)} files, "
          f"{data_manifest.total_bytes / 1e6:.1f} MB, "
          f"data_fp={data_manifest_fp[:12]}")

    # ── Step 3: Preflight check ──
    print("Step 3: Preflight check...")
    report = executor.preflight(data_manifest)
    for check, passed in report.checks.items():
        status = "PASS" if passed else "FAIL"
        detail = report.details.get(check, "")
        print(f"  [{status}] {check}" + (f" — {detail}" if detail else ""))

    if not report.passed:
        print("\nPreflight FAILED — fix the above issues and re-run.")
        return 1

    if args.preflight:
        print("\nPreflight passed. Add --execute to run the sweep.")
        return 0

    if not args.execute:
        print("\nDry run complete. Add --execute to run, or --preflight to check only.")
        return 0

    # ── Step 4: Build variant grid ──
    print("Step 4: Building variant grid...")
    grid_variants = build_grid_variants(
        base_config_path=base_config_path, output_dir=output_dir, seeds=FROZEN_SEEDS,
    )
    aa_variant = build_aa_variant(
        base_config_path=base_config_path, output_dir=output_dir, seeds=FROZEN_SEEDS,
    )
    placebo = load_placebo_evidence(args.placebo_json)

    from renquant_orchestrator.cloud.executor import BacktestRequest
    from renquant_orchestrator.cloud.result_store import ResultStore

    # ── Step 5: Initialize ResultStore (matches API: sweep_id, base_dir) ──
    subrepo_pins = _collect_subrepo_pins(subrepo_root)
    subrepo_pins_sha = hashlib.sha256(
        json.dumps(subrepo_pins, sort_keys=True).encode()
    ).hexdigest()
    strategy_config_fp = hashlib.sha256(
        base_config_path.read_bytes()
    ).hexdigest()
    artifact_fp = hashlib.sha256(
        json.dumps(
            {k: v for k, v in data_manifest.files.items()
             if k.startswith("artifacts/") or k.startswith("models/")},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    sweep_id = args.resume or f"modal_{stamp}"
    store = ResultStore(sweep_id, output_dir)
    grid_spec = {
        "entry_caps": list(ENTRY_CAPS),
        "drift_buffers": [
            "inf" if math.isinf(x) else x for x in DRIFT_BUFFERS
        ],
        "topup_thresholds": list(TOPUP_THRESHOLDS),
    }

    if not args.resume:
        store.init_sweep(
            backend="modal",
            backtest_start=args.start,
            backtest_end=args.end,
            initial_cash=args.initial_cash,
            grid_spec=grid_spec,
            n_variants=len(grid_variants) + 1,
            volume_commit=data_manifest.commit_id,
            subrepo_pins_json=json.dumps(subrepo_pins),
            subrepo_pins_sha256=subrepo_pins_sha,
            strategy_config_fingerprint=strategy_config_fp,
            data_manifest_fingerprint=data_manifest_fp,
            artifact_manifest_fingerprint=artifact_fp,
        )
    print(f"  sweep_id={sweep_id}, db={store._db_path}")

    completed = store.completed_variants()
    print(f"  {len(completed)} variants already completed (resume)")

    def variant_to_request(v, incumbent_turnover=None):
        config = json.loads(v.config_path.read_text())
        config["_strategy_dir"] = str(strat_dir)
        config["initial_cash"] = float(args.initial_cash)
        config["backtest_start"] = args.start
        config["backtest_end"] = args.end
        config["persistence"] = {"enabled": False}
        config.setdefault("data_freshness", {})["enabled"] = False
        if args.manifest_path:
            wf = config.setdefault("walkforward", {})
            wf["enabled"] = True
            wf["manifest_path"] = args.manifest_path
            wf.setdefault("fail_on_no_model", True)

        return BacktestRequest(
            variant_name=v.name,
            role=v.role,
            config_json=json.dumps(config),
            volume_commit_id=data_manifest.commit_id,
            seeds=list(v.seeds),
            start=args.start,
            end=args.end,
            initial_cash=args.initial_cash,
            incumbent_turnover=incumbent_turnover,
        )

    def _store_result(result) -> None:
        """Adapt BacktestResult to ResultStore.insert_variant() API."""
        store.insert_variant(
            variant_name=result.variant_name,
            role=result.role,
            config_fingerprint=result.config_fingerprint,
            per_seed=result.per_seed,
            worker_id=result.worker_id,
            elapsed_seconds=result.elapsed_seconds,
            peak_memory_mb=result.peak_memory_mb,
        )

    # ── Step 6: Run incumbent first (needed for turnover baseline) ──
    incumbent = next(v for v in grid_variants if v.role == "incumbent")
    inc_turnover = None

    if incumbent.name not in completed:
        print(f"\nStep 6: Running incumbent ({incumbent.name})...")
        inc_request = variant_to_request(incumbent)
        inc_results = []

        def on_inc_result(r):
            inc_results.append(r)
            _store_result(r)

        executor.execute_batch(
            [inc_request], on_result=on_inc_result,
            on_error=lambda n, e: print(f"  INCUMBENT FAILED: {e}"),
        )

        if inc_results:
            inc_turnover = _mean_turnover(inc_results[0].per_seed)
            print(f"  Incumbent turnover: {inc_turnover:.4f}")
    else:
        print(f"\nStep 6: Incumbent already completed (resume)")

    # ── Step 7: Dispatch candidates via Modal .map() ──
    all_to_run = [v for v in grid_variants if v.role != "incumbent" and v.name not in completed]
    if aa_variant.name not in completed:
        all_to_run.append(aa_variant)

    print(f"\nStep 7: Dispatching {len(all_to_run)} variants to Modal...")
    requests = [variant_to_request(v, incumbent_turnover=inc_turnover) for v in all_to_run]

    n_done = 0

    def on_result(r):
        nonlocal n_done
        n_done += 1
        _store_result(r)
        print(f"  [{n_done}/{len(requests)}] {r.variant_name} "
              f"({r.elapsed_seconds:.0f}s, worker={r.worker_id[:12]})")

    def on_error(name, exc):
        nonlocal n_done
        n_done += 1
        store.insert_error(name, str(exc))
        print(f"  [{n_done}/{len(requests)}] {name} FAILED: {exc}")

    t0 = time.monotonic()
    summary = executor.execute_batch(
        requests, on_result=on_result, on_error=on_error,
    )
    wall = time.monotonic() - t0

    print(f"\nDone: {summary.n_completed} completed, {summary.n_failed} failed")
    print(f"  Wall time: {wall:.0f}s, estimated cost: ${summary.cost_usd:.2f}")

    store.finalize(total_seconds=wall, cost_usd=summary.cost_usd)

    print(f"\nResults persisted to {store._db_path}")
    print(f"sweep_id={sweep_id}")
    return 0


def _collect_subrepo_pins(subrepo_root: Path) -> dict[str, str]:
    import subprocess

    pins = {}
    for d in sorted(subrepo_root.iterdir()):
        if not d.is_dir():
            continue
        git_dir = d / ".git"
        if not git_dir.exists():
            continue
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(d), stderr=subprocess.DEVNULL,
            ).decode().strip()
            pins[d.name] = sha
        except Exception:
            pins[d.name] = "unknown"
    return pins


def _mean_turnover(per_seed: list[dict]) -> float | None:
    values = []
    for s in per_seed:
        t = (s.get("turnover") or {}).get("turnover_annualized")
        if t is not None and math.isfinite(t):
            values.append(t)
    return sum(values) / len(values) if values else None


if __name__ == "__main__":
    sys.exit(main())
