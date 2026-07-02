#!/usr/bin/env python3
"""POC-B: measure whether lane A (de-throttling) can reach 60% deployment,
or whether CONVICTION SCARCITY binds first (roadmap #230 §8.1 S6 Plan-B premise).

Claim under test: on recent live runs, so few names clear the conviction floor
(mu >= 0.03) that even with top_n=infinity and fractional-free sizing the
deployable fraction is far below 60% -> the parking sleeve (lane B) is the only
mechanism that closes the idle-cash gap; lane A only removes selection
artifacts.

Method: read candidate_scores for the recent daily FULL runs (>=80 candidate
rows). For each run compute the mu distribution and three counterfactual
deployment ceilings, using each candidate's own kelly_target_pct capped at the
BULL_CALM per-name cap (0.12):
  C0 observed        : what the run actually deployed (trades table)
  C1 top_n removed   : sum of capped targets over the top-N-eligible set
                       (mu>=floor, not vetoed/blocked except the top_n window)
  C2 all-eligible    : sum of capped targets over ALL candidates with
                       mu >= floor and blocked_by not in HARD blocks
                       (veto / correlation kept as blocks; window+cash ignored)

Reproduce:
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python \
    <orchestrator>/scripts/poc_conviction_deployability.py
Inputs (read-only): data/runs.alpaca.db (candidate_scores, trades).
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_b_conviction_deployability.json
"""
import json
import os
import sqlite3

import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
MU_FLOOR = 0.03
PER_NAME_CAP = 0.12  # BULL_CALM max_position_pct
HARD_BLOCKS = {"veto", "correlation", "sector"}  # kept binding in C2


def main() -> None:
    con = sqlite3.connect(DB)
    runs = pd.read_sql(
        "select run_id, count(*) n from candidate_scores "
        "where run_id like '%-live-%' group by run_id having n >= 80 "
        "order by run_id desc limit 6", con)
    results = []
    for run_id in runs["run_id"]:
        cs = pd.read_sql(
            "select ticker, role, mu, kelly_target_pct, blocked_by, selected "
            "from candidate_scores where run_id=?", con, params=(run_id,))
        cand = cs[cs["role"] == "candidate"].copy()
        cand["tgt"] = cand["kelly_target_pct"].clip(upper=PER_NAME_CAP)
        eligible = cand[(cand["mu"] >= MU_FLOOR)]
        # C2: everything above floor not hard-blocked
        c2 = eligible[~eligible["blocked_by"].fillna("").str.contains(
            "|".join(HARD_BLOCKS), case=False)]
        tr = pd.read_sql(
            "select ticker, target_pct from trades where run_id=? "
            "and action like 'buy%'", con, params=(run_id,))
        results.append({
            "run_id": run_id,
            "n_candidates": int(len(cand)),
            "mu_median": round(float(cand["mu"].median()), 4),
            "mu_p90": round(float(cand["mu"].quantile(0.9)), 4),
            "n_above_floor": int(len(eligible)),
            "n_above_floor_not_hard_blocked": int(len(c2)),
            "C0_observed_deploy_pct": round(float(tr["target_pct"].sum()), 4),
            "C2_ceiling_deploy_pct": round(float(c2["tgt"].sum()), 4),
            "eligible_tickers": sorted(c2["ticker"].tolist()),
        })
    summary = {
        "mu_floor": MU_FLOOR,
        "per_name_cap": PER_NAME_CAP,
        "hard_blocks_kept": sorted(HARD_BLOCKS),
        "runs": results,
        "verdict_hint": ("if C2_ceiling << 0.60 across runs, conviction "
                         "scarcity binds and lane B is required to close the "
                         "idle-cash gap; lane A only removes artifacts"),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_b_conviction_deployability.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
