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

2026-07-02 ROUND 3 (Codex CHANGES_REQUESTED — round 2's admission/sizing
split itself misclassified `blocked_by`, producing an UNSUPPORTED "100%
blocked before sizing" finding on every one of the 10 canonical daily runs;
see doc/progress/2026-07-02-s-tc-measurement.md round-3 section for the full
response map):

  `blocked_by IS NULL` does NOT mean "survived admission" — it means "not
  yet given ANY reason." Round 2 treated every non-null `blocked_by` as a
  pre-selection admission failure, but `blocked_by` is also the field that
  records SIZING-stage failures and even genuinely SELECTED/SUBMITTED
  outcomes (e.g. `broker_pending_submitted` — a name whose order WAS
  submitted to the broker but whose fill wasn't confirmed at trace-snapshot
  time; see `RenQuant/backtesting/renquant_104/adapters/runner_trace.py`
  `live_trace_selection_maps()`: "Trace filled buys as selected and pending
  submissions as blocked."). Treating that the same as a true pre-selection
  veto forced n_survived_admission=0 on every run — a classification bug,
  not a real finding.

  Fixed: an explicit taxonomy (`_REASON_TAXONOMY` below), derived directly
  from the actual writer code (`renquant-pipeline`'s
  `kernel/selection.py::run_selection_loop` — the true pre-selection greedy
  slot-filling loop — and `kernel/pipeline/task_selection.py::SizeAndEmitTask`
  — the sizing stage that runs strictly AFTER selection succeeds — plus
  RenQuant's `adapters/runner_trace.py` for the live broker-submission
  sweep), not guessed from the string values alone:
    - PRE_SELECTION_BLOCKERS (never reached sizing):
      wash_sale, sector, correlation, tier, defensive_non_bear,
      candidate_not_selected (generic no-specific-reason fallback).
    - SIZING_FAILURES (selected, but sizing failed to produce an order):
      buy_blocked, skip_buys, size_bad_price, size_insufficient_cash,
      size_cash_invariant, kelly_zero:capped_zero, bear_defensive_slot_cap,
      bear_defensive_insufficient_cash.
    - SELECTED_SUBMITTED (selected AND submitted — NOT a blocker; fill
      confirmation status unknown at trace time): broker_pending_submitted.
    - BROKER_OUTCOME (selected, submitted, then skipped at/after broker
      submission): broker_skip:* (prefix).
    - UNCLASSIFIED: any other value — reported in its own bucket, never
      force-fit into pre-selection/sizing, per the review's explicit ask.

  `n_survived_admission` (the sizing population) is now every eligible name
  EXCEPT true PRE_SELECTION_BLOCKERS and UNCLASSIFIED (conservatively
  excluded from both sides pending a real explanation). SELECTED_SUBMITTED
  rows with no matching row in `trades` (fill unconfirmed) are counted in
  the sizing population but EXCLUDED from the correlation itself — their
  true delivered weight is unknown, not zero, and folding an unknown into
  0.0 would be exactly the "undefined treated as a known value" error round
  2 already fixed for the no-buy/zero-dispersion cases (see point 3 above).
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

# ROUND 3 taxonomy — derived from the actual writer code, not guessed:
#   renquant-pipeline/src/renquant_pipeline/kernel/selection.py
#     run_selection_loop(): block_counts keys "wash_sale", "sector",
#     "correlation", "tier", "defensive_non_bear" — the greedy slot-filling
#     loop that runs BEFORE sizing. `candidate_not_selected` is
#     persistence.py's generic fallback when no specific reason was ever
#     recorded (e.g. ran off the end of the ranked list before a slot
#     opened) — also a true pre-selection non-event.
#   renquant-pipeline/src/renquant_pipeline/kernel/pipeline/task_selection.py
#     SizeAndEmitTask._block(): "buy_blocked", "skip_buys", "size_bad_price",
#     "size_insufficient_cash", "size_cash_invariant",
#     "kelly_zero:capped_zero", "bear_defensive_slot_cap",
#     "bear_defensive_insufficient_cash" — this task only runs on names
#     already in ctx._selected, so every reason it stamps is a SIZING
#     failure, not an admission failure.
#   RenQuant/backtesting/renquant_104/adapters/runner_trace.py
#     live_trace_selection_maps(): pending (submitted, unconfirmed-fill)
#     broker orders are swept into the SAME blocked_map via
#     `out_blocked.setdefault(ticker, "broker_pending_submitted")` — this is
#     a SELECTED+SUBMITTED outcome, not a blocker.
#     live_execution_attempt_events(): `broker_skip:{reason}` — a
#     post-selection broker-stage skip, distinct from a sizing failure.
_PRE_SELECTION_BLOCKERS = frozenset({
    "wash_sale", "sector", "correlation", "tier", "defensive_non_bear",
    "candidate_not_selected",
})
_SIZING_FAILURES = frozenset({
    "buy_blocked", "skip_buys", "size_bad_price", "size_insufficient_cash",
    "size_cash_invariant", "kelly_zero:capped_zero", "bear_defensive_slot_cap",
    "bear_defensive_insufficient_cash",
})
_SELECTED_SUBMITTED = frozenset({"broker_pending_submitted"})
_BROKER_OUTCOME_PREFIX = "broker_skip:"


def _classify_reason(reason: str) -> str:
    """Map a raw `blocked_by` value to its pipeline stage.

    Returns one of: "pre_selection_blocked", "sizing_failed",
    "selected_submitted", "broker_outcome", "unclassified".
    """
    if reason in _PRE_SELECTION_BLOCKERS:
        return "pre_selection_blocked"
    if reason in _SIZING_FAILURES:
        return "sizing_failed"
    if reason in _SELECTED_SUBMITTED:
        return "selected_submitted"
    if reason.startswith(_BROKER_OUTCOME_PREFIX):
        return "broker_outcome"
    return "unclassified"


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

    # ROUND 3 fix: classify blocked_by by PIPELINE STAGE (see _classify_reason
    # / the taxonomy comment above _PRE_SELECTION_BLOCKERS), not by
    # "is it non-null." Round 2's `blocked_by IS NULL` test wrongly treated
    # every non-null value (including genuinely selected+submitted names) as
    # a pre-selection admission failure.
    has_reason = elig["blocked_by"].notna() & (elig["blocked_by"].str.len() > 0)
    elig = elig.copy()
    elig["_stage"] = "selected_filled"  # blocked_by is null -> reached trades cleanly
    elig.loc[has_reason, "_stage"] = elig.loc[has_reason, "blocked_by"].map(_classify_reason)

    admission_breakdown = (
        elig.loc[has_reason, "blocked_by"].value_counts().to_dict()
    )
    stage_counts = elig["_stage"].value_counts().to_dict()

    pre_selection_mask = elig["_stage"] == "pre_selection_blocked"
    unclassified_mask = elig["_stage"] == "unclassified"
    # sizing population = everyone except true pre-selection non-events and
    # anything we can't confidently classify (never force-fit unclassified
    # values into either bucket).
    survived = elig.loc[~(pre_selection_mask | unclassified_mask)].copy()
    n_survived_admission = int(len(survived))
    n_unclassified = int(unclassified_mask.sum())
    admission_breakdown["survived_admission"] = n_survived_admission
    admission_breakdown["unclassified"] = n_unclassified

    if n_survived_admission < 4:
        return {
            "run_id": run_id,
            "n_eligible_by_mu": int(len(elig)),
            "admission_breakdown": admission_breakdown,
            "admission_breakdown_by_stage": stage_counts,
            "n_survived_admission": n_survived_admission,
            "n_unclassified": n_unclassified,
            "category": "insufficient_sizing_population",
            "buy_side_decision_tc": None,
            "exposure_transfer_ratio": None,
        }

    tr = pd.read_sql(
        "select ticker, target_pct from trades where run_id=? and action like 'buy%'",
        con, params=(run_id,))
    actual = dict(zip(tr["ticker"], tr["target_pct"]))
    survived["w_actual"] = survived["ticker"].map(actual)
    # ROUND 3: a `selected_submitted` name (broker_pending_submitted) with no
    # matching `trades` row has an UNKNOWN delivered weight (fill status
    # wasn't confirmed at trace time) — NOT a genuine zero. Folding that into
    # 0.0 would repeat the exact "undefined treated as a known value" error
    # round 2 already fixed for no_deployment/zero_dispersion. Exclude these
    # from the correlation population; keep them in n_survived_admission
    # (they did reach/pass sizing) and report their count separately.
    pending_unconfirmed_mask = (
        (survived["_stage"] == "selected_submitted") & survived["w_actual"].isna()
    )
    n_pending_unconfirmed = int(pending_unconfirmed_mask.sum())
    survived["w_actual"] = survived["w_actual"].fillna(0.0)
    corr_pop = survived.loc[~pending_unconfirmed_mask].copy()
    n_bought = int((corr_pop["w_actual"] > 0).sum())

    # ROUND 2 fix (point 3): distinguish "genuinely undefined correlation"
    # cases from a real, computed near-zero correlation, and NEVER average
    # an undefined case into the correlation series. ROUND 3: computed over
    # corr_pop (survived, minus fill-unconfirmed pending submissions), not
    # the raw sizing population.
    if len(corr_pop) < 4:
        category = "insufficient_corr_population"
        tc_p = None
    elif n_bought == 0:
        category = "no_deployment"
        tc_p = None
    elif corr_pop["w_actual"].std() == 0 or corr_pop["kelly_target_pct"].std() == 0:
        category = "zero_dispersion"  # bought, but no size variation to correlate
        tc_p = None
    else:
        category = "measured"
        tc_p = float(np.corrcoef(corr_pop["kelly_target_pct"], corr_pop["w_actual"])[0, 1])

    # ROUND 2 fix (point 5): a magnitude-sensitive companion metric —
    # regression-through-origin slope of actual onto desired. Computable
    # whenever the desired vector has any dispersion, independent of
    # whether w_actual has dispersion (unlike Pearson TC above).
    denom = float(np.dot(corr_pop["kelly_target_pct"], corr_pop["kelly_target_pct"])) if len(corr_pop) else 0.0
    exposure_transfer_ratio = (
        round(float(np.dot(corr_pop["w_actual"], corr_pop["kelly_target_pct"])) / denom, 3)
        if denom > 0 else None
    )

    return {
        "run_id": run_id,
        "n_eligible_by_mu": int(len(elig)),
        "admission_breakdown": admission_breakdown,
        "admission_breakdown_by_stage": stage_counts,
        "n_survived_admission": n_survived_admission,
        "n_unclassified": n_unclassified,
        "n_pending_unconfirmed": n_pending_unconfirmed,
        "n_corr_population": int(len(corr_pop)),
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
                    "insufficient_sizing_population", "insufficient_corr_population")
    }

    out = {
        "label": "EXPLORATORY DIAGNOSTIC — not measured-tier TC; see round-3 "
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
            "non-independent-until-now sample; the admission/sizing split "
            "itself was misclassified through round 2 — see the progress "
            "doc's round-3 section for the corrected taxonomy and its "
            "caveats before citing any number here)."
        ),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_stc_transfer_coefficient.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
