#!/usr/bin/env python3
"""Rank-floor calibration sweep — the #1 cash-drag lever.

Implements the 1D sweep approved in design doc #408. Varies the VetoWeakBuys
floor mechanism while holding all other parameters at production values.

Grid (6 variants):
    adaptive_mean_std       (incumbent: mean+1σ ≈ 0.565)
    adaptive_quantile q=0.90 (top 10%)
    adaptive_quantile q=0.80 (top 20% — coded default)
    adaptive_quantile q=0.70 (top 30%)
    adaptive_quantile q=0.60 (top 40%)
    adaptive_mean_std_mult05 (mean+0.5σ — looser mean+kσ)

Seeds frozen at {42, 43, 44}. Unanimity verdict rule.

Usage::

    # Dry-run: print the plan
    python scripts/run_rank_floor_sweep.py

    # Execute
    python scripts/run_rank_floor_sweep.py --execute
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

from renquant_orchestrator.runtime_paths import default_repo_root


FROZEN_SEEDS: tuple[int, ...] = (42, 43, 44)
AA_SEED_OFFSET = 1000

DEFAULT_BASE_CONFIG = "strategy_config.sim_kelly_ab_admoff.json"
DEFAULT_MANIFEST = "artifacts/sim/walkforward_manifest_v2_20260602.json"
DEFAULT_START = "2024-01-02"
DEFAULT_END = "2026-03-28"
DEFAULT_INITIAL_CASH = 100_000.0

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
class FloorVariant:
    name: str
    role: str
    buy_floor: str
    buy_floor_quantile: float | None
    buy_floor_std_mult: float | None
    config_path: Path
    seeds: tuple[int, ...]

    def as_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "buy_floor": self.buy_floor,
            "seeds": list(self.seeds),
        }
        if self.buy_floor_quantile is not None:
            d["buy_floor_quantile"] = self.buy_floor_quantile
        if self.buy_floor_std_mult is not None:
            d["buy_floor_std_mult"] = self.buy_floor_std_mult
        return d


VARIANT_SPECS = [
    ("incumbent_mean_std", "incumbent", "adaptive_mean_std", None, 1.0),
    ("quantile_q90_top10", "candidate", "adaptive_quantile", 0.90, None),
    ("quantile_q80_top20", "candidate", "adaptive_quantile", 0.80, None),
    ("quantile_q70_top30", "candidate", "adaptive_quantile", 0.70, None),
    ("quantile_q60_top40", "candidate", "adaptive_quantile", 0.60, None),
    ("mean_std_mult05", "candidate", "adaptive_mean_std", None, 0.5),
]


def strategy_dir(repo_root: Path) -> Path:
    return repo_root / "backtesting" / "renquant_104"


def bootstrap_subrepo_imports(repo_root: Path) -> Path:
    for scripts_dir in (repo_root / "scripts", strategy_dir(repo_root)):
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
    from subrepo_paths import resolve_subrepo_root  # noqa: PLC0415

    subrepo_root = resolve_subrepo_root(repo_root).resolve()
    for repo in reversed(SUBREPO_IMPORT_ORDER):
        src = subrepo_root / repo / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    return subrepo_root


def build_variant_config(
    base: dict[str, Any],
    *,
    buy_floor: str,
    buy_floor_quantile: float | None,
    buy_floor_std_mult: float | None,
    output_path: Path,
) -> Path:
    cfg = deepcopy(base)
    panel = cfg.setdefault("ranking", {}).setdefault("panel_scoring", {})
    panel["buy_floor"] = buy_floor
    if buy_floor_quantile is not None:
        panel["buy_floor_quantile"] = buy_floor_quantile
    else:
        panel.pop("buy_floor_quantile", None)
    if buy_floor_std_mult is not None:
        panel["buy_floor_std_mult"] = buy_floor_std_mult
    else:
        panel.pop("buy_floor_std_mult", None)
    panel.setdefault("buy_floor_min", 0.20)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return output_path


def build_variants(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> list[FloorVariant]:
    base = json.loads(base_config_path.read_text())
    variants = []
    for name, role, bf, q, mult in VARIANT_SPECS:
        config_path = output_dir / f"strategy_config.{name}.json"
        build_variant_config(
            base,
            buy_floor=bf,
            buy_floor_quantile=q,
            buy_floor_std_mult=mult,
            output_path=config_path,
        )
        variants.append(FloorVariant(
            name=name,
            role=role,
            buy_floor=bf,
            buy_floor_quantile=q,
            buy_floor_std_mult=mult,
            config_path=config_path,
            seeds=seeds,
        ))
    return variants


def build_aa_variant(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> FloorVariant:
    base = json.loads(base_config_path.read_text())
    config_path = output_dir / "strategy_config.AA_resplit.json"
    build_variant_config(
        base,
        buy_floor="adaptive_mean_std",
        buy_floor_quantile=None,
        buy_floor_std_mult=1.0,
        output_path=config_path,
    )
    return FloorVariant(
        name="AA_resplit",
        role="aa_resplit",
        buy_floor="adaptive_mean_std",
        buy_floor_quantile=None,
        buy_floor_std_mult=1.0,
        config_path=config_path,
        seeds=tuple(s + AA_SEED_OFFSET for s in seeds),
    )


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def execute_variant(
    variant: FloorVariant,
    *,
    start: str,
    end: str,
    initial_cash: float,
    manifest_path: str,
    repo_root: Path,
) -> dict[str, Any]:
    sd = strategy_dir(repo_root)
    if str(sd) not in sys.path:
        sys.path.insert(0, str(sd))
    bootstrap_subrepo_imports(repo_root)

    config = json.loads(variant.config_path.read_text())
    config["_strategy_dir"] = str(sd)
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
        strategy_dir=sd,
        ohlcv=ohlcv,
        spy_df=spy_df,
        sector_etf_map=etf_map,
        initial_cash=float(initial_cash),
        backtest_start=start,
        backtest_end=end,
        snapshot=False,
    )

    metrics = result.get("metrics", {})
    return {
        "variant": variant.name,
        "role": variant.role,
        "buy_floor": variant.buy_floor,
        "buy_floor_quantile": variant.buy_floor_quantile,
        "buy_floor_std_mult": variant.buy_floor_std_mult,
        "apy": metrics.get("apy"),
        "sharpe": metrics.get("sharpe"),
        "max_dd": metrics.get("max_dd"),
        "calmar": metrics.get("calmar"),
        "total_return": metrics.get("total_return"),
        "cash_pct_mean": metrics.get("cash_pct_mean"),
        "n_trades": metrics.get("n_trades"),
        "seeds": list(variant.seeds),
    }


def print_results(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 100)
    print("RANK FLOOR CALIBRATION SWEEP RESULTS")
    print("=" * 100)
    header = (f"{'Variant':<25} {'Floor':>15} {'APY':>8} {'Sharpe':>8} "
              f"{'MaxDD':>8} {'Cash%':>8} {'Trades':>8}")
    print(header)
    print("-" * 100)

    sorted_results = sorted(
        results,
        key=lambda r: r.get("sharpe") or -999,
        reverse=True,
    )
    for r in sorted_results:
        floor_desc = r["buy_floor"]
        if r.get("buy_floor_quantile") is not None:
            floor_desc += f" q={r['buy_floor_quantile']:.2f}"
        elif r.get("buy_floor_std_mult") is not None:
            floor_desc += f" k={r['buy_floor_std_mult']:.1f}"

        parts = [f"{r['variant']:<25} {floor_desc:>15}"]
        for key, fmt in [("apy", "{:>7.1%}"), ("sharpe", "{:>8.3f}"),
                         ("max_dd", "{:>7.1%}"), ("cash_pct_mean", "{:>7.1%}"),
                         ("n_trades", "{:>8.0f}")]:
            val = r.get(key)
            if val is not None:
                parts.append(fmt.format(val))
            else:
                parts.append(f"{'N/A':>8}")
        print(" ".join(parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--initial-cash", type=float, default=DEFAULT_INITIAL_CASH)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    repo_root = default_repo_root()
    sd = strategy_dir(repo_root)
    base_config_path = Path(args.base_config)
    if not base_config_path.is_absolute():
        base_config_path = sd / base_config_path
    if not base_config_path.exists():
        print(f"ERROR: base config not found: {base_config_path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else sd / "artifacts" / "diagnostics" / f"rank_floor_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = build_variants(
        base_config_path=base_config_path,
        output_dir=output_dir,
        seeds=FROZEN_SEEDS,
    )
    aa = build_aa_variant(
        base_config_path=base_config_path,
        output_dir=output_dir,
        seeds=FROZEN_SEEDS,
    )
    all_variants = variants + [aa]

    plan = {
        "study": "rank-floor-calibration-sweep",
        "design_doc": "orchestrator PR #408",
        "mode": "execute" if args.execute else "dry_run",
        "base_config": str(base_config_path),
        "manifest": args.manifest_path,
        "start": args.start,
        "end": args.end,
        "seeds": list(FROZEN_SEEDS),
        "n_variants": len(all_variants),
        "variants": [v.as_json() for v in all_variants],
    }

    plan_path = output_dir / "sweep_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    if not args.execute:
        print(f"DRY RUN: {len(all_variants)} variants planned "
              f"(6 grid + 1 A/A)")
        print(f"Plan saved to {plan_path}")
        print(f"Seeds: {FROZEN_SEEDS}")
        print(f"Base config: {base_config_path}")
        print(f"\nTo execute: add --execute")
        for v in all_variants:
            desc = v.buy_floor
            if v.buy_floor_quantile is not None:
                desc += f" q={v.buy_floor_quantile}"
            if v.buy_floor_std_mult is not None:
                desc += f" k={v.buy_floor_std_mult}"
            print(f"  {v.name:<25} [{v.role:>10}]: {desc}")
        return 0

    print(f"EXECUTING {len(all_variants)} variants × {len(FROZEN_SEEDS)} seeds")
    print(f"Output: {output_dir}")

    results = []
    for i, variant in enumerate(all_variants):
        print(f"\n[{i+1}/{len(all_variants)}] Running {variant.name}...")
        t0 = time.time()
        try:
            result = execute_variant(
                variant,
                start=args.start,
                end=args.end,
                initial_cash=args.initial_cash,
                manifest_path=args.manifest_path,
                repo_root=repo_root,
            )
            elapsed = time.time() - t0
            result["elapsed_seconds"] = elapsed
            results.append(result)
            apy = result.get("apy")
            sharpe = result.get("sharpe")
            print(f"  Done in {elapsed:.0f}s — "
                  f"APY={apy:.1%} Sharpe={sharpe:.3f}"
                  if apy is not None and sharpe is not None
                  else f"  Done in {elapsed:.0f}s")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.0f}s: {exc}")
            results.append({
                "variant": variant.name,
                "role": variant.role,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            })

    results_path = output_dir / "sweep_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(f"\nResults saved to {results_path}")

    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
