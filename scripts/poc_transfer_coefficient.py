#!/usr/bin/env python3
"""S-TC: measure the transfer coefficient — an EXPLORATORY diagnostic for the
last reasoned-tier number in the #231 §0 state vector (asserted ≈0.4; solver
default λ etc. untouched).

Theory (Clarke–de Silva–Thorley 2002): IR = TC × IC × √BR with
TC = cross-sectional correlation between the ACTUAL active weights and the
UNCONSTRAINED risk-adjusted desired weights (w* ∝ μ/σ² — here the model's own
`kelly_target_pct`, which is exactly that quantity before the constraint stack).

2026-07-02 ROUND 2 (Codex CHANGES_REQUESTED — 5 methodology gaps, all closed
here; see doc/progress/2026-07-02-s-tc-measurement.md for the full response
map). Every number in this script's output is now labelled EXPLORATORY /
DIAGNOSTIC, not measured-tier TC and not a justification for any lane/route
decision, until the fixes below are themselves validated against more data:

  1. Full-book pairing is cross-day (today's live broker positions vs the
     LATEST run's desired vector, not a genuine same-timestamp snapshot) —
     now explicitly flagged `same_day_aligned: false` with a corrected
     caveat (the prior caveat text wrongly called this "a same-day
     pairing").
  2. Buy-side eligibility (`role=candidate AND mu>=floor`) previously mapped
     every non-buy to a target of 0 and correlated the whole eligible set —
     conflating ADMISSION effects (regime/QP/rank-floor vetoes recorded in
     `candidate_scores.blocked_by`) with SIZING transfer. Now split: an
     admission-stage breakdown (counts by `blocked_by` reason) is reported
     separately from a sizing-stage TC computed ONLY over names that
     survived every admission gate (`blocked_by IS NULL`).
  3. Runs with zero buys, or where every survivor was bought at the SAME
     target_pct (Pearson TC mathematically undefined — zero variance), no
     longer report `0.0` interchangeably with a genuine near-zero
     correlation. Each run's `category` is one of `no_deployment` (zero
     buys), `zero_dispersion` (bought, but no size variation — a real,
     separately-interesting finding, e.g. a uniform per-name sizing rule),
     or `measured` (a genuine Pearson correlation). Only `measured` runs
     enter the correlation series/mean.
  4. `_canonical_daily_runs` now selects exactly one `pipeline_runs` row per
     `run_date` (the row with the latest `created_at` — i.e. the last
     completed run that day), instead of the raw run list, which had TWO
     entries on 2026-06-09 and an arbitrary `series[-6:]` "recent" slice.
     The mean is now reported with its sample size AND a standard error
     (only over genuinely independent `measured`-category days), not a bare
     unweighted mean over however many happened to be in the last 6 rows.
  5. Pearson/Spearman correlation is scale-invariant — it cannot see a
     uniform shrinkage in DEPLOYED MAGNITUDE (only in relative ordering).
     Added `exposure_transfer_ratio` — an un-normalized projection of
     w_actual onto w* (regression-through-origin slope,
     dot(w_actual, w_star) / dot(w_star, w_star)) — which DOES scale
     linearly with deployed magnitude: if w_actual is a uniformly
     shrunk-by-k copy of w_star's direction, this ratio is ~k, unlike
     Pearson/cosine which would both read ~1.0. Reported alongside, never
     instead of, the correlation-based TC. This system tracks no external
     index benchmark (cash is the only "benchmark" — 0% weight), so
     "active weight" here is the raw weight itself; this is stated
     explicitly rather than assuming a benchmark that does not exist in
     this codebase.

Two measurements, honestly scoped until the S5 ledger makes full historical
book-TC routine:

  (1) FULL-BOOK TC (latest run only): actual weights from the broker's live
      positions (read-only GET /v2/positions) + cash, vs w* from the latest
      daily full run's candidate_scores (candidates AND holdings). One
      number, descriptive only (cross-day pairing — see point 1 above).
  (2) BUY-SIDE DECISION-TC (per canonical daily full run): among
      admission-surviving candidates (μ ≥ 0.03 AND blocked_by IS NULL),
      corr between desired kelly_target_pct and the ACTUAL emitted buy
      target_pct (0 if not bought). Measures how much of the desired
      NEW-money allocation survives top_n / whole-share / cash / shrinkage
      — for the population that was never blocked upstream in the first
      place.

Reproduce:
  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a && \
    .venv/bin/python <orchestrator>/scripts/poc_transfer_coefficient.py
Inputs (read-only): data/runs.alpaca.db; Alpaca /v2/positions.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json
"""
from __future__ import annotations

import json
import math
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
MIN_FULL_RUN_CANDIDATES = 80


def _canonical_daily_runs(con) -> list[str]:
    """One `pipeline_runs` row per `run_date` — the row with the LATEST
    `created_at` that day (the last completed run supersedes an earlier
    same-day attempt) — restricted to "full" runs (>= MIN_FULL_RUN_CANDIDATES
    candidate_scores rows). ROUND 2 fix (point 4): the prior version used
    every raw run_id, including two same-day entries on 2026-06-09, and an
    unweighted "last 6" slice with no independence guarantee.
    """
    counts = pd.read_sql(
        "select run_id, count(*) n from candidate_scores "
        "where run_id like '%-live-%' group by run_id "
        f"having n >= {MIN_FULL_RUN_CANDIDATES}", con)
    if counts.empty:
        return []
    runs = pd.read_sql(
        "select run_id, run_date, created_at from pipeline_runs "
        "where run_id in ({})".format(",".join("?" * len(counts))),
        con, params=counts["run_id"].tolist())
    runs = runs.merge(counts, on="run_id")
    runs["created_at"] = pd.to_datetime(runs["created_at"])
    # one row per run_date: the max created_at (last completed that day)
    idx = runs.groupby("run_date")["created_at"].idxmax()
    canonical = runs.loc[idx].sort_values("run_date")
    return canonical["run_id"].tolist()


def buy_side_decision_tc(con, run_id: str) -> dict | None:
    cs = pd.read_sql(
        "select ticker, role, mu, kelly_target_pct, blocked_by "
        "from candidate_scores where run_id=? and role='candidate'",
        con, params=(run_id,))
    elig = cs[(cs["mu"] >= MU_FLOOR) & cs["kelly_target_pct"].notna()].copy()
    if len(elig) < 4:
        return None

    # ROUND 2 fix (point 2): split ADMISSION (blocked_by) from SIZING.
    # blocked_by is NULL/empty for names that survived every upstream gate
    # (regime / QP admission / rank floor / etc.) and reached sizing.
    blocked_mask = elig["blocked_by"].notna() & (elig["blocked_by"].str.len() > 0)
    admission_breakdown = (
        elig.loc[blocked_mask, "blocked_by"].value_counts().to_dict()
    )
    survived = elig.loc[~blocked_mask].copy()
    n_survived_admission = int(len(survived))
    admission_breakdown["survived_admission"] = n_survived_admission

    if n_survived_admission < 4:
        return {
            "run_id": run_id,
            "n_eligible_by_mu": int(len(elig)),
            "admission_breakdown": admission_breakdown,
            "n_survived_admission": n_survived_admission,
            "category": "insufficient_sizing_population",
            "buy_side_decision_tc": None,
            "exposure_transfer_ratio": None,
        }

    tr = pd.read_sql(
        "select ticker, target_pct from trades where run_id=? and action like 'buy%'",
        con, params=(run_id,))
    actual = dict(zip(tr["ticker"], tr["target_pct"]))
    survived["w_actual"] = survived["ticker"].map(actual).fillna(0.0)
    n_bought = int((survived["w_actual"] > 0).sum())

    # ROUND 2 fix (point 3): distinguish "genuinely undefined correlation"
    # cases from a real, computed near-zero correlation, and NEVER average
    # an undefined case into the correlation series.
    if n_bought == 0:
        category = "no_deployment"
        tc_p = None
    elif survived["w_actual"].std() == 0 or survived["kelly_target_pct"].std() == 0:
        category = "zero_dispersion"  # bought, but no size variation to correlate
        tc_p = None
    else:
        category = "measured"
        tc_p = float(np.corrcoef(survived["kelly_target_pct"], survived["w_actual"])[0, 1])

    # ROUND 2 fix (point 5): a magnitude-sensitive companion metric —
    # regression-through-origin slope of actual onto desired. Computable
    # whenever the desired vector has any dispersion, independent of
    # whether w_actual has dispersion (unlike Pearson TC above).
    denom = float(np.dot(survived["kelly_target_pct"], survived["kelly_target_pct"]))
    exposure_transfer_ratio = (
        round(float(np.dot(survived["w_actual"], survived["kelly_target_pct"])) / denom, 3)
        if denom > 0 else None
    )

    return {
        "run_id": run_id,
        "n_eligible_by_mu": int(len(elig)),
        "admission_breakdown": admission_breakdown,
        "n_survived_admission": n_survived_admission,
        "n_bought": n_bought,
        "category": category,
        "buy_side_decision_tc": round(tc_p, 3) if tc_p is not None else None,
        "exposure_transfer_ratio": exposure_transfer_ratio,
    }


def full_book_tc(con) -> dict:
    canonical = _canonical_daily_runs(con)
    latest = canonical[-1]
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
    star_dot = float(np.dot(cs["w_star"], cs["w_star"]))
    exposure_transfer_ratio = (
        round(float(np.dot(cs["w_actual"], cs["w_star"])) / star_dot, 3)
        if star_dot > 0 else None
    )
    return {
        "run_id": latest,
        "n_names": int(len(cs)),
        "book_pv": round(pv, 0),
        "deployed_frac": round(float(cs["w_actual"].sum()), 3),
        "full_book_tc_pearson": round(tc, 3),
        "full_book_tc_spearman": round(rho_s, 3),
        "exposure_transfer_ratio": exposure_transfer_ratio,
        # ROUND 2 fix (point 1): this pairing is NOT same-day — w* comes
        # from `latest`'s recorded run, w_actual is queried live at
        # whatever moment this script executes (which may be a later
        # calendar day). No point-in-time position snapshot exists yet
        # (tracked as future S5-ledger work) to make this a true same-day
        # measurement, so it is explicitly flagged as descriptive-only.
        "same_day_aligned": False,
        "caveat": ("actual weights are queried LIVE at script-execution time, "
                   "vs the desired vector from the LATEST recorded run "
                   f"({latest}) — these are NOT guaranteed to be the same "
                   "calendar day (same_day_aligned=false: this is a "
                   "cross-day, descriptive pairing, not a measured "
                   "same-timestamp TC). Historical, point-in-time-aligned "
                   "full-book TC becomes possible once the S5 ledger "
                   "persists per-run position values."),
    }


def main() -> None:
    con = sqlite3.connect(DB)
    canonical_runs = _canonical_daily_runs(con)
    all_results = [buy_side_decision_tc(con, rid) for rid in canonical_runs]
    all_results = [r for r in all_results if r is not None]
    measured = [r for r in all_results if r["category"] == "measured"]
    tc_values = [r["buy_side_decision_tc"] for r in measured]
    n_measured = len(tc_values)
    mean_tc = float(np.mean(tc_values)) if n_measured else None
    # standard error only meaningful for n>=2; report explicitly small-n
    # otherwise rather than a misleadingly precise number.
    se_tc = (
        float(np.std(tc_values, ddof=1) / math.sqrt(n_measured))
        if n_measured >= 2 else None
    )

    category_counts = {
        cat: sum(1 for r in all_results if r["category"] == cat)
        for cat in ("measured", "no_deployment", "zero_dispersion",
                    "insufficient_sizing_population")
    }

    out = {
        "label": "EXPLORATORY DIAGNOSTIC — not measured-tier TC; see round-2 "
                 "response map in doc/progress/2026-07-02-s-tc-measurement.md "
                 "before citing any number below as a decision input",
        "theory": "IR = TC * IC * sqrt(BR); TC = corr(w_actual, w* ∝ mu/sigma^2) "
                  "(Clarke-de Silva-Thorley 2002)",
        "n_canonical_daily_runs_considered": len(canonical_runs),
        "buy_side_decision_tc_series": all_results,
        "buy_side_decision_tc_category_counts": category_counts,
        "buy_side_decision_tc_mean_measured_only": (
            round(mean_tc, 3) if mean_tc is not None else None
        ),
        "buy_side_decision_tc_n_measured": n_measured,
        "buy_side_decision_tc_se_measured": (
            round(se_tc, 3) if se_tc is not None else
            ("undefined (n<2)" if n_measured < 2 else None)
        ),
        "full_book": full_book_tc(con),
        "state_vector_update": (
            "EXPLORATORY diagnostic input candidate for the reasoned '≈0.4' "
            "in #231 §0 — NOT a validated replacement and NOT, by itself, "
            "justification for any lane/route decision (small, "
            "non-independent-until-now sample; admission/sizing effects "
            "were conflated until this round; see the progress doc's "
            "round-2 section for the full caveat list)."
        ),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_stc_transfer_coefficient.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
