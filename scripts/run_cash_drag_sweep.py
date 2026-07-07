#!/usr/bin/env python3
"""Cash drag parameter sweep — OAT (one-at-a-time) sensitivity analysis.

Tests each candidate parameter independently against the incumbent production
config. No pre-assumed conclusions — the backtest data decides.

Usage::

    # Dry-run: print the plan
    python scripts/run_cash_drag_sweep.py

    # Execute
    python scripts/run_cash_drag_sweep.py --execute
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, field
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
class SweepVariant:
    name: str
    role: str  # incumbent | candidate | aa_resplit
    hypothesis: str
    seeds: tuple[int, ...]
    config_overrides: dict[str, Any] = field(default_factory=dict)
    config_path: Path | None = None


VARIANT_SPECS: list[tuple[str, str, str, dict[str, Any]]] = [
    # (name, role, hypothesis, overrides)
    # V0: incumbent — no overrides
    ("V0_incumbent", "incumbent", "baseline production config", {}),
    # H1: kelly.fractional
    ("V1_frac_04", "candidate", "H1: fractional 0.3→0.4",
     {"ranking.kelly_sizing.fractional": 0.4}),
    ("V2_frac_05", "candidate", "H1: fractional 0.3→0.5 (half-Kelly)",
     {"ranking.kelly_sizing.fractional": 0.5}),
    ("V3_frac_07", "candidate", "H1: fractional 0.3→0.7",
     {"ranking.kelly_sizing.fractional": 0.7}),
    # H2: kelly.max_concentration
    ("V4_maxconc_015", "candidate", "H2: max_concentration 0.12→0.15",
     {"ranking.kelly_sizing.max_concentration": 0.15}),
    ("V5_maxconc_020", "candidate", "H2: max_concentration 0.12→0.20",
     {"ranking.kelly_sizing.max_concentration": 0.20}),
    # H3: kelly.top_up_threshold
    ("V6_topup_002", "candidate", "H3: top_up_threshold 0.05→0.02",
     {"ranking.kelly_sizing.top_up_threshold": 0.02}),
    # H4: VetoWeakBuys floor
    ("V7_quantile_q70", "candidate", "H4: buy_floor adaptive_quantile q=0.70",
     {"ranking.panel_scoring.buy_floor": "adaptive_quantile",
      "ranking.panel_scoring.buy_floor_quantile": 0.70}),
    # H8: qp_turnover_max
    ("V8_turnover_025", "candidate", "H8: qp_turnover_max 0.15→0.25",
     {"regime_params.BULL_CALM.qp_turnover_max": 0.25}),
]


def _set_nested(d: dict, dotpath: str, value: Any) -> None:
    keys = dotpath.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


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
    overrides: dict[str, Any],
    output_path: Path,
) -> Path:
    cfg = deepcopy(base)
    for dotpath, value in overrides.items():
        _set_nested(cfg, dotpath, value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return output_path


def build_all_variants(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> list[SweepVariant]:
    base = json.loads(base_config_path.read_text())
    variants = []
    for name, role, hypothesis, overrides in VARIANT_SPECS:
        config_path = output_dir / f"strategy_config.{name}.json"
        build_variant_config(base, overrides, config_path)
        variants.append(SweepVariant(
            name=name,
            role=role,
            hypothesis=hypothesis,
            seeds=seeds,
            config_overrides=overrides,
            config_path=config_path,
        ))
    # A/A control
    aa_path = output_dir / "strategy_config.AA_resplit.json"
    build_variant_config(base, {}, aa_path)
    variants.append(SweepVariant(
        name="AA_resplit",
        role="aa_resplit",
        hypothesis="A/A control (noise floor calibration)",
        seeds=tuple(s + AA_SEED_OFFSET for s in seeds),
        config_overrides={},
        config_path=aa_path,
    ))
    return variants


def execute_variant(
    variant: SweepVariant,
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
        "hypothesis": variant.hypothesis,
        "overrides": variant.config_overrides,
        "apy": metrics.get("apy"),
        "sharpe": metrics.get("sharpe"),
        "max_dd": metrics.get("max_dd"),
        "calmar": metrics.get("calmar"),
        "total_return": metrics.get("total_return"),
        "cash_pct_mean": metrics.get("cash_pct_mean"),
        "n_trades": metrics.get("n_trades"),
        "turnover": metrics.get("turnover"),
        "seeds": list(variant.seeds),
    }


def print_results(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 120)
    print("CASH DRAG PARAMETER SWEEP — OAT RESULTS")
    print("=" * 120)
    header = (f"{'Variant':<20} {'Hypothesis':<35} {'APY':>8} {'Sharpe':>8} "
              f"{'MaxDD':>8} {'Cash%':>8} {'Trades':>8} {'Turnov':>8}")
    print(header)
    print("-" * 120)

    incumbent = next((r for r in results if r["role"] == "incumbent"), None)

    for r in results:
        parts = [f"{r['variant']:<20}", f"{r['hypothesis'][:34]:<35}"]
        for key, fmt in [("apy", "{:>7.1%}"), ("sharpe", "{:>8.3f}"),
                         ("max_dd", "{:>7.1%}"), ("cash_pct_mean", "{:>7.1%}"),
                         ("n_trades", "{:>8.0f}"), ("turnover", "{:>7.1%}")]:
            val = r.get(key)
            if val is not None:
                parts.append(fmt.format(val))
            else:
                parts.append(f"{'N/A':>8}")
        line = " ".join(parts)

        if incumbent and r["role"] == "candidate":
            inc_cash = incumbent.get("cash_pct_mean")
            cur_cash = r.get("cash_pct_mean")
            inc_sharpe = incumbent.get("sharpe")
            cur_sharpe = r.get("sharpe")
            deltas = []
            if inc_cash is not None and cur_cash is not None:
                deltas.append(f"cash {(cur_cash-inc_cash)*100:+.1f}pp")
            if inc_sharpe is not None and cur_sharpe is not None:
                deltas.append(f"sharpe {cur_sharpe-inc_sharpe:+.3f}")
            if deltas:
                line += f"  [{', '.join(deltas)}]"

        if r["role"] == "incumbent":
            line += "  ← INCUMBENT"
        elif r["role"] == "aa_resplit":
            line += "  ← A/A CONTROL"

        print(line)


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
        else sd / "artifacts" / "diagnostics" / f"cash_drag_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = build_all_variants(
        base_config_path=base_config_path,
        output_dir=output_dir,
        seeds=FROZEN_SEEDS,
    )

    plan = {
        "study": "cash-drag-OAT-parameter-sweep",
        "design_doc": "doc/design/2026-07-07-cash-drag-parameter-sweep.md",
        "mode": "execute" if args.execute else "dry_run",
        "base_config": str(base_config_path),
        "manifest": args.manifest_path,
        "start": args.start,
        "end": args.end,
        "seeds": list(FROZEN_SEEDS),
        "n_variants": len(variants),
        "variants": [
            {"name": v.name, "role": v.role, "hypothesis": v.hypothesis,
             "overrides": v.config_overrides, "seeds": list(v.seeds)}
            for v in variants
        ],
    }

    plan_path = output_dir / "sweep_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    if not args.execute:
        print(f"DRY RUN: {len(variants)} variants planned")
        print(f"Plan saved to {plan_path}")
        print(f"Seeds: {FROZEN_SEEDS}")
        print(f"Base config: {base_config_path}")
        print(f"\nVariants:")
        for v in variants:
            overrides = v.config_overrides or "(none)"
            print(f"  {v.name:<20} [{v.role:>10}] {v.hypothesis}")
            if v.config_overrides:
                for k, val in v.config_overrides.items():
                    print(f"    {k} = {val}")
        print(f"\nTo execute: add --execute")
        return 0

    print(f"EXECUTING {len(variants)} variants x {len(FROZEN_SEEDS)} seeds")
    print(f"Output: {output_dir}")

    results = []
    for i, variant in enumerate(variants):
        print(f"\n[{i+1}/{len(variants)}] Running {variant.name} "
              f"({variant.hypothesis})...")
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
            cash = result.get("cash_pct_mean")
            if apy is not None and sharpe is not None and cash is not None:
                print(f"  Done in {elapsed:.0f}s — "
                      f"APY={apy:.1%} Sharpe={sharpe:.3f} Cash={cash:.1%}")
            else:
                print(f"  Done in {elapsed:.0f}s")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.0f}s: {exc}")
            results.append({
                "variant": variant.name,
                "role": variant.role,
                "hypothesis": variant.hypothesis,
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
