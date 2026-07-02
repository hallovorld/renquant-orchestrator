#!/usr/bin/env python3
"""A-1 pre-enable evidence: cash_drag_lambda dose-response on REAL run inputs
(RS-2 requires a sweep before enabling; this harness quantifies the direction
and magnitude of the λ lever ahead of the full in-pipeline shadow sweep).

SCOPE (stated honestly): a SENSITIVITY study, not a full replay. It drives the
REAL pipeline solver (`renquant_pipeline.kernel.portfolio_qp.qp_solver.
solve_portfolio_qp_from_snapshot`) with inputs taken from the latest daily FULL
runs (mu/sigma per candidate+holding from candidate_scores; current weights
reconstructed from each holding's most recent `trades.target_pct` as of the
run date) under SIMPLIFIED constraints: per-name cap 0.12 (BULL_CALM), no
sector/correlation groups, no wash-sale mask. The S6 in-pipeline 10-session
shadow sweep remains the enable-gating AC; this tells us what to expect and
whether the lever moves the measured deployment gap at all.

ROUND 2 (2026-07-02, review r4) — the solver only adds the cash-drag objective
term when BOTH `min_invested_pct > 0` AND `cash_drag_lambda > 0`
(`qp_solver.py:468`). The round-1 script never passed `min_invested_pct`, so
the wrapper default (0.0) silently disabled the entire lambda mechanism —
identical solutions at every lambda were GUARANTEED by construction, not
evidence the turnover cap masks anything. Separately: the LIVE production
config (`strategy_config.json` → `rotation.joint_actions`) has BOTH
`qp_min_invested_pct=0` and `qp_cash_drag_lambda=0` set explicitly — i.e. the
cash-drag mechanism is currently fully disabled on BOTH axes, not just
lambda. A-1 (per RS-2 doc, `qp_cash_drag_lambda 0 -> 0.05`) as literally
scoped therefore has ZERO possible effect under current production settings —
this is a direct, mechanical consequence of the gate condition, not new
empirical evidence. To test whether "un-disabling the shipped control"
actually matters, this script now sweeps lambda at a representative
NON-ZERO `min_invested_pct` (0.7 — the value this same config carried before
it was zeroed out; see `strategy_config.json.pre-meta-label-deploy`), and
ALSO runs a genuine 2D sweep of lambda x turnover_max at that min_invested_pct
to separate "turnover cap masks lambda" from "lambda has no effect regardless
of turnover cap". A positive-control point (loose, non-binding turnover cap)
proves the harness can detect a lambda effect when the mechanism is actually
enabled.

Reproduce:
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python \
    <orchestrator>/scripts/poc_lambda_sweep.py
Inputs (read-only): data/runs.alpaca.db; renquant-pipeline sibling checkout.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_lambda_sweep.json
"""
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
PIPE = os.environ.get(
    "RQ_PIPELINE_ROOT", "/Users/renhao/git/github/renquant-pipeline/src")
sys.path.insert(0, PIPE)
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
LAMBDAS = [0.0, 0.01, 0.02, 0.05, 0.10]
PER_NAME_CAP = 0.12  # BULL_CALM max_position_pct (strategy_config.json)
TURNOVER_MAX_PRODUCTION = 0.15  # BULL_CALM qp_turnover_max (strategy_config.json)
TURNOVER_CAPS = [0.15, 0.20, 0.30, 0.50]  # production, global, prior-script, non-binding
MIN_INVESTED_PRODUCTION = 0.0  # CURRENT live config: rotation.joint_actions.qp_min_invested_pct
MIN_INVESTED_UNDISABLED = 0.7  # historical pre-zeroing value (strategy_config.json.pre-meta-label-deploy)
NON_BINDING_TURNOVER = 0.50  # positive-control point: looser than any real regime cap


def _runs(con, k=2):
    """Select the latest `created_at` run for each of the most recent `k`
    distinct calendar dates with >= 80 scored candidates, joined through
    pipeline_runs (NOT lexicographic run_id ordering -- a single date can
    carry many run_ids, and string order does not track created_at)."""
    df = pd.read_sql(
        "select pr.run_id, pr.run_date, pr.created_at, "
        "  (select count(*) from candidate_scores cs where cs.run_id = pr.run_id) as n "
        "from pipeline_runs pr "
        "where pr.run_type = 'live' and pr.strategy = 'renquant-104'",
        con)
    df = df[df["n"] >= 80].copy()
    if df.empty:
        return []
    df["created_at"] = pd.to_datetime(df["created_at"])
    latest_per_date = (
        df.sort_values("created_at")
        .groupby("run_date", as_index=False)
        .last()
        .sort_values("run_date", ascending=False))
    return latest_per_date["run_id"].head(k).tolist()


def _reconstruct_w_current(con, cs, run_id, run_date):
    """Point-in-time current weight per held ticker: the most recent
    trades.target_pct for that ticker as of (and including) this run's date.
    Not the run's own equal-weight-of-cap approximation used in round 1."""
    held = cs.loc[cs["role"] == "holding", "ticker"].tolist()
    if not held:
        return {}, held
    placeholders = ",".join("?" for _ in held)
    tp = pd.read_sql(
        f"select t.ticker, t.target_pct, pr.run_date "
        f"from trades t join pipeline_runs pr on pr.run_id = t.run_id "
        f"where t.ticker in ({placeholders}) and pr.run_date <= ? "
        f"and t.target_pct is not null",
        con, params=(*held, run_date))
    if tp.empty:
        return {}, held
    tp = tp.sort_values("run_date").drop_duplicates("ticker", keep="last")
    return dict(zip(tp["ticker"], tp["target_pct"])), held


def _solve(w_cur, n, tickers, mu, sigma, lam, min_invested_pct,
           turnover_max):
    from renquant_pipeline.kernel.portfolio_qp.constraint_snapshot import (  # noqa: PLC0415
        ConstraintSnapshot)
    from renquant_pipeline.kernel.portfolio_qp.qp_solver import (  # noqa: PLC0415
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
        turnover_max=turnover_max,
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
        min_invested_pct=min_invested_pct, allow_optimal_inaccurate=True)
    tw = np.asarray(sol.target_w)
    return {
        "lambda": lam,
        "min_invested_pct": min_invested_pct,
        "turnover_max": turnover_max,
        "status": sol.status,
        "deployed_frac": round(float(tw.sum()), 3),
        "n_names_gt_1pct": int((tw > 0.01).sum()),
        "max_weight": round(float(tw.max()), 3),
        "turnover": round(float(np.abs(tw - w_cur).sum()), 3),
    }


def sweep_run(con, run_id, run_date):
    cs = pd.read_sql(
        "select ticker, role, mu, sigma from candidate_scores "
        "where run_id=? and mu is not null and sigma is not null and sigma > 0",
        con, params=(run_id,))
    cs = cs.drop_duplicates("ticker").reset_index(drop=True)
    n = len(cs)
    tickers = tuple(cs["ticker"])
    mu = cs["mu"].to_numpy()
    sigma = cs["sigma"].to_numpy()

    w_by_ticker, held = _reconstruct_w_current(con, cs, run_id, run_date)
    n_reconstructed = sum(1 for t in held if t in w_by_ticker)
    w_cur = np.array([w_by_ticker.get(t, 0.0) for t in tickers])

    result = {
        "run_id": run_id, "run_date": run_date, "n_names": n,
        "n_held": len(held), "n_held_reconstructed": n_reconstructed,
        "n_held_no_trade_history": len(held) - n_reconstructed,
    }

    # (A) current production reality: min_invested_pct=0 -- structurally
    # guaranteed to be flat across lambda by the gate at qp_solver.py:468.
    # Reported for completeness, not presented as new evidence.
    result["production_reality_min_invested_0"] = [
        _solve(w_cur, n, tickers, mu, sigma, lam,
               MIN_INVESTED_PRODUCTION, TURNOVER_MAX_PRODUCTION)
        for lam in LAMBDAS
    ]

    # (B) "un-disabled" scenario: min_invested_pct restored to its
    # historical pre-zeroing value, lambda x turnover_max 2D sweep -- this
    # is the genuinely informative comparison (does turnover cap mask
    # lambda once the mechanism can actually act, or does lambda matter
    # regardless of turnover cap).
    result["undisabled_2d_sweep"] = [
        _solve(w_cur, n, tickers, mu, sigma, lam,
               MIN_INVESTED_UNDISABLED, tcap)
        for lam in LAMBDAS for tcap in TURNOVER_CAPS
    ]

    # (C) positive control: loose, deliberately non-binding turnover cap at
    # the un-disabled min_invested_pct -- proves the harness can detect a
    # lambda effect when the mechanism is genuinely active.
    result["positive_control_non_binding_turnover"] = [
        _solve(w_cur, n, tickers, mu, sigma, lam,
               MIN_INVESTED_UNDISABLED, NON_BINDING_TURNOVER)
        for lam in LAMBDAS
    ]
    return result


def main() -> None:
    con = sqlite3.connect(os.path.join(RQ, "data/runs.alpaca.db"))
    run_ids = _runs(con)
    runs_meta = pd.read_sql(
        "select run_id, run_date from pipeline_runs where run_id in (%s)"
        % ",".join("?" for _ in run_ids), con, params=run_ids
    ).set_index("run_id")["run_date"].to_dict()
    out = {
        "scope": ("sensitivity study on real run inputs with simplified "
                  "constraints (per-name cap only); the S6 in-pipeline "
                  "10-session shadow sweep remains the enable-gating AC"),
        "lambdas": LAMBDAS,
        "turnover_caps": TURNOVER_CAPS,
        "min_invested_production": MIN_INVESTED_PRODUCTION,
        "min_invested_undisabled": MIN_INVESTED_UNDISABLED,
        "runs": [sweep_run(con, r, runs_meta[r]) for r in run_ids],
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_lambda_sweep.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
