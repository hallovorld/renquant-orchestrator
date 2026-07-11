#!/usr/bin/env python3
"""Offline one-share-floor ON-vs-OFF replay over the production decision ledger.

READ-ONLY: reads a scratchpad COPY of runs.alpaca.db + the umbrella OHLCV
parquet files. Places no orders, writes only to the scratchpad.

Replays the exact A-3 rescue semantics of
renquant-pipeline/src/renquant_pipeline/kernel/pipeline/task_selection.py
(SizeAndEmitTask, floor branch at lines 571-611 + deferred pass 641-673):

  A candidate blocked at the sizing stage with `size_insufficient_cash`
  (i.e. whole-share rounding produced shares < 1) is rescued to exactly
  ONE share iff:
    (a) max_pct > 0                    (kelly_target_pct > 0 in the ledger)
    (b) override_pct is None           (no BEAR defensive slot; regime != BEAR)
    (c) price <= regime max_position_pct * PV + 1e-6   (regime cap)
    (d) price <= leftover investable = remaining_cash - reserve_pct*PV + 1e-6
  Rescues run in a DEFERRED pass, in rank order, consuming leftover cash
  only after every normal candidate has sized (n_buys tells us how many
  normal buys happened; in this window it is 0 everywhere).

Price source: daily close of the run date (intent-time quote unavailable
offline; caveat recorded in the packet).
"""
import json
import sqlite3
import sys
from collections import defaultdict

import pandas as pd

DB = "/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad/dbs/runs.alpaca.db"
OHLCV = "/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet"

# Pinned prod config (strategy-104 @ 8b2a592, verified from the live pinned
# runtime checkout): regime_params.BULL_CALM
REGIME_CAP = {"BULL_CALM": 0.12, "BULL_VOLATILE": 0.20, "CHOPPY": 0.15, "BEAR": 0.0}
RESERVE = {"BULL_CALM": 0.0, "BULL_VOLATILE": 0.2, "CHOPPY": 0.3, "BEAR": 1.0}

START = "2026-06-01"

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT pr.run_date, pr.run_id, pr.run_type, pr.regime, pr.portfolio_value,
           pr.cash, pr.n_buys, cs.ticker, cs.kelly_target_pct, cs.mu, cs.sigma,
           cs.rank_score
    FROM candidate_scores cs JOIN pipeline_runs pr ON cs.run_id = pr.run_id
    WHERE cs.blocked_by = 'size_insufficient_cash'
      AND cs.role = 'candidate'
      AND pr.run_date >= ?
    ORDER BY pr.run_date, pr.run_id, cs.rank_score DESC
    """,
    (START,),
).fetchall()

# total daily-full sessions in window for denominator
n_sessions = conn.execute(
    "SELECT COUNT(DISTINCT run_date) FROM pipeline_runs WHERE run_date >= ?",
    (START,),
).fetchone()[0]

closes = {}
def close_of(ticker, date):
    if ticker not in closes:
        df = pd.read_parquet(OHLCV.format(t=ticker))
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        closes[ticker] = df["close"]
    s = closes[ticker]
    if date in s.index:
        return float(s.loc[date]), "close(run_date)"
    prior = s[s.index <= date]
    if len(prior):
        return float(prior.iloc[-1]), f"close({prior.index[-1]}, last<=run_date)"
    return None, "missing"

by_run = defaultdict(list)
for r in rows:
    by_run[r["run_id"]].append(r)

out_runs = []
for run_id, cands in by_run.items():
    meta = cands[0]
    regime = meta["regime"]
    pv = float(meta["portfolio_value"])
    cash = float(meta["cash"])
    cap_pct = REGIME_CAP.get(regime, 0.15)
    res_pct = RESERVE.get(regime, 0.0)
    cap_dollars = cap_pct * pv
    n_buys = int(meta["n_buys"] or 0)
    leftover = max(cash - res_pct * pv, 0.0)  # n_buys==0 verified below
    rescued, dropped = [], []
    for c in cands:
        price, src = close_of(c["ticker"], c["run_date"])
        rec = {
            "ticker": c["ticker"],
            "price": price,
            "price_source": src,
            "kelly_target_pct": c["kelly_target_pct"],
            "kelly_target_usd": (c["kelly_target_pct"] or 0) * pv,
            "mu": c["mu"],
        }
        if price is None:
            rec["verdict"] = "UNPRICED (no ohlcv row)"
            dropped.append(rec)
            continue
        if not (c["kelly_target_pct"] or 0) > 0:
            rec["verdict"] = "no-rescue: max_pct == 0 (genuine zero-target)"
            dropped.append(rec)
            continue
        if regime == "BEAR":
            rec["verdict"] = "no-rescue: BEAR defensive override keeps legacy drop"
            dropped.append(rec)
            continue
        if price > cap_dollars + 1e-6:
            rec["verdict"] = (
                f"no-rescue: 1 share ${price:,.2f} > regime cap "
                f"{cap_pct:.0%}*PV = ${cap_dollars:,.2f}"
            )
            dropped.append(rec)
            continue
        if price > leftover + 1e-6:
            rec["verdict"] = f"no-rescue: 1 share > leftover investable ${leftover:,.2f}"
            dropped.append(rec)
            continue
        leftover -= price
        rec["verdict"] = "RESCUED: 1 share"
        rec["pv_pct"] = price / pv
        rescued.append(rec)
    out_runs.append(
        {
            "run_date": meta["run_date"],
            "run_id": run_id,
            "run_type": meta["run_type"],
            "regime": regime,
            "pv": pv,
            "cash": cash,
            "cash_pct": cash / pv,
            "n_buys_actual": n_buys,
            "regime_cap_usd": cap_dollars,
            "rescued": rescued,
            "not_rescued": dropped,
            "deployment_delta_usd": sum(r["price"] for r in rescued),
            "cash_pct_after": (cash - sum(r["price"] for r in rescued)) / pv,
            "max_rescue_pv_pct": max((r["pv_pct"] for r in rescued), default=0.0),
        }
    )

out_runs.sort(key=lambda r: (r["run_date"], r["run_id"]))
dates = sorted({r["run_date"] for r in out_runs})
dates_with_rescue = sorted({r["run_date"] for r in out_runs if r["rescued"]})
per_date_delta = {}
for d in dates:
    day = [r for r in out_runs if r["run_date"] == d]
    # one decision session per day: take the run with the largest delta as the
    # daily-full representative (intraday re-runs repeat the same block)
    rep = max(day, key=lambda r: r["deployment_delta_usd"])
    per_date_delta[d] = {
        "delta_usd": rep["deployment_delta_usd"],
        "rescued": [x["ticker"] for x in rep["rescued"]],
        "not_rescued": [x["ticker"] for x in rep["not_rescued"]],
        "cash_pct_before": rep["cash_pct"],
        "cash_pct_after": rep["cash_pct_after"],
        "max_rescue_pv_pct": rep["max_rescue_pv_pct"],
        "run_id": rep["run_id"],
    }

deltas = [v["delta_usd"] for v in per_date_delta.values() if v["delta_usd"] > 0]
summary = {
    "window": f"{START}..2026-07-10",
    "prod_session_dates_in_window": n_sessions,
    "dates_with_sizing_stage_zero_share_block": len(dates),
    "dates_with_at_least_one_rescue": len(dates_with_rescue),
    "distinct_rescued_tickers": sorted(
        {x["ticker"] for r in out_runs for x in r["rescued"]}
    ),
    "distinct_not_rescued": sorted(
        {x["ticker"]: x["verdict"] for r in out_runs for x in r["not_rescued"]}.items()
    ),
    "per_session_deployment_delta_usd": {
        "min": min(deltas) if deltas else 0,
        "max": max(deltas) if deltas else 0,
        "mean": sum(deltas) / len(deltas) if deltas else 0,
    },
    "normal_buys_displaced": 0 if all(r["n_buys_actual"] == 0 for r in out_runs) else "CHECK",
    "n_buys_all_zero_in_affected_runs": all(r["n_buys_actual"] == 0 for r in out_runs),
    "per_date": per_date_delta,
}

result = {"summary": summary, "runs": out_runs}
outpath = sys.argv[1] if len(sys.argv) > 1 else "/dev/stdout"
with open(outpath, "w") as f:
    json.dump(result, f, indent=1, default=str)
print(f"wrote {outpath}", file=sys.stderr)
print(json.dumps(summary, indent=1, default=str)[:4000], file=sys.stderr)
