#!/usr/bin/env python3
"""S-TC: measure the transfer coefficient — the last reasoned-tier number in the
#231 §0 state vector (asserted ≈0.4; solver default λ etc. untouched).

Theory (Clarke–de Silva–Thorley 2002): IR = TC × IC × √BR with
TC = cross-sectional correlation between the ACTUAL active weights and the
UNCONSTRAINED risk-adjusted desired weights (w* ∝ μ/σ² — here the model's own
`kelly_target_pct`, which is exactly that quantity before the constraint stack).

Two measurements, honestly scoped until the S5 ledger makes full historical
book-TC routine:

  (1) FULL-BOOK TC (latest run only): actual weights from the broker's live
      positions (read-only GET /v2/positions) + cash, vs w* from the latest
      daily full run's candidate_scores (candidates AND holdings). One number,
      but the real thing.
  (2) BUY-SIDE DECISION-TC (per historical full run): among floor-clearing
      candidates (μ ≥ 0.03), corr between desired kelly_target_pct and the
      ACTUAL emitted buy target_pct (0 if not bought). Measures how much of
      the desired NEW-money allocation survives top_n / whole-share / cash /
      shrinkage. Computable for every full run in runs.alpaca.db.

Reproduce:
  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a && \
    .venv/bin/python <orchestrator>/scripts/poc_transfer_coefficient.py
Inputs (read-only): data/runs.alpaca.db; Alpaca /v2/positions.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json
"""
import json
import os
import sqlite3
import urllib.request

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
BASE = os.environ.get("ALPACA_BASE_URL", "https://api.alpaca.markets")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
MU_FLOOR = 0.03


def _full_runs(con) -> list[str]:
    return pd.read_sql(
        "select run_id, count(*) n from candidate_scores "
        "where run_id like '%-live-%' group by run_id having n >= 80 "
        "order by run_id", con)["run_id"].tolist()


def buy_side_decision_tc(con, run_id: str) -> dict | None:
    cs = pd.read_sql(
        "select ticker, role, mu, kelly_target_pct from candidate_scores "
        "where run_id=? and role='candidate'", con, params=(run_id,))
    elig = cs[(cs["mu"] >= MU_FLOOR) & cs["kelly_target_pct"].notna()].copy()
    if len(elig) < 4:
        return None
    tr = pd.read_sql(
        "select ticker, target_pct from trades where run_id=? and action like 'buy%'",
        con, params=(run_id,))
    actual = dict(zip(tr["ticker"], tr["target_pct"]))
    elig["w_actual"] = elig["ticker"].map(actual).fillna(0.0)
    if elig["w_actual"].std() == 0 or elig["kelly_target_pct"].std() == 0:
        tc_p = 0.0  # nothing bought: the constraint stack transferred nothing
    else:
        tc_p = float(np.corrcoef(elig["kelly_target_pct"], elig["w_actual"])[0, 1])
    return {"run_id": run_id, "n_eligible": int(len(elig)),
            "n_bought": int((elig["w_actual"] > 0).sum()),
            "buy_side_decision_tc": round(tc_p, 3)}


def full_book_tc(con) -> dict:
    latest = _full_runs(con)[-1]
    cs = pd.read_sql(
        "select ticker, role, mu, sigma, kelly_target_pct from candidate_scores "
        "where run_id=?", con, params=(latest,))
    # desired: kelly where present, else mu/sigma^2 (long-only: clip mu at 0)
    cs = cs.dropna(subset=["mu"]).copy()
    kelly = cs["kelly_target_pct"]
    fallback = cs["mu"].clip(lower=0) / cs["sigma"].replace(0, np.nan) ** 2
    cs["w_star"] = kelly.fillna(fallback).fillna(0.0).clip(lower=0)
    if cs["w_star"].sum() > 0:
        cs["w_star"] /= cs["w_star"].sum()
    req = urllib.request.Request(
        f"{BASE}/v2/positions",
        headers={"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                 "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]})
    poss = json.load(urllib.request.urlopen(req))
    mv = {p["symbol"]: float(p["market_value"]) for p in poss}
    acct = json.load(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/v2/account",
        headers={"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                 "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]})))
    pv = float(acct["equity"])
    cs["w_actual"] = cs["ticker"].map(mv).fillna(0.0) / pv
    tc = float(np.corrcoef(cs["w_star"], cs["w_actual"])[0, 1])
    rho_s = float(cs[["w_star", "w_actual"]].corr(method="spearman").iloc[0, 1])
    return {"run_id": latest, "n_names": int(len(cs)),
            "book_pv": round(pv, 0),
            "deployed_frac": round(float(cs["w_actual"].sum()), 3),
            "full_book_tc_pearson": round(tc, 3),
            "full_book_tc_spearman": round(rho_s, 3),
            "caveat": ("actual weights are TODAY's broker positions vs the "
                       "latest run's desired vector — a same-day pairing; "
                       "historical full-book TC becomes routine once the S5 "
                       "ledger persists per-run position values")}


def main() -> None:
    con = sqlite3.connect(DB)
    series = [r for r in (buy_side_decision_tc(con, rid) for rid in _full_runs(con))
              if r is not None]
    out = {
        "theory": "IR = TC * IC * sqrt(BR); TC = corr(w_actual, w* ∝ mu/sigma^2) "
                  "(Clarke-de Silva-Thorley 2002)",
        "buy_side_decision_tc_series": series[-10:],
        "buy_side_decision_tc_mean_recent": round(
            float(np.mean([r["buy_side_decision_tc"] for r in series[-6:]])), 3)
        if series else None,
        "full_book": full_book_tc(con),
        "state_vector_update": ("replaces the reasoned '≈0.4' in #231 §0; the "
                                "lane-A/R4 target is TC ≥ 0.6 on BOTH readouts"),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_stc_transfer_coefficient.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
