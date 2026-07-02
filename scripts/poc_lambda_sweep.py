#!/usr/bin/env python3
"""A-1 pre-enable evidence: cash_drag_lambda dose-response on REAL run inputs
(RS-2 requires a sweep before enabling; this harness quantifies the direction
and magnitude of the λ lever ahead of the full in-pipeline shadow sweep).

SCOPE (stated honestly): a SENSITIVITY study, not a full replay. It drives the
REAL pipeline solver (`renquant_pipeline.kernel.portfolio_qp.qp_solver.
solve_portfolio_qp_from_snapshot`) with inputs taken from the latest daily FULL
runs (mu/sigma per candidate+holding from candidate_scores; current weights
from the run's own trades/holdings approximation) under SIMPLIFIED constraints:
per-name cap 0.12 (BULL_CALM), no sector/correlation groups, no wash-sale mask.
The S6 in-pipeline 10-session shadow sweep remains the enable-gating AC; this
tells us what to expect and whether the lever moves the measured deployment gap
at all.

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
PER_NAME_CAP = 0.12  # BULL_CALM max_position_pct
TURNOVER_MAX = 0.30


def _runs(con, k=2):
    return pd.read_sql(
        "select run_id, count(*) n from candidate_scores "
        "where run_id like '%-live-%' group by run_id having n >= 80 "
        "order by run_id desc limit ?", con, params=(k,))["run_id"].tolist()


def sweep_run(con, run_id):
    from renquant_pipeline.kernel.portfolio_qp.constraint_snapshot import (  # noqa: PLC0415
        ConstraintSnapshot)
    from renquant_pipeline.kernel.portfolio_qp.qp_solver import (  # noqa: PLC0415
        solve_portfolio_qp_from_snapshot)
    cs = pd.read_sql(
        "select ticker, role, mu, sigma from candidate_scores "
        "where run_id=? and mu is not null and sigma is not null and sigma > 0",
        con, params=(run_id,))
    cs = cs.drop_duplicates("ticker").reset_index(drop=True)
    n = len(cs)
    # current weights: holdings approximated at equal book weights from the
    # run's holding rows (simplification, stated in-module docstring)
    tr = pd.read_sql(
        "select ticker, target_pct from trades where run_id=? and action like 'buy%'",
        con, params=(run_id,))
    held = set(cs.loc[cs["role"] == "holding", "ticker"])
    w_cur = np.array([
        min(0.08, PER_NAME_CAP) if t in held else 0.0 for t in cs["ticker"]])
    snap = ConstraintSnapshot(
        n=n,
        tickers=tuple(cs["ticker"]),
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
    rows = []
    for lam in LAMBDAS:
        sol = solve_portfolio_qp_from_snapshot(
            snap,
            mu=cs["mu"].to_numpy(),
            sigma=cs["sigma"].to_numpy(),
            cash_drag_lambda=lam,
            allow_optimal_inaccurate=True,
        )
        tw = np.asarray(sol.target_w)
        rows.append({
            "lambda": lam,
            "status": sol.status,
            "deployed_frac": round(float(tw.sum()), 3),
            "n_names_gt_1pct": int((tw > 0.01).sum()),
            "max_weight": round(float(tw.max()), 3),
            "turnover": round(float(np.abs(tw - w_cur).sum()), 3),
        })
    return {"run_id": run_id, "n_names": n, "n_held_approx": len(held),
            "sweep": rows}


def main() -> None:
    con = sqlite3.connect(os.path.join(RQ, "data/runs.alpaca.db"))
    out = {
        "scope": ("sensitivity study on real run inputs with simplified "
                  "constraints (per-name cap only); the S6 in-pipeline "
                  "10-session shadow sweep remains the enable-gating AC"),
        "lambdas": LAMBDAS,
        "runs": [sweep_run(con, r) for r in _runs(con)],
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_lambda_sweep.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
