"""GOAL-1 / AC1 Stage 0: what does the sizing arithmetic ADMIT at each cap?

MECHANICAL ONLY. No forward returns are read, so there is no effective-sample
problem here and no decision rule is being frozen (AC2/AC3).

It calls the PRODUCTION sizer — `renquant_pipeline.kernel.sizing.
compute_position_size`, the same function `SizeAndEmitTask` calls, with the same
`fractional` flag — rather than re-deriving the arithmetic. A second copy of a
sizing rule is exactly the twin-implementation trap this repo keeps paying for.

Read-only: opens runs.alpaca.db with mode=ro and writes nothing outside its own
output file.
"""
from __future__ import annotations

import json
import sqlite3
import statistics as st
import sys
from collections import defaultdict

DB = "file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro"
sys.path.insert(0, "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-pipeline/src")
from renquant_pipeline.kernel.sizing import compute_position_size  # noqa: E402

CAPS = [8, 10, 12, 15, 20]
MODES = [("integer", False), ("fractional", True)]


CFG = "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"


def regime_params():
    """The SERVED per-regime sizing params, read — never assumed.

    A first draft of this script hardcoded max_position_pct=0.15 /
    cash_reserve_pct=0.10 "as BULL_CALM". The served values are 0.3 and 0.0 —
    double the position size and no reserve — so every deployment figure it
    produced was understated. Load-bearing quantities get read.
    """
    with open(CFG) as fh:
        return json.load(fh)["regime_params"]


def sessions(con):
    """One row per DATE: the live run with the most candidates (the full run).

    Per run_id, never per date — there are ~35 live runs per date across lanes
    and summing them yields nonsense (held=350 on a 6-position book).
    """
    rows = con.execute("""
        SELECT run_id, run_date, portfolio_value, cash, n_candidates, regime, confidence
        FROM pipeline_runs WHERE run_type='live' AND portfolio_value IS NOT NULL
        ORDER BY run_date""").fetchall()
    best = {}
    for rid, d, pv, cash, nc, rg, cf in rows:
        if d not in best or (nc or 0) > (best[d][4] or 0):
            best[d] = (rid, d, pv, cash, nc, rg, cf)
    return [best[d] for d in sorted(best)]


def candidates(con, run_id):
    """Admissible NEW-long candidates with a price, best-scored first.

    Direction gate = panel_score > 0 AND expected_return > 0, read off the
    column the gate actually uses (`panel_score`, not `raw_score`).
    """
    return con.execute("""
        SELECT c.ticker, c.panel_score, c.expected_return, c.kelly_target_pct, f.close_price
        FROM candidate_scores c
        JOIN pipeline_runs r ON r.run_id = c.run_id
        JOIN ticker_forward_returns f ON f.ticker = c.ticker AND f.as_of_date = r.run_date
        WHERE c.run_id = ? AND c.role='candidate'
          AND c.panel_score > 0 AND c.expected_return > 0
          AND f.close_price IS NOT NULL AND f.close_price > 0
        ORDER BY c.panel_score DESC""", (run_id,)).fetchall()


def held_count(con, run_id):
    return con.execute(
        "SELECT COUNT(*) FROM candidate_scores WHERE run_id=? AND role='holding'",
        (run_id,)).fetchone()[0]


def replay(con, cap, fractional, rp):
    per_session = []
    unknown = set()
    for rid, d, pv, cash, _, regime, conf in sessions(con):
        prm = rp.get(regime or "")
        if not prm:
            unknown.add(regime); continue
        # production confidence-scales these before calling the sizer
        c = float(conf if conf is not None else 1.0)
        max_pos_pct = float(prm['max_position_pct']) * c
        reserve_pct = float(prm['cash_reserve_pct'])
        if max_pos_pct <= 0:
            continue
        cands = candidates(con, rid)
        if not cands:
            continue
        held = held_count(con, rid)
        free = max(0, cap - held)
        if free == 0:
            per_session.append(dict(date=d, free=0, filled=0, deployed=0.0,
                                    sized_in=[], sized_out=[]))
            continue
        remaining = float(cash or 0.0)
        filled, invested, sin, sout = 0, 0.0, [], []
        for tkr, ps, er, kelly, price in cands:
            if filled >= free:
                sout.append((tkr, price)); continue
            pct, shares = compute_position_size(
                portfolio_value=float(pv), available_cash=remaining,
                max_position_pct=max_pos_pct, cash_reserve_pct=reserve_pct,
                price=float(price), fractional=fractional)
            notional = float(shares) * float(price)
            if shares and notional > 0:
                filled += 1; invested += notional; remaining -= notional
                sin.append((tkr, price))
            else:
                sout.append((tkr, price))
        per_session.append(dict(date=d, free=free, filled=filled,
                                deployed=invested / float(pv) if pv else 0.0,
                                sized_in=sin, sized_out=sout))
    return per_session


def main():
    con = sqlite3.connect(DB, uri=True)
    ss = sessions(con)
    print(f"live sessions with a portfolio value: {len(ss)}  "
          f"{ss[0][1]} .. {ss[-1][1]}")
    n_with = sum(1 for r in ss if candidates(con, r[0]))
    print(f"sessions with >=1 priced admissible candidate: {n_with}\n")

    # Regime params are confidence-scaled per run in production; Stage 0 holds
    # them at the served BULL_CALM values so the CAP is the only thing varying.
    # Any conclusion here is therefore about the cap, not about sizing policy.
    rp = regime_params()
    from collections import Counter
    rc = Counter(r[5] for r in ss)
    print("regime mix across sessions:", dict(rc.most_common(4)))
    print("served params:", {k: (v.get("max_position_pct"), v.get("cash_reserve_pct"))
                             for k, v in rp.items() if k in rc})
    print("(production confidence-scales max_position_pct; this replay does the same)\n")

    hdr = f"{'cap':>4s} {'mode':>11s} {'sessions':>8s} {'med_filled':>10s} {'med_deployed':>12s} {'med_px_in':>9s} {'med_px_out':>10s} {'tilt':>5s}"
    print(hdr); print("-" * len(hdr))
    out = {}
    for cap in CAPS:
        for name, frac in MODES:
            rs = replay(con, cap, frac, rp)
            rs = [r for r in rs if r["free"] > 0]
            if not rs:
                continue
            med_filled = st.median(r["filled"] for r in rs)
            med_dep = st.median(r["deployed"] for r in rs)
            pin = [p for r in rs for _, p in r["sized_in"]]
            pout = [p for r in rs for _, p in r["sized_out"]]
            mi = st.median(pin) if pin else float("nan")
            mo = st.median(pout) if pout else float("nan")
            tilt = (mo / mi) if pin and mi else float("nan")
            print(f"{cap:4d} {name:>11s} {len(rs):8d} {med_filled:10.1f} "
                  f"{med_dep:11.1%} {mi:9.2f} {mo:10.2f} {tilt:5.2f}x")
            out[f"{cap}_{name}"] = dict(sessions=len(rs), med_filled=med_filled,
                                        med_deployed=med_dep, med_price_in=mi,
                                        med_price_out=mo, tilt=tilt,
                                        n_in=len(pin), n_out=len(pout))
    with open("stage0_capacity.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote stage0_capacity.json")


if __name__ == "__main__":
    main()
