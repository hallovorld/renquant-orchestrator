"""GOAL-2 Stage 0: the effective sample, measured BEFORE any rule is frozen.

The approved design (orch#1027) hard-codes the order of operations: assemble
the meta-panel, compute ESS first, and KILL Stage 1 if n_eff < 12 at h=60.
This script IS that computation, and its output is the kill record.

ESS definition (frozen in the design): the greedy maximal set of observation
dates spaced >= h TRADING days apart — non-overlapping label windows, the
independence floor for a 60d-forward estimand. Calendar bdays approximate the
trading calendar; exchange holidays inflate n_eff by at most ~3% and never in
the direction that would rescue a verdict.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sqlite3

import pandas as pd

CORE_LANES = ["alpaca_shadow_blend", "alpaca_shadow_blend_mom", "alpaca_shadow_blend_rb_mom"]
KILL_BAR = 12          # frozen in the approved design; not a knob
HORIZONS = [5, 10, 20, 60]


def score_dates(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return set(d for (d,) in con.execute(
        "SELECT DISTINCT r.run_date FROM candidate_scores c "
        "JOIN pipeline_runs r ON r.run_id = c.run_id "
        "WHERE c.panel_score IS NOT NULL"))


def ess(dates, h):
    idx = {d: i for i, d in enumerate(
        pd.bdate_range("2024-01-01", "2026-12-31").strftime("%Y-%m-%d"))}
    last, n = -10**9, 0
    for d in sorted(dates):
        i = idx.get(d)
        if i is not None and i - last >= h:
            n, last = n + 1, i
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True, help="directory holding runs.*.db")
    ap.add_argument("--out", default="stage0_ess.json")
    a = ap.parse_args()

    main_db = os.path.join(a.data_dir, "runs.alpaca.db")
    con = sqlite3.connect(f"file:{main_db}?mode=ro", uri=True)
    labeled = {h: set(d for (d,) in con.execute(
        f"SELECT DISTINCT as_of_date FROM ticker_forward_returns WHERE fwd_{h}d IS NOT NULL"))
        for h in HORIZONS}

    lane_dates = {}
    for p in sorted(glob.glob(os.path.join(a.data_dir, "runs.alpaca_shadow*.db"))):
        lane_dates[os.path.basename(p)[5:-3]] = score_dates(p)
    missing = [l for l in CORE_LANES if l not in lane_dates]
    if missing:
        raise SystemExit(f"FAIL CLOSED: core lane DB(s) missing: {missing}")
    multi = set.intersection(*(lane_dates[l] for l in CORE_LANES))
    hist = score_dates(main_db)

    out = {
        "kill_bar": KILL_BAR,
        "core_lanes": CORE_LANES,
        "lane_coverage": {l: {"n_dates": len(ds),
                              "range": [min(ds), max(ds)] if ds else None}
                          for l, ds in sorted(lane_dates.items())},
        "meta_panel": {"multi_leg_dates": len(multi),
                       "range": [min(multi), max(multi)] if multi else None,
                       "ess": {}},
        "historical_single_scorer_reference": {"ess": {}},
        "verdict": None,
    }
    for h in HORIZONS:
        out["meta_panel"]["ess"][f"h={h}"] = {
            "labeled_dates": len(multi & labeled[h]),
            "n_eff": ess(multi & labeled[h], h)}
        hl = hist & labeled[h]
        out["historical_single_scorer_reference"]["ess"][f"h={h}"] = {
            "labeled_dates": len(hl), "n_eff": ess(hl, h)}

    n60 = out["meta_panel"]["ess"]["h=60"]["n_eff"]
    ref60 = out["historical_single_scorer_reference"]["ess"]["h=60"]["n_eff"]
    out["verdict"] = (
        f"KILL (per the frozen design bar): meta-panel n_eff={n60} at h=60 "
        f"(< {KILL_BAR}). Best-case ceiling if all history were re-scored per "
        f"leg: {ref60} — ALSO below the bar. Stage 1 is not run."
    )
    body = json.dumps(out, indent=2, sort_keys=True)
    open(a.out, "w").write(body)
    print(body[:400], "…")
    print("sha256:", hashlib.sha256(body.encode()).hexdigest()[:16])


if __name__ == "__main__":
    main()
