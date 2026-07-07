#!/usr/bin/env python3
"""Concentration cap parameter sweep (design doc #403).

2D sweep: entry_cap (max_concentration) × topup_threshold.
Trim is OFF in production (04-24 A/B: trim OFF wins by +12.7pp APY),
so drift_cap dimension is effectively ∞ — deferred to Phase 2 if needed.

Uses the same sim infrastructure as run_kelly_sigma_horizon_ab.py.

Usage:
    # Dry-run: print the plan
    python scripts/run_concentration_cap_sweep.py

    # Execute all variants (serial, ~2-4h)
    python scripts/run_concentration_cap_sweep.py --execute --seeds 3

    # Execute with a specific base config
    python scripts/run_concentration_cap_sweep.py --execute \
        --base-config strategy_config.sim_kelly_ab_admoff.json \
        --manifest-path artifacts/sim/walkforward_manifest_v2_20260602.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
ORCH_REPO = Path(__file__).resolve().parent.parent
UMBRELLA_REPO = ORCH_REPO.parent / "RenQuant"
STRATEGY_DIR = UMBRELLA_REPO / "backtesting" / "renquant_104"

DEFAULT_BASE_CONFIG = "strategy_config.sim_kelly_ab_admoff.json"
DEFAULT_MANIFEST = "artifacts/sim/walkforward_manifest_v2_20260602.json"
DEFAULT_START = "2024-01-02"
DEFAULT_END = "2026-03-28"
DEFAULT_SEEDS = (0, 1, 2)
DEFAULT_INITIAL_CASH = 100_000.0

ENTRY_CAPS = [0.08, 0.10, 0.12, 0.15, 0.20]
TOPUP_THRESHOLDS = [0.02, 0.03, 0.05]

SUBREPO_IMPORT_ORDER = (
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
    "renquant-strategy-104",
    "renquant-backtesting",
    "renquant-orchestrator",
)


@dataclass(frozen=True)
class VariantSpec:
    name: str
    entry_cap: float
    topup_threshold: float
    config_path: Path
    seeds: tuple[int, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entry_cap": self.entry_cap,
            "topup_threshold": self.topup_threshold,
            "config_path": str(self.config_path),
            "seeds": list(self.seeds),
        }


def bootstrap_subrepo_imports() -> Path:
    for scripts_dir in (UMBRELLA_REPO / "scripts", STRATEGY_DIR):
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
    from subrepo_paths import resolve_subrepo_root  # noqa: PLC0415

    subrepo_root = resolve_subrepo_root(UMBRELLA_REPO).resolve()
    for repo in reversed(SUBREPO_IMPORT_ORDER):
        src = subrepo_root / repo / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    return subrepo_root


def build_variant_config(
    base: dict[str, Any],
    *,
    entry_cap: float,
    topup_threshold: float,
    output_path: Path,
) -> Path:
    cfg = deepcopy(base)
    kelly = cfg.setdefault("ranking", {}).setdefault("kelly_sizing", {})
    kelly["max_concentration"] = entry_cap
    kelly["top_up_threshold"] = topup_threshold
    kelly["trim_enabled"] = False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return output_path


def build_variants(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> list[VariantSpec]:
    base = json.loads(base_config_path.read_text())
    variants = []

    for entry_cap in ENTRY_CAPS:
        for topup_thresh in TOPUP_THRESHOLDS:
            name = f"cap{int(entry_cap*100):02d}_topup{int(topup_thresh*100):02d}"
            config_path = output_dir / f"strategy_config.{name}.json"
            build_variant_config(
                base,
                entry_cap=entry_cap,
                topup_threshold=topup_thresh,
                output_path=config_path,
            )
            variants.append(VariantSpec(
                name=name,
                entry_cap=entry_cap,
                topup_threshold=topup_thresh,
                config_path=config_path,
                seeds=seeds,
            ))

    return variants


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _mean(values: list) -> float:
    nums = [v for v in values if v is not None and math.isfinite(float(v))]
    return sum(nums) / len(nums) if nums else float("nan")


def _std(values: list) -> float:
    nums = [v for v in values if v is not None and math.isfinite(float(v))]
    if len(nums) < 2:
        return float("nan")
    m = sum(nums) / len(nums)
    return math.sqrt(sum((x - m) ** 2 for x in nums) / (len(nums) - 1))


def execute_variant(
    variant: VariantSpec,
    *,
    start: str,
    end: str,
    initial_cash: float,
    manifest_path: str = "",
) -> dict[str, Any]:
    if str(STRATEGY_DIR) not in sys.path:
        sys.path.insert(0, str(STRATEGY_DIR))
    bootstrap_subrepo_imports()

    config = json.loads(variant.config_path.read_text())
    config["_strategy_dir"] = str(STRATEGY_DIR)
    config["_strategy_config_name"] = str(variant.config_path)
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

    from kernel.data import fetch_ohlcv  # noqa: PLC0415
    from sim.runner import run_backtest_multi_seed  # noqa: PLC0415

    benchmark = config.get("benchmark", "SPY")
    spy_df = fetch_ohlcv(benchmark)
    etf_map = config.get("sector_etf_map", {})
    symbols = sorted(set(config.get("watchlist", [])) | set(etf_map.values()))
    ohlcv = {benchmark: spy_df}
    for symbol in symbols:
        try:
            ohlcv[symbol] = fetch_ohlcv(symbol)
        except Exception:
            continue

    result = run_backtest_multi_seed(
        seeds=list(variant.seeds),
        parallel=False,
        config=config,
        strategy_dir=STRATEGY_DIR,
        ohlcv=ohlcv,
        spy_df=spy_df,
        sector_etf_map=etf_map,
        initial_cash=float(initial_cash),
        backtest_start=start,
        backtest_end=end,
        snapshot=False,
    )

    metrics = result.get("metrics", {})
    per_regime = {}
    for regime, regime_data in result.get("per_regime", {}).items():
        rm = regime_data.get("metrics", {})
        per_regime[regime] = {
            "apy": rm.get("apy"),
            "sharpe": rm.get("sharpe"),
            "max_dd": rm.get("max_dd"),
            "cash_pct_mean": rm.get("cash_pct_mean"),
            "n_holdings_mean": rm.get("n_holdings_mean"),
            "topup_count": rm.get("topup_count", 0),
        }

    return {
        "variant": variant.name,
        "entry_cap": variant.entry_cap,
        "topup_threshold": variant.topup_threshold,
        "apy": metrics.get("apy"),
        "sharpe": metrics.get("sharpe"),
        "max_dd": metrics.get("max_dd"),
        "calmar": metrics.get("calmar"),
        "total_return": metrics.get("total_return"),
        "per_regime": per_regime,
        "seeds": list(variant.seeds),
    }


def print_results_table(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 100)
    print("CONCENTRATION CAP SWEEP RESULTS")
    print("=" * 100)
    print(f"{'Variant':<20} {'Cap':>5} {'TopUp':>6} {'APY':>8} {'Sharpe':>8} "
          f"{'MaxDD':>8} {'Calmar':>8}")
    print("-" * 100)

    sorted_results = sorted(results, key=lambda r: r.get("sharpe") or -999, reverse=True)
    for r in sorted_results:
        apy = r.get("apy")
        sharpe = r.get("sharpe")
        maxdd = r.get("max_dd")
        calmar = r.get("calmar")
        print(
            f"{r['variant']:<20} "
            f"{r['entry_cap']:>5.0%} "
            f"{r['topup_threshold']:>6.0%} "
            f"{apy:>7.1%} " if apy is not None else f"{'N/A':>8} ",
            end="",
        )
        if sharpe is not None:
            print(f"{sharpe:>8.3f} ", end="")
        else:
            print(f"{'N/A':>8} ", end="")
        if maxdd is not None:
            print(f"{maxdd:>7.1%} ", end="")
        else:
            print(f"{'N/A':>8} ", end="")
        if calmar is not None:
            print(f"{calmar:>8.2f}")
        else:
            print(f"{'N/A':>8}")

    # BULL_CALM breakdown
    print("\n" + "-" * 100)
    print("BULL_CALM REGIME BREAKDOWN")
    print(f"{'Variant':<20} {'APY':>8} {'Sharpe':>8} {'Cash%':>8} {'Holdings':>10} {'TopUps':>8}")
    print("-" * 100)
    for r in sorted_results:
        bc = (r.get("per_regime") or {}).get("BULL_CALM", {})
        apy = bc.get("apy")
        sharpe = bc.get("sharpe")
        cash = bc.get("cash_pct_mean")
        hold = bc.get("n_holdings_mean")
        topup = bc.get("topup_count", 0)
        print(
            f"{r['variant']:<20} ",
            end="",
        )
        print(f"{apy:>7.1%} " if apy is not None else f"{'N/A':>8} ", end="")
        print(f"{sharpe:>8.3f} " if sharpe is not None else f"{'N/A':>8} ", end="")
        print(f"{cash:>7.1%} " if cash is not None else f"{'N/A':>8} ", end="")
        print(f"{hold:>10.1f} " if hold is not None else f"{'N/A':>10} ", end="")
        print(f"{topup:>8}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--seeds", default="3")
    parser.add_argument("--initial-cash", type=float, default=DEFAULT_INITIAL_CASH)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    seeds = tuple(range(int(args.seeds))) if args.seeds.isdigit() else tuple(
        int(s.strip()) for s in args.seeds.split(",")
    )

    base_config_path = Path(args.base_config)
    if not base_config_path.is_absolute():
        base_config_path = STRATEGY_DIR / base_config_path
    if not base_config_path.exists():
        print(f"ERROR: base config not found: {base_config_path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else STRATEGY_DIR / "artifacts" / "diagnostics" / f"concentration_cap_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = build_variants(
        base_config_path=base_config_path,
        output_dir=output_dir,
        seeds=seeds,
    )

    plan = {
        "study": "concentration-cap-asymmetry-sweep",
        "design_doc": "orchestrator PR #403",
        "mode": "execute" if args.execute else "dry_run",
        "base_config": str(base_config_path),
        "manifest": args.manifest_path,
        "start": args.start,
        "end": args.end,
        "seeds": list(seeds),
        "n_variants": len(variants),
        "variants": [v.as_json() for v in variants],
        "grid": {
            "entry_caps": ENTRY_CAPS,
            "topup_thresholds": TOPUP_THRESHOLDS,
            "trim_enabled": False,
        },
    }

    plan_path = output_dir / "sweep_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    if not args.execute:
        print(f"DRY RUN: {len(variants)} variants planned")
        print(f"Plan saved to {plan_path}")
        print(f"\nGrid: {len(ENTRY_CAPS)} entry_caps × {len(TOPUP_THRESHOLDS)} topup_thresholds")
        print(f"Seeds: {seeds}")
        print(f"Base config: {base_config_path}")
        print(f"\nTo execute: add --execute")
        for v in variants:
            print(f"  {v.name}: cap={v.entry_cap:.0%} topup={v.topup_threshold:.0%}")
        return 0

    print(f"EXECUTING {len(variants)} variants × {len(seeds)} seeds")
    print(f"Output: {output_dir}")

    results = []
    for i, variant in enumerate(variants):
        print(f"\n[{i+1}/{len(variants)}] Running {variant.name} "
              f"(cap={variant.entry_cap:.0%}, topup={variant.topup_threshold:.0%})...")
        t0 = time.time()
        try:
            result = execute_variant(
                variant,
                start=args.start,
                end=args.end,
                initial_cash=args.initial_cash,
                manifest_path=args.manifest_path,
            )
            elapsed = time.time() - t0
            result["elapsed_seconds"] = elapsed
            results.append(result)
            apy = result.get("apy")
            sharpe = result.get("sharpe")
            print(f"  Done in {elapsed:.0f}s — APY={apy:.1%} Sharpe={sharpe:.3f}"
                  if apy is not None and sharpe is not None
                  else f"  Done in {elapsed:.0f}s")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.0f}s: {exc}")
            results.append({
                "variant": variant.name,
                "entry_cap": variant.entry_cap,
                "topup_threshold": variant.topup_threshold,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            })

    results_path = output_dir / "sweep_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(f"\nResults saved to {results_path}")

    print_results_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
