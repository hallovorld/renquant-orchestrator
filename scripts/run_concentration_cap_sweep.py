#!/usr/bin/env python3
"""Concentration cap parameter sweep — implements the approved design doc
``doc/design/2026-07-06-concentration-cap-research.md`` (PR #403).

3D sweep over the Kelly sizing config, per #403's frozen grid:

    entry_cap    ∈ {0.08, 0.10, 0.12, 0.15, 0.20}   # max_concentration
    drift_buffer ∈ {0.0, 0.08, 0.13, 0.18, inf}      # TrimHeldTask trigger buffer; inf = trim OFF
    topup_thresh ∈ {0.02, 0.03, 0.05}                 # top_up_threshold

    75 combinations total (5 × 5 × 3).

``drift_buffer`` occupies the exact arithmetic slot ``TrimHeldTask`` already
reads as ``ranking.kelly_sizing.trim_threshold`` (trim fires when
``current_pct > kelly_target + trim_threshold``) — no new trigger mechanism.
``drift_buffer = inf`` maps to ``trim_enabled: False`` (today's incumbent
behavior); finite values map to ``trim_enabled: True`` + that
``trim_threshold``.

Seeds are FROZEN at {42, 43, 44} per #403's round-2 fix (this repo's
standard seed triple; see doc/research/2026-07-03-d3-core-shrink-check.md).
The verdict rule is UNANIMITY across all 3 seeds, not mean/median — a
config's verdict for any criterion is NULL unless all 3 seeds independently
satisfy it (matching the D3/M8 convention that seeds are a robustness check,
not additional statistical power to pool).

Controls (§7.2, #403 "Controls" section):
  - A/A: incumbent config re-run with seed-offset resplit; must show ~zero
    Sharpe delta vs the incumbent's own primary run.
  - Placebo: shuffle-label evidence from
    scripts/analyze_manifest_sanity_placebo.py, supplied via --placebo-json
    (same pattern as scripts/run_kelly_sigma_horizon_ab.py).
  - Incumbent: entry_cap=0.12, drift_buffer=inf, topup_thresh=0.05 (today's
    production config) as the control arm every candidate is compared to.

Usage::

    # Dry-run: print the plan (no sims run)
    python scripts/run_concentration_cap_sweep.py

    # Execute the full 75-variant grid with the frozen seed set
    python scripts/run_concentration_cap_sweep.py --execute

    # Execute with a specific base config / manifest
    python scripts/run_concentration_cap_sweep.py --execute \\
        --base-config strategy_config.sim_kelly_ab_admoff.json \\
        --manifest-path artifacts/sim/walkforward_manifest_v2_20260602.json \\
        --placebo-json artifacts/diagnostics/.../placebo/shuffle_placebo.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from renquant_orchestrator.runtime_paths import default_repo_root


# ── Frozen contract (#403) — do not change without a new design PR ──
FROZEN_SEEDS: tuple[int, ...] = (42, 43, 44)
AA_SEED_OFFSET = 1000

ENTRY_CAPS: tuple[float, ...] = (0.08, 0.10, 0.12, 0.15, 0.20)
DRIFT_BUFFERS: tuple[float, ...] = (0.0, 0.08, 0.13, 0.18, float("inf"))
TOPUP_THRESHOLDS: tuple[float, ...] = (0.02, 0.03, 0.05)

INCUMBENT_ENTRY_CAP = 0.12
INCUMBENT_DRIFT_BUFFER = float("inf")
INCUMBENT_TOPUP_THRESHOLD = 0.05

REQUIRED_REGIMES: tuple[str, ...] = ("BULL_CALM", "BEAR", "BULL_VOLATILE")

# Materiality bands (#403 decision rule).
FULL_PERIOD_SHARPE_MATERIALITY_BAND = 0.02
PER_REGIME_SHARPE_MATERIALITY_BAND = 0.02
MAXDD_TOLERANCE_MULT = 1.10
TURNOVER_CEILING_MULT = 1.25
AA_MAX_ABS_SHARPE_LIFT = 0.10

# No formal per-trade transaction-cost model exists in this sim (verified:
# no commission/slippage field on trade_events, no cost_model function in
# sim/ or kernel/). Cost delta is therefore a MODELED proxy — turnover ×
# an assumed per-unit-turnover cost — not a readout of a pre-existing
# model. This is a simplifying assumption, documented here and in the
# progress doc, not a discovery of an existing calibrated cost model.
ASSUMED_COST_BPS_PER_UNIT_TURNOVER = 10.0

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


def strategy_dir(repo_root: Path) -> Path:
    return repo_root / "backtesting" / "renquant_104"


@dataclass(frozen=True)
class VariantSpec:
    name: str
    role: str  # "incumbent" | "candidate" | "aa_resplit"
    entry_cap: float
    drift_buffer: float
    topup_threshold: float
    config_path: Path
    seeds: tuple[int, ...] = FROZEN_SEEDS

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "entry_cap": self.entry_cap,
            "drift_buffer": (
                "inf" if math.isinf(self.drift_buffer) else self.drift_buffer
            ),
            "topup_threshold": self.topup_threshold,
            "config_path": str(self.config_path),
            "seeds": list(self.seeds),
        }


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
    entry_cap: float,
    drift_buffer: float,
    topup_threshold: float,
    output_path: Path,
) -> Path:
    cfg = deepcopy(base)
    kelly = cfg.setdefault("ranking", {}).setdefault("kelly_sizing", {})
    kelly["max_concentration"] = entry_cap
    kelly["top_up_threshold"] = topup_threshold
    if math.isinf(drift_buffer):
        # inf = trim OFF — today's incumbent behavior. TrimHeldTask's own
        # `trim_enabled` gate (default False) already encodes this; no
        # trim_threshold value is read when disabled.
        kelly["trim_enabled"] = False
        kelly.pop("trim_threshold", None)
    else:
        kelly["trim_enabled"] = True
        kelly["trim_threshold"] = drift_buffer
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return output_path


def _variant_name(entry_cap: float, drift_buffer: float, topup_thresh: float) -> str:
    db = "inf" if math.isinf(drift_buffer) else f"{int(drift_buffer * 100):02d}"
    return f"cap{int(entry_cap * 100):02d}_drift{db}_topup{int(topup_thresh * 100):02d}"


def build_grid_variants(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> list[VariantSpec]:
    """Build the full 75-variant frozen grid (#403 "Parameter grid")."""
    base = json.loads(base_config_path.read_text())
    variants = []
    for entry_cap in ENTRY_CAPS:
        for drift_buffer in DRIFT_BUFFERS:
            for topup_thresh in TOPUP_THRESHOLDS:
                name = _variant_name(entry_cap, drift_buffer, topup_thresh)
                config_path = output_dir / f"strategy_config.{name}.json"
                build_variant_config(
                    base,
                    entry_cap=entry_cap,
                    drift_buffer=drift_buffer,
                    topup_threshold=topup_thresh,
                    output_path=config_path,
                )
                role = (
                    "incumbent"
                    if (
                        entry_cap == INCUMBENT_ENTRY_CAP
                        and math.isinf(drift_buffer) == math.isinf(INCUMBENT_DRIFT_BUFFER)
                        and topup_thresh == INCUMBENT_TOPUP_THRESHOLD
                    )
                    else "candidate"
                )
                variants.append(VariantSpec(
                    name=name,
                    role=role,
                    entry_cap=entry_cap,
                    drift_buffer=drift_buffer,
                    topup_threshold=topup_thresh,
                    config_path=config_path,
                    seeds=seeds,
                ))
    assert len(variants) == 75, f"expected 75 grid variants, got {len(variants)}"
    return variants


def build_aa_variant(
    *,
    base_config_path: Path,
    output_dir: Path,
    seeds: tuple[int, ...],
) -> VariantSpec:
    """Incumbent config, seed-offset resplit — the A/A control (#403 §Controls)."""
    base = json.loads(base_config_path.read_text())
    config_path = output_dir / "strategy_config.AA_incumbent_resplit.json"
    build_variant_config(
        base,
        entry_cap=INCUMBENT_ENTRY_CAP,
        drift_buffer=INCUMBENT_DRIFT_BUFFER,
        topup_threshold=INCUMBENT_TOPUP_THRESHOLD,
        output_path=config_path,
    )
    aa_seeds = tuple(s + AA_SEED_OFFSET for s in seeds)
    return VariantSpec(
        name="AA_incumbent_resplit",
        role="aa_resplit",
        entry_cap=INCUMBENT_ENTRY_CAP,
        drift_buffer=INCUMBENT_DRIFT_BUFFER,
        topup_threshold=INCUMBENT_TOPUP_THRESHOLD,
        config_path=config_path,
        seeds=aa_seeds,
    )


# ── Metrics helpers (adapted from scripts/run_kelly_sigma_horizon_ab.py) ──

def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _numeric_values(values: Any) -> list[float]:
    out: list[float] = []
    for value in values or []:
        num = _finite(value)
        if num is not None:
            out.append(num)
    return out


def _mean(values: Any) -> float:
    vals = _numeric_values(values)
    return float(sum(vals) / len(vals)) if vals else float("nan")


def _returns_metrics(returns: list[float]) -> dict[str, float]:
    returns = _numeric_values(returns)
    if not returns:
        return {"total_return": 0.0, "apy": 0.0, "sharpe": float("nan"),
                "max_dd": float("nan"), "calmar": float("nan")}
    total = 1.0
    equity = []
    for ret in returns:
        total *= 1.0 + ret
        equity.append(total)
    total_return = total - 1.0
    apy = (
        (1.0 + total_return) ** (252.0 / len(returns)) - 1.0
        if total_return > -1.0 else float("nan")
    )
    mean_ret = sum(returns) / len(returns)
    std_ret = (
        math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1))
        if len(returns) >= 2 else float("nan")
    )
    sharpe = (
        mean_ret / std_ret * math.sqrt(252.0)
        if math.isfinite(std_ret) and std_ret > 0.0 else float("nan")
    )
    peak = -float("inf")
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0.0:
            max_dd = max(max_dd, 1.0 - value / peak)
    calmar = apy / max_dd if max_dd > 0.0 and math.isfinite(apy) else float("nan")
    return {
        "total_return": float(total_return), "apy": float(apy),
        "sharpe": float(sharpe), "max_dd": float(max_dd), "calmar": float(calmar),
    }


def per_regime_metrics(equity_df: Any, required_regimes: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Split equity_df by its 'regime' column and compute per-regime
    returns metrics — regimes have no dedicated field on SimResult; they
    must be derived from equity_df, matching
    run_kelly_sigma_horizon_ab.py::_seed_per_regime_metrics."""
    out: dict[str, dict[str, Any]] = {r: {"apy": None, "sharpe": None, "max_dd": None}
                                        for r in required_regimes}
    if equity_df is None or getattr(equity_df, "empty", True) or "portfolio" not in equity_df.columns:
        return out
    if "regime" not in equity_df.columns:
        return out
    portfolio = equity_df["portfolio"].astype(float)
    returns = portfolio.pct_change()
    for raw_regime, group in equity_df.groupby("regime"):
        regime = str(raw_regime or "UNKNOWN")
        if regime not in required_regimes:
            continue
        group_returns = _numeric_values(returns.reindex(group.index).dropna().tolist())
        perf = _returns_metrics(group_returns)
        out[regime] = {
            "n_days": int(len(group)),
            "apy": perf["apy"], "sharpe": perf["sharpe"],
            "max_dd": perf["max_dd"], "calmar": perf["calmar"],
        }
    return out


def compute_turnover_fills_cost(
    trade_log: list[dict], *, n_days: int, incumbent_turnover_annualized: float | None = None,
) -> dict[str, Any]:
    """Turnover (annualized sum of |Δweight| proxy), fill count, and a
    MODELED cost-delta-vs-incumbent — required outputs per #403's
    round-2 fix (top_up_threshold is a churn-control knob; the decision
    rule's "net of transaction costs" claim needs churn as a first-class
    metric, not a footnote)."""
    fill_count = len(trade_log or [])
    weight_flow = 0.0
    for t in trade_log or []:
        tp = _finite(t.get("target_pct"))
        if tp is not None:
            weight_flow += abs(tp)
    years = max(n_days / 252.0, 1e-9)
    turnover_annualized = weight_flow / years
    modeled_cost_bps = turnover_annualized * ASSUMED_COST_BPS_PER_UNIT_TURNOVER
    cost_delta_bps = (
        modeled_cost_bps - (incumbent_turnover_annualized or 0.0) * ASSUMED_COST_BPS_PER_UNIT_TURNOVER
        if incumbent_turnover_annualized is not None else None
    )
    return {
        "turnover_annualized": turnover_annualized,
        "fill_count": fill_count,
        "modeled_cost_bps": modeled_cost_bps,
        "cost_delta_bps_vs_incumbent": cost_delta_bps,
    }


def compute_winner_continuation(trade_log: list[dict], *, entry_cap: float) -> dict[str, Any]:
    """Approximate winner-continuation diagnostic (#403 metrics section).

    APPROXIMATION, documented honestly: this sim exposes discrete trade
    events (buy target_pct, sell pnl_pct), not a continuous daily
    per-ticker weight trace. A position's weight-at-exit is estimated as
    ``entry_target_pct * (1 + pnl_pct)`` — i.e. assuming share count was
    unchanged between the most recent buy/topup and the sell (holds
    unless an intervening partial sell/topup occurred, which this proxy
    does not detect). A sell is counted as "let it run" when this
    estimated exit weight exceeds entry_cap; its realized pnl_pct then
    answers whether letting it drift past entry_cap was net positive.
    """
    last_buy_target_pct: dict[str, float] = {}
    drifted_returns: list[float] = []
    for t in trade_log or []:
        ticker = t.get("ticker")
        if t.get("action") == "buy":
            tp = _finite(t.get("target_pct"))
            if ticker is not None and tp is not None:
                last_buy_target_pct[ticker] = tp
        elif t.get("action") == "sell":
            entry_tp = last_buy_target_pct.get(ticker)
            pnl_pct = _finite(t.get("pnl_pct"))
            if entry_tp is not None and pnl_pct is not None:
                implied_exit_pct = entry_tp * (1.0 + pnl_pct)
                if implied_exit_pct > entry_cap:
                    drifted_returns.append(pnl_pct)
    return {
        "n_drifted_above_cap": len(drifted_returns),
        "mean_pnl_pct_when_drifted": _mean(drifted_returns) if drifted_returns else None,
        "net_positive": (
            _mean(drifted_returns) > 0.0 if drifted_returns else None
        ),
    }


def prefetch_ohlcv(base_config_path: Path, subrepo_root: Path) -> dict[str, Any]:
    """Load OHLCV data ONCE for all variants. Returns a bundle dict with
    keys: ohlcv, spy_df, sector_etf_map."""
    from kernel.data import fetch_ohlcv  # noqa: PLC0415

    config = json.loads(base_config_path.read_text())
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
    return {"ohlcv": ohlcv, "spy_df": spy_df, "sector_etf_map": etf_map}


def execute_variant(
    variant: VariantSpec,
    *,
    subrepo_root: Path,
    strategy_dir_path: Path,
    start: str,
    end: str,
    initial_cash: float,
    manifest_path: str,
    incumbent_turnover_annualized: float | None = None,
    ohlcv_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one variant across ALL its frozen seeds and return per-seed
    results plus the aggregated view. Per-seed results are kept
    (not just mean/std) because #403's verdict rule is UNANIMITY, which
    requires checking each seed independently."""
    config = json.loads(variant.config_path.read_text())
    config["_strategy_dir"] = str(strategy_dir_path)
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

    from sim.runner import run_backtest_multi_seed  # noqa: PLC0415

    if ohlcv_bundle is not None:
        ohlcv = ohlcv_bundle["ohlcv"]
        spy_df = ohlcv_bundle["spy_df"]
        etf_map = ohlcv_bundle["sector_etf_map"]
    else:
        from kernel.data import fetch_ohlcv  # noqa: PLC0415
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
        seeds=list(variant.seeds), parallel=False, config=config,
        strategy_dir=strategy_dir_path, ohlcv=ohlcv, spy_df=spy_df,
        sector_etf_map=etf_map, initial_cash=float(initial_cash),
        backtest_start=start, backtest_end=end, snapshot=False,
    )

    per_seed: list[dict[str, Any]] = []
    for seed, seed_result in zip(result.seeds, result.per_seed_results):
        regimes = per_regime_metrics(getattr(seed_result, "equity_df", None), REQUIRED_REGIMES)
        eq_df = getattr(seed_result, "equity_df", None)
        n_days = int(len(eq_df)) if eq_df is not None else 0
        trade_log = getattr(seed_result, "trade_log", None)
        trade_log = trade_log if trade_log is not None else []
        turnover = compute_turnover_fills_cost(
            trade_log, n_days=n_days,
            incumbent_turnover_annualized=incumbent_turnover_annualized,
        )
        winner_cont = compute_winner_continuation(
            trade_log, entry_cap=variant.entry_cap,
        )
        per_seed.append({
            "seed": seed,
            "apy": _finite(seed_result.apy),
            "sharpe": _finite(seed_result.sharpe),
            "max_dd": _finite(seed_result.max_dd),
            "calmar": _finite(seed_result.calmar),
            "per_regime": regimes,
            "turnover": turnover,
            "winner_continuation": winner_cont,
        })

    return {
        "variant": variant.name,
        "role": variant.role,
        "entry_cap": variant.entry_cap,
        "drift_buffer": "inf" if math.isinf(variant.drift_buffer) else variant.drift_buffer,
        "topup_threshold": variant.topup_threshold,
        "seeds": list(variant.seeds),
        "per_seed": per_seed,
    }


# ── Verdict (unanimity across all 3 frozen seeds — #403 decision rule) ──

def _seed_criteria(
    seed_row: dict[str, Any],
    incumbent_seed_row: dict[str, Any],
) -> dict[str, bool | None]:
    """Evaluate #403's 7 numbered criteria for ONE seed vs the matching
    incumbent seed. Returns None (not False) when data is missing, so the
    caller can distinguish "failed" from "unmeasurable"."""
    out: dict[str, bool | None] = {}

    cand_bc = (seed_row.get("per_regime") or {}).get("BULL_CALM", {})
    inc_bc = (incumbent_seed_row.get("per_regime") or {}).get("BULL_CALM", {})
    cand_bc_sharpe = _finite(cand_bc.get("sharpe"))
    inc_bc_sharpe = _finite(inc_bc.get("sharpe"))
    out["1_bull_calm_sharpe_net_of_cost"] = (
        cand_bc_sharpe >= inc_bc_sharpe
        if cand_bc_sharpe is not None and inc_bc_sharpe is not None else None
    )

    cand_bc_dd = _finite(cand_bc.get("max_dd"))
    inc_bc_dd = _finite(inc_bc.get("max_dd"))
    out["2_bull_calm_maxdd_tolerance"] = (
        cand_bc_dd <= inc_bc_dd * MAXDD_TOLERANCE_MULT
        if cand_bc_dd is not None and inc_bc_dd is not None else None
    )

    cand_full_sharpe = _finite(seed_row.get("sharpe"))
    inc_full_sharpe = _finite(incumbent_seed_row.get("sharpe"))
    out["3_full_period_no_material_regression"] = (
        cand_full_sharpe >= inc_full_sharpe - FULL_PERIOD_SHARPE_MATERIALITY_BAND
        if cand_full_sharpe is not None and inc_full_sharpe is not None else None
    )

    per_regime_ok = True
    per_regime_any_missing = False
    for regime in REQUIRED_REGIMES:
        cand_r = (seed_row.get("per_regime") or {}).get(regime, {})
        inc_r = (incumbent_seed_row.get("per_regime") or {}).get(regime, {})
        c_sharpe, i_sharpe = _finite(cand_r.get("sharpe")), _finite(inc_r.get("sharpe"))
        c_dd, i_dd = _finite(cand_r.get("max_dd")), _finite(inc_r.get("max_dd"))
        if c_sharpe is None or i_sharpe is None or c_dd is None or i_dd is None:
            per_regime_any_missing = True
            continue
        if c_sharpe < i_sharpe - PER_REGIME_SHARPE_MATERIALITY_BAND:
            per_regime_ok = False
        if c_dd > i_dd * MAXDD_TOLERANCE_MULT:
            per_regime_ok = False
    out["4_per_regime_no_material_regression_all_regimes"] = (
        None if per_regime_any_missing else per_regime_ok
    )

    cand_turnover = _finite((seed_row.get("turnover") or {}).get("turnover_annualized"))
    inc_turnover = _finite((incumbent_seed_row.get("turnover") or {}).get("turnover_annualized"))
    out["5_turnover_ceiling"] = (
        cand_turnover <= inc_turnover * TURNOVER_CEILING_MULT
        if cand_turnover is not None and inc_turnover is not None else None
    )

    # 6. placebo — evaluated once at the study level, not per-seed; see
    #    apply_placebo_to_verdict(). Left unset here.
    out["6_placebo_no_lift"] = None

    winner_cont = seed_row.get("winner_continuation") or {}
    out["7_winner_continuation_net_positive"] = winner_cont.get("net_positive")

    return out


def unanimity_verdict(
    candidate_result: dict[str, Any],
    incumbent_result: dict[str, Any],
    *,
    placebo_passed: bool | None,
) -> dict[str, Any]:
    """#403 verdict rule: a candidate clears ONLY if ALL 3 frozen seeds
    independently satisfy EVERY criterion (unanimity, not mean/median —
    matching this repo's D3/M8 seed-robustness convention, not additional
    statistical power to pool)."""
    cand_seeds = {row["seed"]: row for row in candidate_result.get("per_seed", [])}
    inc_seeds = {row["seed"] - AA_SEED_OFFSET if row["seed"] >= AA_SEED_OFFSET else row["seed"]: row
                 for row in incumbent_result.get("per_seed", [])}

    per_seed_criteria: dict[int, dict[str, bool | None]] = {}
    for seed, cand_row in cand_seeds.items():
        inc_row = inc_seeds.get(seed)
        if inc_row is None:
            per_seed_criteria[seed] = {f"criterion_{i}": None for i in range(1, 8)}
            continue
        criteria = _seed_criteria(cand_row, inc_row)
        criteria["6_placebo_no_lift"] = placebo_passed
        per_seed_criteria[seed] = criteria

    criterion_names = sorted({name for c in per_seed_criteria.values() for name in c})
    unanimous: dict[str, bool | None] = {}
    for name in criterion_names:
        values = [c.get(name) for c in per_seed_criteria.values()]
        if any(v is None for v in values):
            unanimous[name] = None  # NULL, not "average out" — missing data blocks the verdict
        else:
            unanimous[name] = all(values)

    all_measured = all(v is not None for v in unanimous.values())
    tier3_ready = all_measured and all(unanimous.values())

    return {
        "variant": candidate_result.get("variant"),
        "per_seed_criteria": per_seed_criteria,
        "unanimous_criteria": unanimous,
        "tier3_ready": tier3_ready,
        "blocked_reasons": [
            name for name, v in unanimous.items() if v is not True
        ],
    }


def load_placebo_evidence(paths: list[str]) -> dict[str, Any]:
    """Same pattern as scripts/run_kelly_sigma_horizon_ab.py::load_placebo_evidence —
    external shuffle/time-shift placebo run via analyze_manifest_sanity_placebo.py."""
    evidence = []
    for raw in paths:
        payload = json.loads(Path(raw).read_text())
        interp = payload.get("interpretation") or {}
        evidence.append({
            "path": str(raw),
            "promotion_evidence": bool(interp.get("promotion_evidence")),
        })
    return {
        "provided": bool(evidence),
        "passed": bool(evidence) and all(row["promotion_evidence"] for row in evidence),
        "items": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--initial-cash", type=float, default=DEFAULT_INITIAL_CASH)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--placebo-json", action="append", default=[],
                        help="path(s) to analyze_manifest_sanity_placebo.py JSON output; "
                             "required for a Tier-3 verdict (criterion 6)")
    parser.add_argument(
        "--dev-seeds", default=None,
        help="DEV/local-testing ONLY override for the frozen seed set — NEVER use for a "
             "gating run. Requires --i-know-this-breaks-the-frozen-contract.",
    )
    parser.add_argument("--i-know-this-breaks-the-frozen-contract", action="store_true")
    parser.add_argument(
        "--workers", type=int, default=max(1, os.cpu_count() - 2),
        help="parallel worker threads (default: cpu_count - 2; 1 = serial)",
    )
    args = parser.parse_args(argv)

    if args.dev_seeds and not args.i_know_this_breaks_the_frozen_contract:
        print(
            "ERROR: --dev-seeds requires --i-know-this-breaks-the-frozen-contract. "
            "The seed set is frozen to {42, 43, 44} per #403's approved contract; "
            "any gating run MUST use the frozen set.",
        )
        return 1
    seeds = (
        tuple(int(s.strip()) for s in args.dev_seeds.split(","))
        if args.dev_seeds and args.i_know_this_breaks_the_frozen_contract
        else FROZEN_SEEDS
    )

    repo_root = default_repo_root()
    strat_dir = strategy_dir(repo_root)

    base_config_path = Path(args.base_config)
    if not base_config_path.is_absolute():
        base_config_path = strat_dir / base_config_path
    if not base_config_path.exists():
        print(f"ERROR: base config not found: {base_config_path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir
        else strat_dir / "artifacts" / "diagnostics" / f"concentration_cap_sweep_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    grid_variants = build_grid_variants(
        base_config_path=base_config_path, output_dir=output_dir, seeds=seeds,
    )
    aa_variant = build_aa_variant(
        base_config_path=base_config_path, output_dir=output_dir, seeds=seeds,
    )
    placebo = load_placebo_evidence(args.placebo_json)

    plan = {
        "study": "concentration-cap-asymmetry-sweep",
        "design_doc": "orchestrator PR #403 (doc/design/2026-07-06-concentration-cap-research.md)",
        "mode": "execute" if args.execute else "dry_run",
        "base_config": str(base_config_path),
        "manifest": args.manifest_path,
        "start": args.start, "end": args.end,
        "seeds": list(seeds),
        "seeds_frozen": seeds == FROZEN_SEEDS,
        "n_grid_variants": len(grid_variants),
        "grid": {
            "entry_caps": list(ENTRY_CAPS),
            "drift_buffers": ["inf" if math.isinf(x) else x for x in DRIFT_BUFFERS],
            "topup_thresholds": list(TOPUP_THRESHOLDS),
        },
        "controls": {
            "aa_resplit": aa_variant.as_json(),
            "placebo": placebo,
            "incumbent": {
                "entry_cap": INCUMBENT_ENTRY_CAP,
                "drift_buffer": "inf",
                "topup_threshold": INCUMBENT_TOPUP_THRESHOLD,
            },
        },
        "variants": [v.as_json() for v in grid_variants],
    }
    plan_path = output_dir / "sweep_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    if not args.execute:
        print(f"DRY RUN: {len(grid_variants)} grid variants + 1 A/A control planned")
        print(f"Plan saved to {plan_path}")
        print(f"Seeds: {seeds} (frozen={seeds == FROZEN_SEEDS})")
        if not placebo["provided"]:
            print("WARNING: no --placebo-json supplied — Tier-3 verdict criterion 6 "
                  "(placebo no-lift) will be NULL until placebo evidence is provided.")
        print("\nTo execute: add --execute")
        return 0

    subrepo_root = bootstrap_subrepo_imports(repo_root)
    n_workers = max(1, args.workers)

    print(f"Pre-fetching OHLCV data (shared across all variants)...")
    ohlcv_bundle = prefetch_ohlcv(base_config_path, subrepo_root)
    print(f"  loaded {len(ohlcv_bundle['ohlcv'])} symbols")

    print(f"EXECUTING incumbent (control arm) + A/A resplit + {len(grid_variants)} grid variants")
    print(f"  workers={n_workers} ({'serial' if n_workers == 1 else 'threaded'})")
    incumbent_variant = next(v for v in grid_variants if v.role == "incumbent")
    incumbent_result = execute_variant(
        incumbent_variant, subrepo_root=subrepo_root, strategy_dir_path=strat_dir,
        start=args.start, end=args.end, initial_cash=args.initial_cash,
        manifest_path=args.manifest_path, ohlcv_bundle=ohlcv_bundle,
    )
    inc_turnover = _mean([
        (row.get("turnover") or {}).get("turnover_annualized")
        for row in incumbent_result.get("per_seed", [])
    ])

    aa_result = execute_variant(
        aa_variant, subrepo_root=subrepo_root, strategy_dir_path=strat_dir,
        start=args.start, end=args.end, initial_cash=args.initial_cash,
        manifest_path=args.manifest_path, incumbent_turnover_annualized=inc_turnover,
        ohlcv_bundle=ohlcv_bundle,
    )
    inc_sharpe_mean = _mean([row.get("sharpe") for row in incumbent_result.get("per_seed", [])])
    aa_sharpe_mean = _mean([row.get("sharpe") for row in aa_result.get("per_seed", [])])
    aa_sharpe_lift = (
        aa_sharpe_mean - inc_sharpe_mean
        if math.isfinite(aa_sharpe_mean) and math.isfinite(inc_sharpe_mean) else float("nan")
    )
    aa_passed = math.isfinite(aa_sharpe_lift) and abs(aa_sharpe_lift) <= AA_MAX_ABS_SHARPE_LIFT
    print(f"A/A resplit Sharpe lift: {aa_sharpe_lift:+.4f} "
          f"({'PASS' if aa_passed else 'FAIL'} — tolerance ±{AA_MAX_ABS_SHARPE_LIFT})")

    candidates = [v for v in grid_variants if v.role != "incumbent"]
    results = [incumbent_result]
    verdicts = []

    common_kwargs = dict(
        subrepo_root=subrepo_root, strategy_dir_path=strat_dir,
        start=args.start, end=args.end, initial_cash=args.initial_cash,
        manifest_path=args.manifest_path, incumbent_turnover_annualized=inc_turnover,
        ohlcv_bundle=ohlcv_bundle,
    )

    if n_workers <= 1:
        for i, variant in enumerate(candidates):
            print(f"[{i+1}/{len(candidates)}] Running {variant.name}...")
            t0 = time.time()
            try:
                result = execute_variant(variant, **common_kwargs)
                result["elapsed_seconds"] = time.time() - t0
                results.append(result)
                verdict = unanimity_verdict(result, incumbent_result, placebo_passed=(
                    placebo["passed"] if placebo["provided"] else None
                ))
                verdicts.append(verdict)
                print(f"  tier3_ready={verdict['tier3_ready']}")
            except Exception as exc:
                print(f"  FAILED: {exc}")
                results.append({"variant": variant.name, "error": str(exc)})
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            future_to_variant = {}
            for variant in candidates:
                future = pool.submit(execute_variant, variant, **common_kwargs)
                future_to_variant[future] = variant
            done_count = 0
            for future in as_completed(future_to_variant):
                done_count += 1
                variant = future_to_variant[future]
                try:
                    result = future.result()
                    results.append(result)
                    verdict = unanimity_verdict(result, incumbent_result, placebo_passed=(
                        placebo["passed"] if placebo["provided"] else None
                    ))
                    verdicts.append(verdict)
                    print(f"[{done_count}/{len(candidates)}] {variant.name} "
                          f"tier3_ready={verdict['tier3_ready']}")
                except Exception as exc:
                    print(f"[{done_count}/{len(candidates)}] {variant.name} FAILED: {exc}")
                    results.append({"variant": variant.name, "error": str(exc)})

    results_path = output_dir / "sweep_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str) + "\n")
    verdicts_path = output_dir / "sweep_verdicts.json"
    verdicts_path.write_text(json.dumps({
        "aa_control": {"sharpe_lift": aa_sharpe_lift, "passed": aa_passed},
        "placebo": placebo,
        "verdicts": verdicts,
    }, indent=2, default=str) + "\n")
    print(f"\nResults: {results_path}\nVerdicts: {verdicts_path}")

    tier3_winners = [v["variant"] for v in verdicts if v["tier3_ready"]]
    print(f"\nTier-3-ready candidates: {tier3_winners or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
