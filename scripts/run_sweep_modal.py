#!/usr/bin/env python3
"""Run the concentration cap sweep on Modal cloud compute.

Wraps the existing sweep logic (scripts/run_concentration_cap_sweep.py) with
the cloud executor pipeline:
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
import json
import math
import os
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
        build_grid_variants,
        build_aa_variant,
        load_placebo_evidence,
        bootstrap_subrepo_imports,
    )

    subrepo_root = bootstrap_subrepo_imports(repo_root)

    # ── Step 1: Bundle subrepo source ──
    print("Step 1: Bundling subrepo source code...")
    from renquant_orchestrator.cloud.bundle import bundle_subrepos, compute_bundle_fingerprint

    bundle_dir = output_dir / "bundle"
    manifest = bundle_subrepos(subrepo_root, strat_dir, bundle_dir)
    bundle_fp = compute_bundle_fingerprint(manifest)
    print(f"  Bundled {len(manifest)} files, fingerprint={bundle_fp[:12]}")

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

    local_paths: dict[str, str] = {}
    if ohlcv_dir.is_dir():
        local_paths["ohlcv"] = str(ohlcv_dir)
    if artifacts_dir.is_dir():
        local_paths["artifacts"] = str(artifacts_dir)
    if model_dir.is_dir():
        local_paths["models"] = str(model_dir)

    data_manifest = executor.sync_data(local_paths)
    print(f"  Volume commit={data_manifest.commit_id}, "
          f"{len(data_manifest.files)} files, "
          f"{data_manifest.total_bytes / 1e6:.1f} MB")

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

    # ── Step 4: Build variant grid → BacktestRequests ──
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

    base_config = json.loads(base_config_path.read_text())

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

    # ── Step 5: Initialize ResultStore ──
    db_path = output_dir / "sweep_results.db"
    store = ResultStore(str(db_path))

    import hashlib
    subrepo_pins = _collect_subrepo_pins(subrepo_root)
    subrepo_pins_sha = hashlib.sha256(
        json.dumps(subrepo_pins, sort_keys=True).encode()
    ).hexdigest()

    sweep_id = args.resume or store.init_sweep(
        name="concentration-cap-sweep-modal",
        n_variants=len(grid_variants) + 1,
        subrepo_pins_json=json.dumps(subrepo_pins),
        subrepo_pins_sha256=subrepo_pins_sha,
        strategy_config_fingerprint=hashlib.sha256(
            base_config_path.read_bytes()
        ).hexdigest(),
        data_manifest_fingerprint=hashlib.sha256(
            json.dumps(data_manifest.files, sort_keys=True).encode()
        ).hexdigest(),
        artifact_manifest_fingerprint=bundle_fp,
    )
    print(f"  sweep_id={sweep_id}, db={db_path}")

    completed = store.completed_variants(sweep_id)
    print(f"  {len(completed)} variants already completed (resume)")

    # ── Step 6: Run incumbent first (needed for turnover baseline) ──
    incumbent = next(v for v in grid_variants if v.role == "incumbent")
    inc_turnover = None

    if incumbent.name not in completed:
        print(f"\nStep 6: Running incumbent ({incumbent.name})...")
        inc_request = variant_to_request(incumbent)
        inc_results = []

        def on_inc_result(r):
            inc_results.append(r)
            store.insert_variant(sweep_id, r)

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
    candidates = [v for v in grid_variants if v.role != "incumbent" and v.name not in completed]
    if aa_variant.name not in completed:
        candidates.append(aa_variant)

    print(f"\nStep 7: Dispatching {len(candidates)} variants to Modal...")
    requests = [variant_to_request(v, incumbent_turnover=inc_turnover) for v in candidates]

    n_done = 0

    def on_result(r):
        nonlocal n_done
        n_done += 1
        store.insert_variant(sweep_id, r)
        print(f"  [{n_done}/{len(requests)}] {r.variant_name} "
              f"({r.elapsed_seconds:.0f}s, worker={r.worker_id[:12]})")

    def on_error(name, exc):
        nonlocal n_done
        n_done += 1
        store.insert_error(sweep_id, name, str(exc))
        print(f"  [{n_done}/{len(requests)}] {name} FAILED: {exc}")

    t0 = time.monotonic()
    summary = executor.execute_batch(
        requests, on_result=on_result, on_error=on_error,
    )
    wall = time.monotonic() - t0

    print(f"\nDone: {summary.n_completed} completed, {summary.n_failed} failed")
    print(f"  Wall time: {wall:.0f}s, estimated cost: ${summary.cost_usd:.2f}")

    store.finalize(sweep_id)

    # ── Step 8: Compute verdicts ──
    print("\nStep 8: Computing verdicts...")
    from run_concentration_cap_sweep import unanimity_verdict
    # TODO: read back from store and compute verdicts

    print(f"\nResults persisted to {db_path}")
    print(f"sweep_id={sweep_id}")
    return 0


def _collect_subrepo_pins(subrepo_root: Path) -> dict[str, str]:
    pins = {}
    for d in sorted(subrepo_root.iterdir()):
        if not d.is_dir():
            continue
        git_dir = d / ".git"
        if not git_dir.exists():
            continue
        head_file = git_dir / "HEAD" if git_dir.is_dir() else None
        if head_file and head_file.exists():
            import subprocess
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
