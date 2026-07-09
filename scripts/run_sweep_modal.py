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
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from renquant_orchestrator.cloud.executor import BacktestRequest

from renquant_orchestrator.runtime_paths import default_repo_root


def run_sweep(
    *,
    executor: Any,
    store: Any,
    grid_variants: list,
    aa_variant: Any,
    placebo: dict[str, Any],
    variant_by_name: dict[str, Any],
    data_manifest: Any,
    strat_dir: Path,
    manifest_path: str,
    start: str,
    end: str,
    initial_cash: float,
) -> dict[str, Any]:
    """Run incumbent + candidates + A/A resplit through `executor`, persist
    every result to `store`, then compute and store unanimity verdicts.

    Split out from main() so the real ResultStore API can be exercised
    end-to-end against a fake/local executor in tests, rather than only
    unit-testing each piece (ResultStore, executor, verdict math) in
    isolation — which is exactly what let the original CLI/store API
    mismatch go undetected.
    """
    sys.path.insert(0, str(strat_dir.parent.parent / "scripts"))
    from run_concentration_cap_sweep import AA_MAX_ABS_SHARPE_LIFT, _mean, unanimity_verdict

    def variant_to_request(v, incumbent_turnover=None):
        config = json.loads(v.config_path.read_text())
        config["_strategy_dir"] = str(strat_dir)
        config["initial_cash"] = float(initial_cash)
        config["backtest_start"] = start
        config["backtest_end"] = end
        config["persistence"] = {"enabled": False}
        config.setdefault("data_freshness", {})["enabled"] = False
        if manifest_path:
            wf = config.setdefault("walkforward", {})
            wf["enabled"] = True
            wf["manifest_path"] = manifest_path
            wf.setdefault("fail_on_no_model", True)

        return BacktestRequest(
            variant_name=v.name,
            role=v.role,
            config_json=json.dumps(config),
            volume_commit_id=data_manifest.commit_id,
            seeds=list(v.seeds),
            start=start,
            end=end,
            initial_cash=initial_cash,
            incumbent_turnover=incumbent_turnover,
        )

    completed = store.completed_variants()
    print(f"  {len(completed)} variants already completed (resume)")

    all_results: dict[str, Any] = {}

    def persist(r):
        v = variant_by_name.get(r.variant_name)
        store.insert_variant(
            r.variant_name,
            r.role,
            r.config_fingerprint,
            r.per_seed,
            entry_cap=getattr(v, "entry_cap", None),
            drift_buffer=getattr(v, "drift_buffer", None),
            topup_threshold=getattr(v, "topup_threshold", None),
            worker_id=r.worker_id,
            elapsed_seconds=r.elapsed_seconds,
            peak_memory_mb=r.peak_memory_mb,
        )
        all_results[r.variant_name] = r

    # ── Step 6: run incumbent first (needed for turnover baseline) ──
    incumbent = next(v for v in grid_variants if v.role == "incumbent")
    inc_turnover = None

    if incumbent.name not in completed:
        print(f"\nStep 6: Running incumbent ({incumbent.name})...")
        print("  (first run builds Docker image on Modal — may take 3-5 min, cached after)")
        executor.execute_batch(
            [variant_to_request(incumbent)],
            on_result=persist,
            on_error=lambda n, e: print(f"  INCUMBENT FAILED: {e}"),
        )
        inc_result = all_results.get(incumbent.name)
        if inc_result is not None:
            inc_turnover = _mean_turnover(inc_result.per_seed)
            print(f"  Incumbent turnover: {inc_turnover:.4f}")
    else:
        print("\nStep 6: Incumbent already completed (resume)")

    # ── Step 7: dispatch remaining candidates + A/A resplit ──
    candidates = [
        v for v in grid_variants if v.role != "incumbent" and v.name not in completed
    ]
    if aa_variant.name not in completed:
        candidates.append(aa_variant)

    print(f"\nStep 7: Dispatching {len(candidates)} variants...")
    requests = [
        variant_to_request(v, incumbent_turnover=inc_turnover) for v in candidates
    ]

    n_done = 0
    errors: dict[str, str] = {}

    def on_result(r):
        nonlocal n_done
        n_done += 1
        persist(r)
        print(
            f"  [{n_done}/{len(requests)}] {r.variant_name} "
            f"({r.elapsed_seconds:.0f}s, worker={r.worker_id[:12]})"
        )

    def on_error(name, exc):
        nonlocal n_done
        n_done += 1
        errors[name] = str(exc)
        store.insert_error(name, str(exc))
        print(f"  [{n_done}/{len(requests)}] {name} FAILED: {exc}")

    t0 = time.monotonic()
    summary = executor.execute_batch(requests, on_result=on_result, on_error=on_error)
    wall = time.monotonic() - t0

    print(f"\nDone: {summary.n_completed} completed, {summary.n_failed} failed")
    print(f"  Wall time: {wall:.0f}s, estimated cost: ${summary.cost_usd:.2f}")

    # ── Step 8: compute verdicts ──
    print("\nStep 8: Computing verdicts...")
    inc_result = all_results.get(incumbent.name)
    aa_result = all_results.get(aa_variant.name)

    aa_sharpe_lift = float("nan")
    aa_passed: bool | None = None
    if inc_result is not None and aa_result is not None:
        inc_sharpe_mean = _mean([row.get("sharpe") for row in inc_result.per_seed])
        aa_sharpe_mean = _mean([row.get("sharpe") for row in aa_result.per_seed])
        if math.isfinite(inc_sharpe_mean) and math.isfinite(aa_sharpe_mean):
            aa_sharpe_lift = aa_sharpe_mean - inc_sharpe_mean
            aa_passed = abs(aa_sharpe_lift) <= AA_MAX_ABS_SHARPE_LIFT
        print(
            f"A/A resplit Sharpe lift: {aa_sharpe_lift:+.4f} "
            f"({'PASS' if aa_passed else 'FAIL'} — tolerance ±{AA_MAX_ABS_SHARPE_LIFT})"
        )

    verdicts: list[dict[str, Any]] = []
    if inc_result is not None:
        inc_dict = {"variant": inc_result.variant_name, "per_seed": inc_result.per_seed}
        for name, r in all_results.items():
            if name in (incumbent.name, aa_variant.name):
                continue
            cand_dict = {"variant": r.variant_name, "per_seed": r.per_seed}
            verdict = unanimity_verdict(
                cand_dict,
                inc_dict,
                placebo_passed=(placebo["passed"] if placebo["provided"] else None),
            )
            store.update_verdict(name, verdict)
            verdicts.append(verdict)
            print(f"  {name}: tier3_ready={verdict['tier3_ready']}")

    store.finalize(
        total_seconds=wall,
        cost_usd=summary.cost_usd,
        aa_sharpe_lift=(aa_sharpe_lift if math.isfinite(aa_sharpe_lift) else None),
        aa_passed=aa_passed,
    )

    tier3_winners = [v["variant"] for v in verdicts if v["tier3_ready"]]
    print(f"\nTier-3-ready candidates: {tier3_winners or 'none'}")

    return {
        "n_completed": summary.n_completed,
        "n_failed": summary.n_failed,
        "errors": errors,
        "verdicts": verdicts,
        "aa_sharpe_lift": aa_sharpe_lift,
        "aa_passed": aa_passed,
        "tier3_winners": tier3_winners,
    }


def stage_panel_history(
    repo_root: Path, base_config: dict[str, Any],
) -> tuple[Path, Path]:
    """Stage the fundamentals inputs SimAdapter/job_panel_scoring need for Volume sync.

    THREE independent consumers read fundamentals files, and all three were
    silently unsynced or misrouted (rounds 1-3 of real bounded Modal smoke
    tests each found one):

    1. SimAdapter._load_panel_history_cache() resolves "panel_history_path"
       (default "data/alpha158_291_fundamental_dataset.parquet", not
       overridden in any config this sweep uses) relative to
       strategy_dir.parent.parent, i.e. the same repo_root already used
       for ohlcv_dir. Fixed by staging under the "data" label
       (-> /data/data/<file> once the Volume is mounted at /data).

    2. renquant_pipeline.kernel.panel_pipeline.job_panel_scoring's
       XGBoost-scorer fund-feature lookup (needed whenever
       scorer.feature_cols includes earnings_yield/book_to_price/
       gross_profitability/roe/asset_growth — true for this sweep's
       panel_ltr_xgboost scorer) reads its OWN "data" / "sec_fundamentals_
       daily.parquet" relative to renquant_pipeline...panel_pipeline.
       _data_root.data_root() — which resolves RENQUANT_DATA_ROOT if set
       (modal_app.py pins it to "/data"), landing at the SAME
       /data/data/... path as (1). Covered by the same "data"-label stage.

    3. A THIRD, genuinely separate implementation: RenQuant/backtesting/
       renquant_104/kernel/panel_pipeline/job_panel_scoring.py — a stale
       bundled COPY (predates the _data_root.py refactor entirely) that
       adapters/sim.py actually imports via `from kernel.panel_pipeline
       import PanelScorer` (a different top-level import path than
       renquant_pipeline.kernel.panel_pipeline — confirmed by direct
       inspection, NOT the same module object). It hardcodes
       `Path(__file__).resolve().parents[4]`, which for this file bundled
       at /data/app/kernel/panel_pipeline/job_panel_scoring.py resolves to
       "/" (the container filesystem root) — so it looks for
       /data/sec_fundamentals_daily.parquet, ONE level shallower than (2)'s
       path, completely independent of RENQUANT_DATA_ROOT. THIS is the
       consumer that's actually exercised by this sweep's real backtest
       execution (confirmed: round 3's real smoke test showed neither of
       (1)/(2)'s file-not-found errors, yet panel_fundamentals_missing
       still fired — because this third path was never covered at all).

    IMPORTANT (round 7 — confirmed by direct architecture investigation,
    not assumption): RenQuant/backtesting/renquant_104/kernel/ is NOT a
    forgotten/stale accidental duplicate of renquant_pipeline. It has its
    own long, active, independent git history (decomposition refactors as
    recently as 2026-06-12, one day before other sibling files in the same
    tree were touched 2026-06-14) — this is the genuine, deliberately
    separate backtesting/sim kernel, not a mistake to "fix" by redirecting
    the import to canonical. Eliminating or aliasing it would risk breaking
    every local (non-Modal) backtest that currently depends on it. The
    correct, safe fix given this constraint is exactly what rounds 4-7 do:
    stage the specific data files/dirs this kernel's own hardcoded
    `parents[4]`-relative paths expect, not touch the import itself.

    Round 7 also found this same stale kernel's job_panel_scoring.py has
    TWO MORE `data/`-relative dependencies exercised by this sweep's actual
    XGBoost artifact (confirmed via the walk-forward manifest's
    feature_cols: pead_signal/pead_quintile_rank/days_since_earnings/
    sue_signal/surprise_momentum/surprise_streak + sentiment_*):
    data/earnings_surprise/ and data/news_sentiment_alpaca/ (per-ticker
    parquet directories, ~3MB/~4MB total — small, same selective-staging
    rationale). These do NOT hard fail-closed the way the fund-feature
    check does (job_panel_scoring.py's own "Feature-health check" only
    logs a warning for all-zero PEAD/SUE columns, it does not block the
    day) — so their absence would not have caused another timeout, but it
    would have silently degraded these features to zero, giving a
    misleadingly weaker smoke-test result than what round 4-6's fixes
    alone would produce. Staged proactively here rather than waiting for
    a fourth expensive real Modal test to reveal it as a "the model looks
    worse than expected" symptom instead of an outright failure.

    Selectively stage just these files/dirs (792 MB + 17.5 MB + ~3MB +
    ~4MB — the 17.5MB file duplicated at two paths since it's small)
    rather than the full data/ dir (24 GB) — same rationale as the OHLCV
    subsetting elsewhere in main().

    Returns (data_staging, root_staging): data_staging is for
    local_paths["data"] (consumers 1+2, plus earnings_surprise/
    news_sentiment_alpaca for the canonical resolver's own equivalent
    lookups); root_staging is for local_paths[""] (consumer 3 — empty
    label means no path prefix, so files land directly at the Volume
    root). Any individual source file/dir that's missing is skipped with
    a warning (caller decides whether that is fatal) rather than raising.
    """
    panel_history_path = base_config.get("ranking", {}).get("panel_scoring", {}).get(
        "panel_history_path",
        base_config.get("panel_history_path", "data/alpha158_291_fundamental_dataset.parquet"),
    )
    data_staging = Path(tempfile.mkdtemp(prefix="data_sync_"))
    root_staging = Path(tempfile.mkdtemp(prefix="data_sync_root_"))
    for rel_path in (panel_history_path, "data/sec_fundamentals_daily.parquet"):
        src = repo_root / rel_path
        if src.exists():
            dst = data_staging / Path(rel_path).name
            shutil.copy2(src, dst)
            print(f"  Staged {rel_path}: {dst.name} "
                  f"({src.stat().st_size / 1e6:.0f} MB)")
        else:
            print(f"  WARNING: {rel_path} not found at {src} "
                  f"— panel scoring will fail-closed on the remote worker")

    for dir_name in ("earnings_surprise", "news_sentiment_alpaca"):
        src_dir = repo_root / "data" / dir_name
        if src_dir.is_dir():
            # Flat under data_staging (matching the two files above), NOT
            # nested under an extra "data" subdir — the "data" LABEL itself
            # already contributes that path segment once uploaded
            # (label "data" + rel "earnings_surprise/X" -> /data/data/
            # earnings_surprise/X on the Volume, matching repo/"data"/
            # "earnings_surprise" where repo == RENQUANT_DATA_ROOT == /data).
            dst_dir = data_staging / dir_name
            shutil.copytree(src_dir, dst_dir)
            n_files = sum(1 for _ in dst_dir.iterdir())
            total_mb = sum(f.stat().st_size for f in dst_dir.iterdir()) / 1e6
            print(f"  Staged data/{dir_name}/: {n_files} files ({total_mb:.1f} MB)")
        else:
            print(f"  WARNING: data/{dir_name} not found at {src_dir} "
                  f"— PEAD/SUE/sentiment features will silently zero-impute "
                  f"(warning-only, not fail-closed, but degrades result quality)")

    sec_fund_src = repo_root / "data" / "sec_fundamentals_daily.parquet"
    if sec_fund_src.exists():
        dst = root_staging / sec_fund_src.name
        shutil.copy2(sec_fund_src, dst)
        print(f"  Staged data/sec_fundamentals_daily.parquet at Volume root "
              f"(legacy kernel/panel_pipeline consumer): {dst.name} "
              f"({sec_fund_src.stat().st_size / 1e6:.0f} MB)")

    for dir_name in ("earnings_surprise", "news_sentiment_alpaca"):
        src_dir = repo_root / "data" / dir_name
        if src_dir.is_dir():
            dst_dir = root_staging / dir_name
            shutil.copytree(src_dir, dst_dir)
            print(f"  Staged data/{dir_name}/ at Volume root "
                  f"(legacy kernel/panel_pipeline consumer): "
                  f"{sum(1 for _ in dst_dir.iterdir())} files")
    return data_staging, root_staging


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
    parser.add_argument("--max-variants", type=int, default=None,
                        help="Limit total variants (incumbent + N-1 candidates) for smoke testing")
    args = parser.parse_args(argv)

    repo_root = default_repo_root()
    strat_dir = repo_root / "backtesting" / "renquant_104"

    base_config_path = Path(args.base_config)
    if not base_config_path.is_absolute():
        base_config_path = strat_dir / base_config_path
    if not base_config_path.exists():
        print(f"ERROR: base config not found: {base_config_path}")
        return 1

    manifest_abs_path = strat_dir / args.manifest_path
    if not manifest_abs_path.exists():
        print(f"ERROR: walkforward manifest not found: {manifest_abs_path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir
        else strat_dir / "artifacts" / "diagnostics" / f"modal_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(strat_dir.parent.parent / "scripts"))
    from run_concentration_cap_sweep import (
        ENTRY_CAPS,
        DRIFT_BUFFERS,
        TOPUP_THRESHOLDS,
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
    bundle_manifest = bundle_subrepos(subrepo_root, strat_dir, bundle_dir)
    bundle_fp = compute_bundle_fingerprint(bundle_manifest)
    print(f"  Bundled {len(bundle_manifest)} files, fingerprint={bundle_fp[:12]}")

    # ── Step 2: Stage data for sync ──
    print("Step 2: Staging data...")
    from renquant_orchestrator.cloud.modal_executor import ModalExecutor

    executor = ModalExecutor(
        bundle_dir=str(bundle_dir),
        volume_name=args.volume_name,
        timeout=args.timeout,
    )

    ohlcv_dir = repo_root / "data" / "ohlcv"

    # Only sync OHLCV for symbols the sweep actually uses (16 MB vs 250 MB)
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

    # SimAdapter._load_panel_history_cache() resolves "panel_history_path"
    # relative to strategy_dir.parent.parent (== repo_root here). Missing this
    # caused every simulated day to fail-closed on panel scoring
    # (panel_fundamentals_missing) until the remote task hit its timeout.
    data_staging, root_staging = stage_panel_history(repo_root, base_config)

    # Copy artifacts into bundle at kernel/artifacts/... so they appear at the
    # path SimAdapter expects (strategy_dir/artifacts/...) without symlinks.
    wf_manifest = json.loads(manifest_abs_path.read_text())
    staged_count = 0
    for retrain in wf_manifest.get("retrains", []):
        for key in ("artifact_uri", "calibrator_uri"):
            uri = retrain.get(key)
            if not uri:
                continue
            src = strat_dir / uri
            if src.exists():
                dst = bundle_dir / "kernel" / uri
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                staged_count += 1
    manifest_dst = bundle_dir / "kernel" / args.manifest_path
    manifest_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_abs_path, manifest_dst)
    staged_count += 1
    print(f"  Staged {staged_count} artifact files into bundle")

    local_paths: dict[str, str] = {
        "ohlcv": str(ohlcv_staging),
        "app": str(bundle_dir),
        "data": str(data_staging),
        # Empty label -> no path prefix -> lands at Volume root. Needed for
        # the stale bundled kernel/panel_pipeline/job_panel_scoring.py copy
        # (see stage_panel_history's docstring, consumer 3) which resolves
        # its own root via a hardcoded parents[4] rather than
        # RENQUANT_DATA_ROOT, landing one directory level shallower than
        # the "data" label above.
        "": str(root_staging),
    }

    # ── Step 3: Verify staged data contract ──
    print("Step 3: Verifying staged data contract...")
    from renquant_orchestrator.cloud.data_contract import verify_staged

    contract = verify_staged(
        bundle_dir=bundle_dir,
        ohlcv_staging=ohlcv_staging,
        data_staging=data_staging,
        base_config=base_config,
        manifest_path=args.manifest_path,
    )
    print(contract.summary())
    if not contract.passed:
        n_fail = len(contract.failed)
        print(f"\nData contract FAILED — {n_fail} required file(s) missing. "
              "Fix before syncing to Modal Volume.")
        return 1
    print(f"  Data contract PASSED: {len(contract.checks)} checks, "
          f"0 failures")

    # ── Step 4: Sync to Modal Volume ──
    print("Step 4: Syncing data to Modal Volume...")
    data_manifest = executor.sync_data(local_paths)
    print(f"  Volume commit={data_manifest.commit_id}, "
          f"{len(data_manifest.files)} files, "
          f"{data_manifest.total_bytes / 1e6:.1f} MB")

    # ── Step 5: Preflight check ──
    print("Step 5: Preflight check...")
    n_grid_variants = len(ENTRY_CAPS) * len(DRIFT_BUFFERS) * len(TOPUP_THRESHOLDS)
    n_variants_planned = (
        args.max_variants if args.max_variants is not None else n_grid_variants
    ) + 1
    report = executor.preflight(
        data_manifest,
        n_variants=n_variants_planned,
        n_seeds_per_variant=len(FROZEN_SEEDS),
    )
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

    # ── Step 6: Build variant grid ──
    print("Step 6: Building variant grid...")
    grid_variants = build_grid_variants(
        base_config_path=base_config_path, output_dir=output_dir, seeds=FROZEN_SEEDS,
    )
    if args.max_variants is not None:
        incumbent = next(v for v in grid_variants if v.role == "incumbent")
        candidates = [v for v in grid_variants if v.role == "candidate"]
        n_cand = max(0, args.max_variants - 1)
        grid_variants = [incumbent] + candidates[:n_cand]
        print(f"  Smoke mode: limited to {len(grid_variants)} variants "
              f"(incumbent + {n_cand} candidates)")
    aa_variant = build_aa_variant(
        base_config_path=base_config_path, output_dir=output_dir, seeds=FROZEN_SEEDS,
    )
    placebo = load_placebo_evidence(args.placebo_json)
    variant_by_name = {v.name: v for v in grid_variants}
    variant_by_name[aa_variant.name] = aa_variant

    # ── Step 7: initialize ResultStore ──
    from renquant_orchestrator.cloud.result_store import ResultStore

    sweep_id = args.resume or f"concentration-cap-sweep-modal-{stamp}"
    store = ResultStore(sweep_id, base_dir=output_dir)

    subrepo_pins = _collect_subrepo_pins(subrepo_root)
    subrepo_pins_sha = hashlib.sha256(
        json.dumps(subrepo_pins, sort_keys=True).encode()
    ).hexdigest()
    # Model/WF-artifact provenance leg (distinct from bundle_fp, which is the
    # *source-code* bundle fingerprint — see doc/design/2026-07-07-cloud-
    # backtest-compute.md §7's pinned-multirepo-assembly contract).
    artifact_manifest_fingerprint = hashlib.sha256(
        manifest_abs_path.read_bytes()
    ).hexdigest()

    store.init_sweep(
        backend="modal",
        backtest_start=args.start,
        backtest_end=args.end,
        initial_cash=args.initial_cash,
        grid_spec=[v.as_json() for v in grid_variants] + [aa_variant.as_json()],
        n_variants=len(grid_variants) + 1,
        volume_commit=data_manifest.commit_id,
        subrepo_pins_json=json.dumps(subrepo_pins),
        subrepo_pins_sha256=subrepo_pins_sha,
        strategy_config_fingerprint=hashlib.sha256(
            base_config_path.read_bytes()
        ).hexdigest(),
        data_manifest_fingerprint=hashlib.sha256(
            json.dumps(data_manifest.files, sort_keys=True).encode()
        ).hexdigest(),
        artifact_manifest_fingerprint=artifact_manifest_fingerprint,
    )
    print(f"  sweep_id={sweep_id}, db={store._db_path}")

    run_sweep(
        executor=executor,
        store=store,
        grid_variants=grid_variants,
        aa_variant=aa_variant,
        placebo=placebo,
        variant_by_name=variant_by_name,
        data_manifest=data_manifest,
        strat_dir=strat_dir,
        manifest_path=args.manifest_path,
        start=args.start,
        end=args.end,
        initial_cash=args.initial_cash,
    )

    print(f"\nResults persisted to {store._db_path}")
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
