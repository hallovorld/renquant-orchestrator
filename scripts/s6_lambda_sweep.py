#!/usr/bin/env python3
"""S6: in-pipeline QP cash-drag lambda sweep — writes to config_experiments.

Runs the QP solver at multiple cash_drag_lambda values against REAL daily-run
inputs (mu/sigma from candidate_scores, w_current from trades.target_pct) and
records each result as a config_experiments row. The readiness_monitor checks
this table for the S6 gate (3 configs x 15 sessions = 45 experiments).

Data flow:
  runs.alpaca.db (RO) → solver → config_experiments (same DB, WRITE)

This is the promoted version of poc_lambda_sweep.py. Key differences:
  - Writes structured experiment rows to config_experiments (not JSON output)
  - Runs against ALL qualifying runs (not just the latest 2)
  - Persists per-run per-lambda results for the readiness monitor

STRICTLY READ-ONLY on everything except config_experiments.
Pipeline solver imported from renquant-pipeline.

Usage:
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python \\
    <orchestrator>/scripts/s6_lambda_sweep.py [--dry-run] [--runs N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ORCH = Path(__file__).resolve().parents[1] / "src"
RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
PIPE = os.environ.get(
    "RQ_PIPELINE_ROOT", "/Users/renhao/git/github/renquant-pipeline/src")
sys.path.insert(0, str(ORCH))
sys.path.insert(0, PIPE)

LAMBDAS = [0.0, 0.01, 0.02, 0.05, 0.10]
PER_NAME_CAP = 0.12
TURNOVER_MAX = 0.15
MIN_INVESTED_PCT = 0.7
MIN_CANDIDATES = 40


def _qualifying_runs(con: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    """Select runs with enough scored candidates for a meaningful sweep."""
    df = pd.read_sql(
        "SELECT pr.run_id, pr.run_date, pr.created_at, "
        "  (SELECT COUNT(*) FROM candidate_scores cs "
        "   WHERE cs.run_id = pr.run_id AND cs.mu IS NOT NULL) AS n "
        "FROM pipeline_runs pr "
        "WHERE pr.run_type = 'live' AND pr.strategy = 'renquant-104'",
        con)
    df = df[df["n"] >= MIN_CANDIDATES].copy()
    if df.empty:
        return []
    df["created_at"] = pd.to_datetime(df["created_at"])
    latest_per_date = (
        df.sort_values("created_at")
        .groupby("run_date", as_index=False)
        .last()
        .sort_values("run_date", ascending=False))
    if limit:
        latest_per_date = latest_per_date.head(limit)
    return latest_per_date[["run_id", "run_date"]].to_dict("records")


def _reconstruct_w_current(con, cs, run_id, run_date):
    held = cs.loc[cs["role"] == "holding", "ticker"].tolist()
    if not held:
        return {}, held
    placeholders = ",".join("?" for _ in held)
    tp = pd.read_sql(
        f"SELECT t.ticker, t.target_pct, pr.run_date "
        f"FROM trades t JOIN pipeline_runs pr ON pr.run_id = t.run_id "
        f"WHERE t.ticker IN ({placeholders}) AND pr.run_date <= ? "
        f"AND t.target_pct IS NOT NULL",
        con, params=(*held, run_date))
    if tp.empty:
        return {}, held
    tp = tp.sort_values("run_date").drop_duplicates("ticker", keep="last")
    return dict(zip(tp["ticker"], tp["target_pct"])), held


def _solve(w_cur, n, tickers, mu, sigma, lam):
    from renquant_pipeline.kernel.portfolio_qp.constraint_snapshot import (
        ConstraintSnapshot)
    from renquant_pipeline.kernel.portfolio_qp.qp_solver import (
        solve_portfolio_qp_from_snapshot)
    snap = ConstraintSnapshot(
        n=n,
        tickers=tuple(tickers),
        w_current=w_cur,
        w_upper_hard=np.full(n, PER_NAME_CAP),
        w_upper=np.full(n, PER_NAME_CAP),
        w_lower=0.0,
        dw_max=np.full(n, 0.5),
        cash_reserve=0.0,
        turnover_max=TURNOVER_MAX,
        drawdown=0.0,
        drawdown_limit=0.20,
        gross_max=None,
        wash_sale_mask=np.zeros(n, dtype=bool),
        sector_indicator=None,
        sector_cap_vec=None,
        sector_names=None,
        corr_group_pairs=(),
    )
    sol = solve_portfolio_qp_from_snapshot(
        snap, mu=mu, sigma=sigma, cash_drag_lambda=lam,
        min_invested_pct=MIN_INVESTED_PCT, allow_optimal_inaccurate=True)
    tw = np.asarray(sol.target_w)
    return {
        "status": sol.status,
        "deployed_frac": round(float(tw.sum()), 4),
        "n_names_selected": int((tw > 0.01).sum()),
        "max_weight": round(float(tw.max()), 4),
        "turnover": round(float(np.abs(tw - w_cur).sum()), 4),
    }


def _experiment_id(run_id: str, lam: float) -> str:
    key = f"s6-sweep:{run_id}:lambda={lam}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def sweep_run(con, run_id, run_date):
    cs = pd.read_sql(
        "SELECT ticker, role, mu, sigma FROM candidate_scores "
        "WHERE run_id=? AND mu IS NOT NULL AND sigma IS NOT NULL AND sigma > 0",
        con, params=(run_id,))
    cs = cs.drop_duplicates("ticker").reset_index(drop=True)
    n = len(cs)
    if n < MIN_CANDIDATES:
        return []
    tickers = tuple(cs["ticker"])
    mu = cs["mu"].to_numpy()
    sigma = cs["sigma"].to_numpy()

    w_by_ticker, held = _reconstruct_w_current(con, cs, run_id, run_date)
    w_cur = np.array([w_by_ticker.get(t, 0.0) for t in tickers])

    now_iso = datetime.now(timezone.utc).isoformat()
    experiments = []
    for lam in LAMBDAS:
        sol = _solve(w_cur, n, tickers, mu, sigma, lam)
        experiments.append({
            "experiment_id": _experiment_id(run_id, lam),
            "run_date": run_date,
            "config_name": f"lambda_{lam}",
            "config": {
                "cash_drag_lambda": lam,
                "min_invested_pct": MIN_INVESTED_PCT,
                "turnover_max": TURNOVER_MAX,
                "per_name_cap": PER_NAME_CAP,
            },
            "baseline_run_id": run_id,
            "deployed_frac": sol["deployed_frac"],
            "n_names_selected": sol["n_names_selected"],
            "turnover": sol["turnover"],
            "max_weight": sol["max_weight"],
            "solver_status": sol["status"],
            "cash_drag_lambda": lam,
            "min_invested_pct": MIN_INVESTED_PCT,
            "turnover_max": TURNOVER_MAX,
            "metrics": {
                "n_candidates": n,
                "n_held": len(held),
                "sum_w_current": round(float(w_cur.sum()), 4),
            },
            "created_at": now_iso,
        })
    return experiments


def main():
    parser = argparse.ArgumentParser(
        description="S6: QP cash-drag lambda sweep → config_experiments")
    parser.add_argument("--db", default=os.path.join(RQ, "data/runs.alpaca.db"),
                        help="runs.alpaca.db path")
    parser.add_argument("--runs", type=int, default=None,
                        help="limit to N most recent qualifying runs")
    parser.add_argument("--dry-run", action="store_true",
                        help="print experiments without writing")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    runs = _qualifying_runs(con, limit=args.runs)
    print(f"Qualifying runs: {len(runs)}")

    all_experiments = []
    for r in runs:
        exps = sweep_run(con, r["run_id"], r["run_date"])
        all_experiments.extend(exps)
        print(f"  {r['run_date']} ({r['run_id'][:20]}...): {len(exps)} experiments")

    if args.dry_run:
        print(f"\nDry run: {len(all_experiments)} experiments prepared (not written)")
        for exp in all_experiments[:5]:
            print(f"  {exp['run_date']} {exp['config_name']}: "
                  f"deployed={exp['deployed_frac']}, turnover={exp['turnover']}, "
                  f"status={exp['solver_status']}")
        return

    from renquant_orchestrator.config_experiment_store import (
        ensure_table, write_experiments)
    ensure_table(con)
    n = write_experiments(con, all_experiments)
    total = con.execute("SELECT COUNT(*) FROM config_experiments").fetchone()[0]
    print(f"\nWritten: {n} new experiments ({total} total in config_experiments)")
    con.close()


if __name__ == "__main__":
    main()
