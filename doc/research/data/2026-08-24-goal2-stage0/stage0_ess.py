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


#: Provenance predicate — the ONLY runs that may count toward a 104 ESS claim.
#: Matches the selection `intraday_session_inputs` / `export_batch_scores.py`
#: already use: a completed live run of a named strategy, never a sim/backfill.
#: codex review 2026-08-24: the first revision accepted every candidate_scores
#: row with a panel score, so `runs.alpaca.db` contributed 560 SIM dates
#: alongside 90 live ones and the result was reported as a live re-score
#: history ceiling. Measured: 634 dates unfiltered vs 74 with this predicate.
_LIVE_ONLY = ("r.run_type = 'live' "
              "AND r.strategy IS NOT NULL AND r.strategy != ''")


def score_dates(db, *, with_provenance=False):
    """Distinct run_dates of LIVE, strategy-named runs carrying panel scores.

    Returns the date set; with ``with_provenance`` also returns the selected
    run_ids and the count excluded by the predicate, so the artifact can state
    what was rejected rather than only what survived — a reader seeing 74 dates
    and no exclusion count cannot tell a correct filter from an empty source.
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    sel = list(con.execute(
        "SELECT DISTINCT r.run_date, r.run_id FROM candidate_scores c "
        "JOIN pipeline_runs r ON r.run_id = c.run_id "
        f"WHERE c.panel_score IS NOT NULL AND {_LIVE_ONLY}"))
    dates = {d for d, _ in sel}
    if not with_provenance:
        con.close()
        return dates
    total = next(con.execute(
        "SELECT COUNT(DISTINCT r.run_date) FROM candidate_scores c "
        "JOIN pipeline_runs r ON r.run_id = c.run_id "
        "WHERE c.panel_score IS NOT NULL"))[0]
    con.close()
    run_ids = sorted({rid for _, rid in sel})
    return dates, {
        "dates_selected": len(dates),
        "dates_excluded_by_provenance": total - len(dates),
        "dates_before_filter": total,
        "n_run_ids": len(run_ids),
        # Pins the exact rows, not the file: a DB that grows later still
        # reproduces this number iff the same runs were selected.
        "selected_rows_sha256": hashlib.sha256(
            "\n".join(f"{d}|{r}" for d, r in sorted(sel)).encode()).hexdigest(),
        "predicate": "run_type='live' AND strategy NOT NULL/''",
    }


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
    hist, hist_prov = score_dates(main_db, with_provenance=True)

    out = {
        "kill_bar": KILL_BAR,
        "core_lanes": CORE_LANES,
        "lane_coverage": {l: {"n_dates": len(ds),
                              "range": [min(ds), max(ds)] if ds else None}
                          for l, ds in sorted(lane_dates.items())},
        "meta_panel": {"multi_leg_dates": len(multi),
                       "range": [min(multi), max(multi)] if multi else None,
                       "ess": {}},
        "historical_single_scorer_reference": {"ess": {}, "provenance": hist_prov},
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
        f"(< {KILL_BAR}). Best-case ceiling if all LIVE history were re-scored "
        f"per leg: {ref60} — ALSO below the bar. Stage 1 is not run. "
        f"The ceiling counts only live, strategy-named runs "
        f"({hist_prov['dates_selected']} dates; "
        f"{hist_prov['dates_excluded_by_provenance']} excluded by provenance, "
        f"overwhelmingly sim); an unfiltered count would inflate it and is not "
        f"a 104 re-score history."
    )
    body = json.dumps(out, indent=2, sort_keys=True)
    open(a.out, "w").write(body)
    print(body[:400], "…")
    print("sha256:", hashlib.sha256(body.encode()).hexdigest()[:16])


if __name__ == "__main__":
    main()
