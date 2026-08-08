"""BEAR exit-side prereg — reachability measurement, verifier + derivation.

Supports doc/design/2026-08-08-bear-exit-prereg.md §1: why the active exit
`CrossSectionalPanelExitTask` produced zero fires over the last 60 live days.

DEFAULT (verify): recompute every reachability number quoted in the design +
progress docs from the committed CSV alone —
`2026-08-08-bear-exit-reachability-rows.csv`, beside this file. No DB, no
scratch inputs, no network. Exits non-zero if any recomputed number differs
from the frozen expected value.

--derive: rebuild the CSV from the machine-local live runs DB
(`RenQuant/data/runs.alpaca.db`, deliberately not committed). Refuses with a
clear message when the DB is absent.

Frozen measurement definition (matches the production trigger arithmetic in
renquant-pipeline/src/renquant_pipeline/kernel/pipeline/task_panel_conviction_xs.py
::CrossSectionalPanelExitTask.run):

* window: the last 60 distinct `run_type='live'` run_dates in
  `pipeline_runs` at derivation time (2026-08-08 run: 2026-05-15..2026-08-07);
* best run per day: the day's run with the most candidate-role rows in
  `candidate_scores` (tie-break: latest `created_at`) — sell-only intraday
  ticks carry no candidate cross-section;
* cross-section: ALL finite `panel_score` rows of that run (candidates +
  holdings), exactly as the task builds `all_scores`;
* day kept iff cross-section >= min_universe AND >= 1 holding row with finite
  panel_score and mu;
* per holding row: xsec_pct = fraction of the cross-section <= the holding's
  panel_score; threshold replay = sorted[clamp(round(n*pct_floor))]; legs:
  panel_score <= threshold (xs leg), mu <= mu_ceiling (mu leg), AND-rule =
  both, strong-mu bypass = mu <= mu_strong.

Production knobs frozen from the pinned config
(renquant-strategy-104/configs/strategy_config.json :: risk.panel_exit):
pct_floor=0.20, mu_ceiling=0.0, mu_strong=-0.05, min_universe=5.
"""
from __future__ import annotations

import csv
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
CSV = HERE / "2026-08-08-bear-exit-reachability-rows.csv"
DB = Path("/Users/renhao/git/github/RenQuant/data/runs.alpaca.db")

PCT_FLOOR = 0.20
MU_CEILING = 0.0
MU_STRONG = -0.05
MIN_UNIVERSE = 5
WINDOW_DAYS = 60

# Frozen expected values (2026-08-08 derivation; quoted in the design doc §1).
EXPECTED = {
    "days_kept": 43,
    "rows": 200,
    "pct_median": 0.8907,
    "pct_min": 0.2,
    "mu_median": 0.0351,
    "xs_leg_rows": 7,
    "mu_leg_rows": 1,
    "and_fires": 0,
    "strong_fires": 0,
}

FIELDS = [
    "run_date", "run_id", "ticker", "panel_score", "mu",
    "xsec_n", "xsec_pct", "xs_leg", "mu_leg", "and_fires", "strong_fires",
]


def _summarize(rows: list[dict]) -> dict:
    pcts = [float(r["xsec_pct"]) for r in rows]
    mus = [float(r["mu"]) for r in rows]
    return {
        "days_kept": len({r["run_date"] for r in rows}),
        "rows": len(rows),
        "pct_median": round(statistics.median(pcts), 4),
        "pct_min": round(min(pcts), 4),
        "mu_median": round(statistics.median(mus), 4),
        "xs_leg_rows": sum(int(r["xs_leg"]) for r in rows),
        "mu_leg_rows": sum(int(r["mu_leg"]) for r in rows),
        "and_fires": sum(int(r["and_fires"]) for r in rows),
        "strong_fires": sum(int(r["strong_fires"]) for r in rows),
    }


def verify() -> int:
    with open(CSV, newline="") as fh:
        rows = list(csv.DictReader(fh))
    got = _summarize(rows)
    ok = True
    print(f"== reachability verify from {CSV.name} ==")
    for key, want in EXPECTED.items():
        match = got[key] == want
        ok &= match
        print(f"  {key:14s} got={got[key]:<10} expected={want:<10} "
              f"{'OK' if match else 'MISMATCH'}")
    print("VERDICT:", "REPRODUCED" if ok else "MISMATCH")
    return 0 if ok else 1


def derive() -> int:
    if not DB.exists():
        print(f"--derive needs the machine-local live runs DB at {DB} "
              "(deliberately not committed). Run on the workstation, or use "
              "the default verify mode against the committed CSV.")
        return 2
    import sqlite3

    con = sqlite3.connect(DB)
    cur = con.cursor()
    dates = [r[0] for r in cur.execute(
        "SELECT DISTINCT run_date FROM pipeline_runs WHERE run_type='live' "
        "ORDER BY run_date DESC LIMIT ?", (WINDOW_DAYS,))]
    out: list[dict] = []
    for day in sorted(dates):
        best = cur.execute(
            "SELECT p.run_id, COUNT(CASE WHEN c.role='candidate' THEN 1 END) nc "
            "FROM pipeline_runs p LEFT JOIN candidate_scores c ON c.run_id=p.run_id "
            "WHERE p.run_type='live' AND p.run_date=? "
            "GROUP BY p.run_id ORDER BY nc DESC, p.created_at DESC LIMIT 1",
            (day,)).fetchone()
        if not best:
            continue
        run_id = best[0]
        cs = cur.execute(
            "SELECT ticker, role, panel_score, mu FROM candidate_scores "
            "WHERE run_id=?", (run_id,)).fetchall()
        xsec = [float(p) for (_, _, p, _) in cs
                if p is not None and math.isfinite(float(p))]
        if len(xsec) < MIN_UNIVERSE:
            continue
        srt = sorted(xsec)
        n = len(srt)
        idx = max(0, min(int(round(n * PCT_FLOOR)), n - 1))
        threshold = srt[idx]
        for ticker, role, p, m in cs:
            if role != "holding" or p is None or m is None:
                continue
            p, m = float(p), float(m)
            if not (math.isfinite(p) and math.isfinite(m)):
                continue
            xs_leg = p <= threshold
            mu_leg = m <= MU_CEILING
            out.append({
                "run_date": day, "run_id": run_id, "ticker": ticker,
                "panel_score": p, "mu": m, "xsec_n": n,
                "xsec_pct": round(sum(1 for s in srt if s <= p) / n, 6),
                "xs_leg": int(xs_leg), "mu_leg": int(mu_leg),
                "and_fires": int(xs_leg and mu_leg),
                "strong_fires": int(m <= MU_STRONG),
            })
    with open(CSV, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out)
    print(f"wrote {len(out)} rows -> {CSV}")
    got = _summarize(out)
    for key, val in got.items():
        print(f"  {key:14s} {val}")
    return 0


if __name__ == "__main__":
    sys.exit(derive() if "--derive" in sys.argv[1:] else verify())
