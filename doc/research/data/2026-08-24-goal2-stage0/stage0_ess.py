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


#: The EXACT strategy this ESS claim is about. Not "any named strategy" —
#: these DBs are shared, so a non-empty `strategy` proves only that SOMETHING
#: was named (codex review round 2). Verified present and uniform across every
#: lane DB before pinning it.
EXPECTED_STRATEGY = "renquant-104"

#: Provenance predicate — the ONLY runs that may count toward a 104 ESS claim.
#: Matches the selection `intraday_session_inputs` / `export_batch_scores.py`
#: already use: a completed live run of THIS strategy, never a sim/backfill.
#: Round 1 accepted every candidate_scores row with a panel score, so
#: `runs.alpaca.db` contributed 560 SIM dates alongside 90 live ones and the
#: result was reported as a live re-score history ceiling.
_LIVE_ONLY = "r.run_type = 'live' AND r.strategy = ?"


def _assert_no_foreign_strategy(con, db):
    """Fail closed if the DB carries any strategy other than the expected one.

    Filtering TO a value silently tolerates a DB that has quietly become
    multi-strategy; asserting that no OTHER value exists turns that into a
    stop. The two are not the same check and only the second notices drift.
    """
    others = sorted({(s or "") for (s,) in con.execute(
        "SELECT DISTINCT strategy FROM pipeline_runs WHERE run_type = 'live'")
        } - {EXPECTED_STRATEGY})
    if others:
        raise SystemExit(
            f"FAIL CLOSED: {db} has live runs for unexpected strategies "
            f"{others} — an ESS claim scoped to {EXPECTED_STRATEGY!r} cannot be "
            f"made from a DB whose lane membership is ambiguous.")


def score_dates(db, *, with_provenance=False):
    """Distinct run_dates of LIVE, strategy-named runs carrying panel scores.

    Returns the date set; with ``with_provenance`` also returns the selected
    run_ids and the count excluded by the predicate, so the artifact can state
    what was rejected rather than only what survived — a reader seeing 74 dates
    and no exclusion count cannot tell a correct filter from an empty source.
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    _assert_no_foreign_strategy(con, db)
    # Every field the INCLUSION decision depends on is selected, because the
    # digest below must cover all of them (codex review round 2): hashing only
    # (run_date, run_id) leaves run_type, strategy and panel-score presence
    # free to change while the digest stays put — a digest whose subject is
    # narrower than the predicate it claims to pin.
    sel = list(con.execute(
        "SELECT DISTINCT r.run_date, r.run_id, r.run_type, r.strategy, "
        "  CASE WHEN c.panel_score IS NOT NULL THEN 1 ELSE 0 END AS has_score "
        "FROM candidate_scores c "
        "JOIN pipeline_runs r ON r.run_id = c.run_id "
        f"WHERE c.panel_score IS NOT NULL AND {_LIVE_ONLY}",
        (EXPECTED_STRATEGY,)))
    dates = {row[0] for row in sel}
    if not with_provenance:
        con.close()
        return dates
    total = next(con.execute(
        "SELECT COUNT(DISTINCT r.run_date) FROM candidate_scores c "
        "JOIN pipeline_runs r ON r.run_id = c.run_id "
        "WHERE c.panel_score IS NOT NULL"))[0]
    con.close()
    run_ids = sorted({row[1] for row in sel})
    return dates, {
        "dates_selected": len(dates),
        "dates_excluded_by_provenance": total - len(dates),
        "dates_before_filter": total,
        "n_run_ids": len(run_ids),
        "run_ids": run_ids,
        # Covers EVERY inclusion-determining field, not just row identity, so
        # a run flipping run_type or losing its panel scores changes the digest.
        "selection_sha256": hashlib.sha256(
            "\n".join("|".join(str(v) for v in row)
                       for row in sorted(sel)).encode()).hexdigest(),
        "digest_covers": ["run_date", "run_id", "run_type", "strategy",
                          "panel_score_present"],
        "predicate": f"run_type='live' AND strategy='{EXPECTED_STRATEGY}' "
                     f"AND candidate_scores.panel_score IS NOT NULL",
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
    # LABEL AVAILABILITY IS ALSO AN INCLUSION INPUT (codex review round 3).
    # Every reported ESS is computed over `dates & labeled[h]`, so the label
    # side determines the number exactly as much as the run selection does.
    # Round 2 pinned the runs and left this unpinned: `ticker_forward_returns`
    # can be backfilled or corrected, moving labeled_dates and n_eff while
    # every selection_sha256 stays identical. Digest it per horizon, so a
    # label backfill is visible as a changed fingerprint rather than as a
    # silently different answer.
    labeled, label_prov = {}, {}
    for h in HORIZONS:
        rows = sorted(d for (d,) in con.execute(
            f"SELECT DISTINCT as_of_date FROM ticker_forward_returns "
            f"WHERE fwd_{h}d IS NOT NULL"))
        labeled[h] = set(rows)
        label_prov[f"h={h}"] = {
            "n_label_dates": len(rows),
            "range": [rows[0], rows[-1]] if rows else None,
            "field": f"fwd_{h}d IS NOT NULL",
            "labeled_dates_sha256": hashlib.sha256(
                "\n".join(rows).encode()).hexdigest(),
        }

    # LANE IDENTITY IS OUT-OF-BAND, and this says so rather than implying
    # otherwise (codex review round 2). Verified against the schema: for the
    # DB file
    #   pipeline_runs(run_id, run_date, run_type, strategy, regime, confidence,
    #     portfolio_value, cash, n_candidates, n_exits, n_rotations, n_buys,
    #     buy_blocked, skip_buys, bear_only, counters_json, run_bundle_json,
    #     commit_sha, training_cutoff, model_content_sha256, created_at)
    # there is NO lane/tag/variant column, and `model_content_sha256` does not
    # separate lanes either — one sha (c816b…) is shared by SEVEN lane DBs,
    # because lanes differ by CONFIG (which legs blend), not by artifact. So
    # the file path is the only lane signal that exists, and the honest
    # response is to constrain it and record what it selected, not to dress it
    # up as in-band provenance.
    lane_dates, lane_prov = {}, {}
    for lane in CORE_LANES:
        path = os.path.join(a.data_dir, f"runs.{lane}.db")
        if not os.path.exists(path):
            raise SystemExit(f"FAIL CLOSED: core lane DB missing: {path}")
        lane_dates[lane], lane_prov[lane] = score_dates(path, with_provenance=True)
    # An UNEXPECTED shadow DB is RECORDED, not a stop — and the comment now
    # says what the code does (codex review round 3: the previous wording
    # claimed a stop while the code continued, which is an assertion the
    # implementation did not carry). Continuing is right: the frozen design
    # names the three core lanes, so the meta-panel intersection is defined
    # over CORE_LANES regardless of what else exists on disk. Recording the
    # extras is what keeps a corpus that quietly grew a lane visible in the
    # artifact instead of invisible.
    on_disk = {os.path.basename(x)[5:-3]
               for x in glob.glob(os.path.join(a.data_dir, "runs.alpaca_shadow*.db"))}
    unexpected = sorted(on_disk - set(CORE_LANES))
    context_only = {l: len(score_dates(os.path.join(a.data_dir, f"runs.{l}.db")))
                    for l in unexpected}
    multi = set.intersection(*(lane_dates[l] for l in CORE_LANES))
    hist, hist_prov = score_dates(main_db, with_provenance=True)

    out = {
        "kill_bar": KILL_BAR,
        "core_lanes": CORE_LANES,
        "lane_identity": {
            "source": "DB FILE PATH — pipeline_runs has no lane/tag column, "
                      "and model_content_sha256 is shared across lanes "
                      "(one sha spans 7 lane DBs), so no in-band lane "
                      "identity exists in this schema",
            "core_lanes_required": CORE_LANES,
            "other_shadow_dbs_present": context_only,
        },
        "lane_coverage": {l: {"n_dates": len(ds),
                              "range": [min(ds), max(ds)] if ds else None,
                              "provenance": lane_prov[l]}
                          for l, ds in sorted(lane_dates.items())},
        "meta_panel": {"multi_leg_dates": len(multi),
                       "range": [min(multi), max(multi)] if multi else None,
                       "ess": {}},
        "historical_single_scorer_reference": {"ess": {}, "provenance": hist_prov},
        # The other half of every ESS: which dates carry a realized label.
        "label_availability": {
            "source": f"{os.path.basename(main_db)}::ticker_forward_returns",
            "note": "ESS = |selected_dates & labeled_dates|, so a backfill here "
                    "moves n_eff without touching any selection digest — "
                    "digested per horizon for that reason",
            "per_horizon": label_prov,
        },
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
