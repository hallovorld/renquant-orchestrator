"""L1 deployment-controller SHADOW logger (allocation machine, orch#918 L1).

Operator grant 2026-08-08 ("开"): the shadow phase computes and LOGS the
controller's target exposure daily beside the live run. It places no orders,
changes no config, and writes exactly one JSONL line per run date to its own
log directory.

WHAT IT LOGS — components, not just the verdict. Each row carries σ̂ (EWMA
vol), the regime multiplier g with its source (the live snapshot's regime
label + confidence), the target at the frozen candidate σ* = 0.15, and the
book's ACHIEVED exposure from the same snapshot. Because the components are
logged, any later σ* choice can be recomputed from the log alone — the
shadow period is σ*-agnostic, so the operator's drawdown-appetite decision
does not reset the clock.

FROZEN PARAMETERS (the orch#919 evaluation set — changing any is a new dated
amendment, not an edit):
    λ = 0.94   EWMA decay (RiskMetrics)
    σ* = 0.15  candidate target vol (recomputable later from components)
    κ_bear = 0.5, κ_vol = 0.25
    E_min = 0.3, E_max = 1.0

LIVE ADAPTATION, stated openly: the evaluation used the regime-artifact
posterior vector; the live surface emits (regime label, confidence) in
``live_state_snapshots``. The shadow uses
``g = 1 − κ_bear·conf·1[BEAR] − κ_vol·conf·1[BULL_VOLATILE]`` — the same
functional form fed by what production actually publishes daily. The row
records the label+confidence so the approximation is auditable.

FAIL-CLOSED: missing OHLCV, an unreadable DB, or a stale snapshot (not
today's) produce a REFUSED row on stdout and exit 1 — never a silent skip,
never an invented number. Idempotent per date: an existing row for the date
refuses a rewrite (append-only log).
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .runtime_paths import default_data_root, default_strategy_config_path

LAMBDA = 0.94
SIGMA_STAR = 0.15
KAPPA_BEAR = 0.5
KAPPA_VOL = 0.25
E_MIN, E_MAX = 0.3, 1.0
VOL_WINDOW_DAYS = 500  # trading days of history fed to the EWMA

DEFAULT_LOG_SUBDIR = ("logs", "l1_exposure_shadow")
SCHEMA = "l1_exposure_shadow.v1"


def universe_ew_returns(ohlcv_root: Path, tickers: list[str], *,
                        min_names: int = 30) -> "object":
    """Equal-weight daily TR returns over the sector-map universe.

    Import-light: pandas is imported here, not at module top, so the module
    stays cheap for callers that only need the pure helpers."""
    import pandas as pd  # noqa: PLC0415

    from renquant_model_common.total_return import total_return_close  # noqa: PLC0415

    frames = {}
    for t in tickers:
        f = ohlcv_root / t / "1d.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        div = df["dividend"] if "dividend" in df.columns else pd.Series(0.0, index=df.index)
        frames[t] = total_return_close(df["close"], div).pct_change()
    if len(frames) < min_names:
        raise RuntimeError(
            f"only {len(frames)} of {len(tickers)} names have OHLCV — refusing "
            f"a vol estimate on a thin universe (floor {min_names})")
    return pd.DataFrame(frames).mean(axis=1).dropna().iloc[-VOL_WINDOW_DAYS:]


def ewma_vol_annualized(returns) -> float:
    """EWMA(λ) vol of the return series, annualized. Uses ALL rows given —
    the caller controls the window. No lookahead by construction: the caller
    feeds returns up to and including the last completed session."""
    var = returns.pow(2).ewm(alpha=1 - LAMBDA).mean().iloc[-1]
    return float(math.sqrt(var * 252))


def regime_multiplier(regime: str | None, confidence: float | None) -> float:
    conf = confidence if confidence is not None and math.isfinite(confidence) else 0.0
    conf = min(max(conf, 0.0), 1.0)
    g = 1.0
    if regime == "BEAR":
        g -= KAPPA_BEAR * conf
    elif regime == "BULL_VOLATILE":
        g -= KAPPA_VOL * conf
    return max(g, 0.0)


def target_exposure(sigma_hat: float, g: float, *,
                    sigma_star: float = SIGMA_STAR) -> float:
    if not (math.isfinite(sigma_hat) and sigma_hat > 0):
        raise ValueError(f"unusable sigma_hat {sigma_hat!r}")
    return float(min(max((sigma_star / sigma_hat) * g, E_MIN), E_MAX))


def latest_snapshot(db_path: Path) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT run_date, regime, confidence, cash, portfolio_value "
            "FROM live_state_snapshots ORDER BY rowid DESC LIMIT 1").fetchone()
    finally:
        con.close()
    if row is None:
        raise RuntimeError("live_state_snapshots is empty")
    return dict(zip(("run_date", "regime", "confidence", "cash", "portfolio_value"), row))


def build_row(*, snapshot: dict, sigma_hat: float, asof: date) -> dict:
    g = regime_multiplier(snapshot.get("regime"), snapshot.get("confidence"))
    pv = snapshot.get("portfolio_value")
    cash = snapshot.get("cash")
    achieved = (1.0 - cash / pv) if (pv and cash is not None and pv > 0) else None
    tgt = target_exposure(sigma_hat, g)
    return {
        "schema": SCHEMA,
        "asof": asof.isoformat(),
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sigma_hat": round(sigma_hat, 6),
        "regime": snapshot.get("regime"),
        "regime_confidence": snapshot.get("confidence"),
        "g": round(g, 6),
        "sigma_star_candidate": SIGMA_STAR,
        "target_exposure": round(tgt, 6),
        "achieved_exposure": None if achieved is None else round(achieved, 6),
        "gap": None if achieved is None else round(tgt - achieved, 6),
        "params": {"lambda": LAMBDA, "kappa_bear": KAPPA_BEAR,
                   "kappa_vol": KAPPA_VOL, "e_min": E_MIN, "e_max": E_MAX},
        "snapshot_run_date": snapshot.get("run_date"),
    }


def append_row(log_dir: Path, row: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / "l1_exposure_shadow.jsonl"
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("asof") == row["asof"]:
                    raise RuntimeError(
                        f"a row for {row['asof']} already exists — append-only, "
                        "one row per date; refusing a rewrite")
            except json.JSONDecodeError:
                continue  # a corrupt line never masks the duplicate check for valid ones
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=None,
                    help="explicit umbrella override; defaults resolve through "
                         "default_data_root()/default_strategy_config_path()")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--ohlcv-root", type=Path, default=None)
    ap.add_argument("--sector-map-config", type=Path, default=None,
                    help="strategy config carrying sector_map (universe source)")
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--allow-stale-snapshot", action="store_true",
                    help="log even if the newest snapshot is not from today "
                         "(the row records snapshot_run_date either way)")
    args = ap.parse_args(argv)

    # Canonical runtime contract (codex on orch#920): data/state resolve through
    # default_data_root() (RENQUANT_DATA_ROOT first, umbrella fallback), and the
    # universe comes from the PINNED strategy-config resolver — never a
    # hardcoded sibling working tree. --repo-root stays as explicit override.
    data_root = default_data_root(args.repo_root)
    db = args.db or data_root / "data" / "runs.alpaca.db"
    ohlcv = args.ohlcv_root or data_root / "data" / "ohlcv"
    log_dir = args.log_dir or data_root.joinpath(*DEFAULT_LOG_SUBDIR)
    cfg_path = (args.sector_map_config
                or default_strategy_config_path(repo_root=args.repo_root))

    try:
        sector_map = json.loads(cfg_path.read_text(encoding="utf-8"))["sector_map"]
        tickers = [t for t, s in sector_map.items()
                   if s not in ("benchmark", "defensive_bonds")]
        snap = latest_snapshot(db)
        today = date.today()
        if snap.get("run_date") != today.isoformat() and not args.allow_stale_snapshot:
            print(json.dumps({"status": "REFUSED-STALE-SNAPSHOT",
                              "snapshot_run_date": snap.get("run_date"),
                              "today": today.isoformat()}, indent=2))
            return 1
        rets = universe_ew_returns(ohlcv, tickers)
        sigma_hat = ewma_vol_annualized(rets)
        row = build_row(snapshot=snap, sigma_hat=sigma_hat, asof=today)
        out = append_row(log_dir, row)
    except Exception as exc:  # noqa: BLE001 — fail-closed with the reason on stdout
        print(json.dumps({"status": "REFUSED", "why": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "LOGGED", "path": str(out), **row}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
