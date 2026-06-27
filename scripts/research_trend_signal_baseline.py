#!/usr/bin/env python3
"""Read-only DATA-QUALITY / PROVENANCE DIAGNOSTIC for renquant105's goal: catch MORE
(recall) and MORE-ACCURATE (precision) multi-period TREND signals.

SCOPE AND HONEST LIMITS (read before using any number)
------------------------------------------------------
This script is a DIAGNOSTIC, not a model-vs-gate adjudication. The faithful production
cross-section (the LIVE ledger) is too short for the primary trend horizon (fwd_20d/60d):
the per-name decision ledger was only wired ~2026-05-04 (#133), and a 20-session label
needs 20 trading sessions to realize, so only a handful of aged dates exist and they sit
inside a single overlapping window (a low overlap-ratio, NOT N independent observations).

This script can NEVER emit a model-vs-gate lever ranking. The synthetic
``(book_size, mu_floor)`` killed-winner decomposition is scorer-mixed, k-dependent,
non-causal, and is NOT the deployed selection path — MORE DATES DO NOT REPAIR THAT
ESTIMAND. Sufficiency is necessary, not sufficient. Therefore:

  * ``bottleneck_verdict`` is ``UNDETERMINED`` UNCONDITIONALLY. There is no code path that
    flips it to ``DETERMINED`` and no code path that produces a ``missed_by_model`` vs
    ``killed_by_gate`` ranking. A faithful verdict requires a future STATEFUL production
    replay (homogeneous artifact provenance + paired counterfactuals + block-aware
    uncertainty) that this script does NOT perform.
  * ``lever_ranking`` is ALWAYS ``null``.
  * A "sufficient" overlap-ratio may at most unlock IC *descriptives* (and an on-cohort
    placebo) — NEVER a model-vs-gate ranking.

What the descriptive numbers ARE and ARE NOT
--------------------------------------------
  1. Signal accuracy (PRECISION lens) — cross-sectional rank-IC of the pooled live score
     (``mu`` / ``raw_score``) vs forward returns at fwd_5/10/20/60d. The live ``mu`` cohort
     is a SCORER MIXTURE (``panel_ltr_xgboost``-dominant with only a handful of
     ``hf_patchtst`` rows), so this is NOT a clean PatchTST-primary IC. The 0.036 number
     from another experiment is NOT a portable significance bar — a placebo that PRESERVES
     TIME DEPENDENCE (a blockwise per-ticker rank shift, not an independent within-date
     permutation) MUST be recomputed on THIS exact cohort and each horizon before any IC is
     called "real". This script reports such a placebo (``--placebo-shuffles``) using the
     finite-MC estimator ``(exceedances + 1) / (B + 1)`` so the p-value is NEVER 0, runs it
     ONLY on the faithful homogeneous LIVE cohort (NOT the unfaithful SIM cohort), and
     compares observed IC to that distribution; it does not cite the foreign 0.036 as a
     pass/fail line.
  2. Trend RECALL / PRECISION — top-k / top-quintile capture of the day's realized
     up-trends and the directional precision of the top-k. "Real trend" here is an EX-POST
     top-decile positive fwd_20d cross-section, which is a per-date drift label, NOT a
     persistent multi-day trend EVENT with a defined start/end. Recall is mechanically
     universe-size dependent. These are reported WITH the IMPLEMENTED baselines (the ANALYTIC
     random-recall ``k/n``, a market-sign precision baseline, and the current-selected-book)
     so the model number is not read in a vacuum. The report DISTINGUISHES these IMPLEMENTED
     baselines from the REQUIRED FOLLOW-UPS that are NOT delivered here (simple-momentum —
     the ledger carries no trailing-price feature — oracle-capacity, regime/sector-neutral,
     net-of-cost, AUPRC,
     capacity-normalized recall, and an explicit trend-event start/end definition).
  3. GATE impact — the live conviction gate ``(mu - mean(mu)) >= mu_floor`` is ONE
     synthetic de-meaned threshold, NOT the deployed ordered gate stack + capacity
     allocation. The killed-winner split is K-DEPENDENT BY CONSTRUCTION (it reverses under
     different ``book_size`` / universe / ``mu_floor``); this script reports it across a
     SENSITIVITY GRID of (book_size, mu_floor) ONLY to make the k-dependence visible, and
     labels the whole thing "scorer-mixture ranking vs one synthetic threshold", NEVER a
     causal model-vs-gate attribution and NEVER a lever ranking. The persisted ``selected``
     / ``blocked_by`` columns are summarized to contrast this synthetic threshold against the
     ACTUAL deployed selection.
  4. STALENESS — a chronological IC split is reported as DESCRIPTIVE ONLY. It CONFOUNDS
     model age with regime, scorer composition, universe and label overlap, so it is NOT
     evidence that freshness caused any decline. The controlled paired experiment that
     WOULD identify a freshness effect is described in the research doc, not run here.

PROVENANCE / REPRODUCIBILITY
----------------------------
Every run emits an immutable input manifest (``--json`` → ``manifest``): DB SHA256, file
size + mtime, sqlite schema version, the resolved per-date run_ids, the live scorer/
model_type mix, CLI args, code commit, the aged session calendar, and the as-of date. Every
denominator/window is labelled explicitly (all-live gate stats vs the aged-subset trend
stats are kept separate and never conflated).

Read-only. The DB is opened ``mode=ro``; the script never writes to any canonical path.
Usage:
    research_trend_signal_baseline.py [--runs-db PATH] [--book-size 8] [--mu-floor 0.03]
        [--min-overlap-ratio 6] [--min-xsec 10] [--as-of YYYY-MM-DD]
        [--placebo-shuffles 200] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

REPO = Path("/Users/renhao/git/github/RenQuant")
DEF_DB = REPO / "data" / "runs.alpaca.db"
HORIZONS = ["fwd_5d", "fwd_10d", "fwd_20d", "fwd_60d"]
PRIMARY = "fwd_20d"
_HORIZON_N = {"fwd_5d": 5, "fwd_10d": 10, "fwd_20d": 20, "fwd_60d": 60}
# Foreign reference ONLY — NOT a portable significance bar for this cohort. Kept so the
# report can explicitly say "do not use this as the line; placebo recomputed on-cohort".
FOREIGN_LEAKAGE_FLOOR_REFERENCE = 0.036
# Sensitivity grid for the K-DEPENDENT killed-winner split (Finding 3). The split reverses
# across these operating points; reporting the surface makes that explicit.
SENS_BOOK_SIZES = (5, 8, 12)
SENS_MU_FLOORS = (0.0, 0.03, 0.06)


def _connect_ro(db: Path):
    """Open the ledger strictly read-only (never mutate a canonical path)."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _sha256(db: Path) -> str:
    h = hashlib.sha256()
    with open(db, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _code_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(Path(__file__).resolve().parent),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def load(db: Path, *, as_of=None):
    """Load the per-name score ledger joined to forward returns, keeping ``run_type``.

    DETERMINISTIC run resolution (Finding 2): per (date, run_type) keep the run_id with the
    most candidate rows; ties are REJECTED, not silently broken — a tied date is recorded in
    ``ambiguous_dates`` and dropped, so the result never depends on row order. ``selected``
    and ``blocked_by`` are loaded and RETAINED (the deployed selection is summarized so the
    one synthetic de-meaned threshold can be contrasted with the actual gate).

    AS-OF CORRECTNESS: when ``as_of`` is given, candidate runs (and therefore the resolved-run
    / scorer-mix manifest surfaces) and the session calendar are filtered to
    ``run_date <= as_of``. An as-of rerun must NOT surface later-dated runs in provenance or
    summary surfaces, even though horizon aging already filters the IC rows downstream.
    """
    import pandas as pd  # noqa: PLC0415
    con = _connect_ro(db)
    cs = pd.read_sql(
        "select cs.run_id, cs.ticker, cs.raw_score, cs.mu, cs.selected, cs.blocked_by, "
        "cs.model_type, cs.active_scorer, pr.run_type, pr.run_date "
        "from candidate_scores cs join pipeline_runs pr on cs.run_id = pr.run_id "
        "where cs.mu is not null", con)
    fr = pd.read_sql(
        "select as_of_date as date, ticker, fwd_5d, fwd_10d, fwd_20d, fwd_60d "
        "from ticker_forward_returns", con)
    schema_version = pd.read_sql("pragma schema_version", con).iloc[0, 0]
    con.close()
    cs["date"] = pd.to_datetime(cs["run_date"], errors="coerce")
    fr["date"] = pd.to_datetime(fr["date"], errors="coerce")
    cs = cs.dropna(subset=["date"])
    if as_of is not None:
        as_of_ts = pd.Timestamp(as_of)
        cs = cs[cs["date"] <= as_of_ts]
        fr = fr[fr["date"] <= as_of_ts]
    n = cs.groupby(["date", "run_type", "run_id"]).size().reset_index(name="n")
    # deterministic: max rows per (date, run_type); REJECT ties.
    n = n.sort_values(["date", "run_type", "n"])
    top = n.groupby(["date", "run_type"]).tail(1)
    second = n.groupby(["date", "run_type"]).tail(2).groupby(["date", "run_type"]).head(1)
    merged = top.merge(second, on=["date", "run_type"], suffixes=("", "_2"))
    ambiguous = merged[(merged["n"] == merged["n_2"]) & (merged["run_id"] != merged["run_id_2"])]
    ambiguous_dates = sorted({str(pd.Timestamp(d).date()) for d in ambiguous["date"]})
    keep = top.merge(ambiguous[["date", "run_type"]], on=["date", "run_type"], how="left",
                     indicator=True)
    keep = keep[keep["_merge"] == "left_only"]
    cs = cs.merge(keep[["date", "run_type", "run_id"]], on=["date", "run_type", "run_id"])
    sessions = sorted(fr["date"].dropna().unique())
    m = cs.merge(fr, on=["date", "ticker"], how="left")
    resolved_runs = (cs[["date", "run_type", "run_id"]].drop_duplicates()
                     .assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"))
                     .sort_values(["run_type", "date"]).to_dict("records"))
    meta = {"schema_version": int(schema_version), "ambiguous_dates_rejected": ambiguous_dates,
            "resolved_runs": resolved_runs}
    return m, sessions, meta


def _aged_cutoff(sessions, horizon_n: int, as_of):
    """Newest date whose ``horizon_n``-session label is fully realized as of ``as_of``."""
    import pandas as pd  # noqa: PLC0415
    as_of_ts = pd.Timestamp(as_of)
    idx = pd.DatetimeIndex([s for s in sessions if pd.Timestamp(s) <= as_of_ts])
    if len(idx) > horizon_n:
        return idx[-(horizon_n + 1)]
    return (idx[0] - pd.Timedelta(days=1)) if len(idx) else as_of_ts


# The sufficiency criterion is a CONSERVATIVE DESCRIPTIVE *overlap-ratio* (n_dates / horizon_n),
# NOT a power / N_eff calc: it ignores calendar gaps, irregular coverage, autocorrelation beyond
# the horizon, scorer composition, and regime concentration. The REAL unblock — which #201 MUST
# CONSUME AS THE SAME CRITERION — is: a conservative overlap-ratio descriptor now; a
# pre-registered minimum-effect/power + an empirical-dependence calc on a faithful homogeneous
# cohort as the real unblock (NO calendar date). The verdict stays UNDETERMINED regardless.
OVERLAP_RATIO_UNBLOCK_NOTE = (
    "conservative overlap-ratio descriptor now; the real unblock (which #201 must consume as "
    "the SAME criterion) is a pre-registered minimum-effect/power + an empirical-dependence "
    "calc on a faithful homogeneous cohort (NO calendar date). Verdict stays UNDETERMINED.")


def _overlap_ratio(n_dates: int, horizon_n: int) -> float:
    """Conservative DESCRIPTIVE overlap-ratio for OVERLAPPING horizon labels (Finding 3).

    N adjacent dates with an N-session forward label cover ~ n_dates / horizon_n
    NON-overlapping windows. This is a CONSERVATIVE DESCRIPTOR, NOT a power/N_eff figure: it
    ignores gaps, irregular coverage, autocorrelation beyond the horizon, scorer composition,
    and regime concentration. It NEVER unlocks a verdict; see OVERLAP_RATIO_UNBLOCK_NOTE.
    """
    if n_dates <= 0:
        return 0.0
    return n_dates / float(horizon_n)


def rank_ic(frame, horizon, score, *, min_xsec):
    """Per-date Spearman(score, realized horizon return); pooled mean ± IC_IR."""
    import pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon, score])
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    ics = []
    for _dt, s in g.groupby("date"):
        if s[score].nunique() > 2 and s[horizon].nunique() > 1:
            ics.append(float(s[[score, horizon]].corr("spearman").iloc[0, 1]))
    ics = pd.Series([x for x in ics if x == x])
    if not len(ics):
        return {"n_dates": 0, "overlap_ratio": 0.0, "mean_ic": None, "ic_ir": None,
                "median_ic": None}
    sd = float(ics.std())
    return {"n_dates": int(len(ics)),
            "overlap_ratio": round(_overlap_ratio(len(ics), _HORIZON_N[horizon]), 2),
            "mean_ic": float(ics.mean()),
            "ic_ir": (float(ics.mean() / sd) if sd > 0 else None),
            "median_ic": float(ics.median())}


def placebo_ic(frame, horizon, score, *, min_xsec, n_shuffles, seed=0):
    """Dependence-PRESERVING on-cohort placebo (Findings 2 + 7).

    The earlier within-date permutation destroyed persistent ticker rank and cross-date
    dependence while the overlapping fwd labels stay correlated → the null was too narrow
    (it even printed p=0 on the SIM ref). Instead this uses a BLOCKWISE CIRCULAR TIME-SHIFT:
    each date's WHOLE score cross-section is kept intact (preserving persistent within-date
    ticker ranks AND the score series' serial structure) and re-paired to a DIFFERENT date's
    realized returns via a circular shift of the date axis by a random non-zero lag. That
    breaks the score↔return alignment while preserving both the cross-sectional and the
    serial dependence the overlapping labels carry.

    The p-value is the finite-MC estimator ``(exceedances + 1) / (B + 1)`` so it is NEVER 0.
    CALLER CONTRACT: run this ONLY on a faithful homogeneous cohort (the LIVE lens), NEVER on
    the explicitly unfaithful SIM cohort.
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon, score])
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    obs = rank_ic(g, horizon, score, min_xsec=min_xsec)
    note_pre = ("dependence-preserving blockwise circular date-shift placebo; "
                "p=(exceedances+1)/(B+1); compare observed_ic to placebo_p95_ic")
    if not obs["n_dates"] or n_shuffles <= 0:
        return {"n_shuffles": 0, "observed_ic": obs.get("mean_ic"),
                "placebo_mean_ic": None, "placebo_std_ic": None, "placebo_p95_ic": None,
                "p_value": None, "note": "no placebo (thin or disabled)"}
    # Per date: (score vector, return vector) keyed by ticker, kept WHOLE.
    dates = sorted(g["date"].unique())
    n_dates = len(dates)
    if n_dates < 3:
        # Too few blocks to circular-shift without trivially recovering the identity.
        return {"n_shuffles": 0, "observed_ic": obs["mean_ic"], "placebo_mean_ic": None,
                "placebo_std_ic": None, "placebo_p95_ic": None, "p_value": None,
                "note": "placebo skipped: < 3 date-blocks — cannot circular-shift the date axis"}
    by_date = {d: s for d, s in g.groupby("date")}
    score_maps = {d: dict(zip(by_date[d]["ticker"], by_date[d][score])) for d in dates}
    rng = np.random.default_rng(seed)
    means = []
    # All non-zero lags give a valid dependence-preserving re-pairing; sample (or enumerate).
    lags = list(range(1, n_dates))
    n_draws = min(n_shuffles, len(lags))
    chosen = lags if n_shuffles >= len(lags) else list(rng.choice(lags, size=n_draws,
                                                                   replace=False))
    for lag in chosen:
        ics = []
        for i, d in enumerate(dates):
            src = dates[(i + lag) % n_dates]  # score date for the placebo pairing
            ret_s = by_date[d]
            smap = score_maps[src]
            paired = ret_s.assign(_sc=ret_s["ticker"].map(smap)).dropna(subset=["_sc"])
            if len(paired) >= min_xsec and paired["_sc"].nunique() > 2 and \
                    paired[horizon].nunique() > 1:
                ics.append(float(paired[["_sc", horizon]].corr("spearman").iloc[0, 1]))
        ics = [x for x in ics if x == x]
        if ics:
            means.append(float(np.mean(ics)))
    if not means:
        return {"n_shuffles": 0, "observed_ic": obs["mean_ic"], "placebo_mean_ic": None,
                "placebo_std_ic": None, "placebo_p95_ic": None, "p_value": None,
                "note": "placebo degenerate (no shifted pairing met min_xsec)"}
    means = np.array(means)
    b = len(means)
    exceed = int((means >= obs["mean_ic"]).sum())
    p = (exceed + 1) / (b + 1)  # finite-MC: never 0, never > 1
    return {"n_shuffles": int(b), "observed_ic": obs["mean_ic"],
            "placebo_mean_ic": float(means.mean()), "placebo_std_ic": float(means.std()),
            "placebo_p95_ic": float(np.percentile(means, 95)), "p_value": float(p),
            "note": note_pre}


def recall_precision_gate(frame, *, horizon, book_size, mu_floor, min_xsec):
    """Descriptive trend recall/precision + IMPLEMENTED baselines + the K-DEPENDENT split.

    A realized "trend" = a name in the top-decile of POSITIVE ``horizon`` return on a date
    (EX-POST per-date drift label, NOT a persistent event — see module docstring). Reports:
      * model top-k / top-quintile recall, top-k directional precision;
      * gate-admitted (one synthetic de-meaned threshold) recall/precision;
      * IMPLEMENTED baselines (Finding 4), with NO Monte-Carlo noise:
          - ``recall_random`` = the ANALYTIC random top-k recall ``book_size / n`` (the exact
            expectation of a random top-k's trend recall; no seeded draw);
          - ``prec_market_sign`` = market-positive prevalence (precision of "pick any name");
          - ``recall_selected_book`` = recall of the ACTUAL persisted ``selected`` book (the
            current-selected-book baseline) — implemented from the real selection column.
        REQUIRED FOLLOW-UPS (NOT implemented here — flagged in ``baselines_followups``):
        simple-momentum ranking (the ledger carries NO trailing-price feature), oracle-
        capacity, regime/sector-neutral, AUPRC, capacity-normalized recall, net-of-cost.
      * killed-winner split (missed_by_model / killed_by_gate) — reported but LABELLED
        k-dependent and NON-causal; it is NEVER turned into a lever ranking.
    Aggregated as a per-date block (mean over dates).
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon]).copy()
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    if g.empty:
        return {"n_dates": 0}
    has_selected = "selected" in g.columns
    rows = []
    for _dt, s in g.groupby("date"):
        s = s.copy()
        n = len(s)
        dec_n = max(1, int(round(n * 0.10)))
        quint_n = max(1, int(round(n * 0.20)))
        ret_rank = s[horizon].rank(ascending=False, method="first")
        real_trend = (s[horizon] > 0) & (ret_rank <= dec_n)
        n_real = int(real_trend.sum())
        mu_rank = s["mu"].rank(ascending=False, method="first")
        model_topk = mu_rank <= book_size
        model_topq = mu_rank <= quint_n
        dem = s["mu"] - s["mu"].mean()
        admit = dem >= mu_floor
        pos_tercile = s[horizon] > s[horizon].quantile(2 / 3)
        # ANALYTIC random top-k recall: a random top-k captures each real trend w.p. k/n, so
        # its expected recall is exactly min(1, book_size / n) — no MC noise, no seed.
        recall_random = float(min(1.0, book_size / n))
        mkt_pos_frac = float((s[horizon] > 0).mean())  # market-sign precision baseline
        # current-selected-book baseline: the ACTUAL persisted selection (real column).
        if has_selected:
            sel_mask = pd.to_numeric(s["selected"], errors="coerce").fillna(0) > 0
            n_sel = int(sel_mask.sum())
            recall_selected = (float((sel_mask & real_trend).sum() / n_real)
                               if (n_real and n_sel) else np.nan)
        else:
            recall_selected = np.nan
        rows.append({
            "n": n, "n_real": n_real, "n_admit": int(admit.sum()),
            "recall_topk": (float((model_topk & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_topq": (float((model_topq & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_gate": (float((admit & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_random": recall_random,  # analytic k/n, deterministic
            "recall_selected_book": recall_selected,  # current-selected-book baseline
            "prec_topk_pos": (float((model_topk & (s[horizon] > 0)).sum() / book_size)),
            "prec_topk_terc": (float((model_topk & pos_tercile).sum() / book_size)),
            "prec_market_sign": mkt_pos_frac,  # baseline: pick any name -> this is precision
            "prec_gate_pos": (float((admit & (s[horizon] > 0)).sum() / admit.sum()) if admit.sum() else np.nan),
            "prec_gate_terc": (float((admit & pos_tercile).sum() / admit.sum()) if admit.sum() else np.nan),
            # K-DEPENDENT, NON-CAUSAL split (reported, NEVER a lever ranking):
            "killed_by_gate": (float(((real_trend) & (model_topk) & (~admit)).sum() / n_real) if n_real else np.nan),
            "missed_by_model": (float(((real_trend) & (~model_topk)).sum() / n_real) if n_real else np.nan),
        })
    df = pd.DataFrame(rows)
    out = {"n_dates": int(len(df)), "book_size": book_size, "mu_floor": mu_floor,
           "overlap_ratio": round(_overlap_ratio(len(df), _HORIZON_N[horizon]), 2),
           "mean_names": float(df["n"].mean()), "mean_real_trends": float(df["n_real"].mean()),
           "mean_gate_admits": float(df["n_admit"].mean()),
           "baselines_implemented": ["recall_random (analytic k/n)", "prec_market_sign",
                                     "recall_selected_book (current-selected book)"],
           "baselines_followups_NOT_implemented": [
               "simple-momentum (no trailing-price feature in the ledger)", "oracle-capacity",
               "regime/sector-neutral", "AUPRC", "capacity-normalized recall", "net-of-cost",
               "explicit trend-event start/end definition"]}
    for c in ["recall_topk", "recall_topq", "recall_gate", "recall_random",
              "recall_selected_book", "prec_topk_pos", "prec_topk_terc", "prec_market_sign",
              "prec_gate_pos", "prec_gate_terc", "killed_by_gate", "missed_by_model"]:
        v = df[c].dropna()
        out[c] = float(v.mean()) if len(v) else None
    return out


def killed_winner_sensitivity(frame, *, horizon, min_xsec):
    """Finding 3: the killed-winner split across an operating-point grid, to expose that the
    missed_by_model / killed_by_gate ratio is K-DEPENDENT and reverses — so it is NEVER
    labelled a "bottleneck" off a single (book_size, mu_floor)."""
    grid = []
    for bs in SENS_BOOK_SIZES:
        for mf in SENS_MU_FLOORS:
            r = recall_precision_gate(frame, horizon=horizon, book_size=bs, mu_floor=mf,
                                      min_xsec=min_xsec)
            if r.get("n_dates"):
                grid.append({"book_size": bs, "mu_floor": mf,
                             "missed_by_model": r.get("missed_by_model"),
                             "killed_by_gate": r.get("killed_by_gate"),
                             "recall_topk": r.get("recall_topk")})
    ratios = [(g["missed_by_model"] / g["killed_by_gate"])
              for g in grid if g.get("killed_by_gate")]
    return {"grid": grid,
            "ratio_min": (min(ratios) if ratios else None),
            "ratio_max": (max(ratios) if ratios else None),
            "note": ("missed/killed ratio spans the grid; it is k-dependent and NOT a causal "
                     "bottleneck attribution")}


def deployed_selection_summary(frame, *, min_xsec):
    """Summarize the ACTUAL persisted selection (Finding 2): how often the live path SELECTED
    names and what blocked the rest — contrasted with the synthetic de-meaned threshold."""
    import pandas as pd  # noqa: PLC0415
    g = frame.copy()
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    if g.empty or "selected" not in g.columns:
        return {"n_dates": 0}
    sel = pd.to_numeric(g["selected"], errors="coerce").fillna(0)
    per_date = g.assign(_sel=sel).groupby("date")["_sel"].sum()
    blocked = (g["blocked_by"].dropna().astype(str).value_counts().head(8).to_dict())
    return {"n_dates": int(g["date"].nunique()),
            "mean_selected_per_date": float(per_date.mean()),
            "dates_with_zero_selected_frac": float((per_date == 0).mean()),
            "top_blocked_by": {str(k): int(v) for k, v in blocked.items()},
            "note": "ACTUAL deployed selection — contrast with the synthetic mu-demean threshold"}


def evaluate(db: Path, *, book_size, mu_floor, min_overlap_ratio, min_xsec, as_of=None,
             placebo_shuffles=0):
    import datetime as _dt  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(_dt.date.today())
    # AS-OF CORRECTNESS: candidate runs + the resolved-run/scorer-mix manifest surfaces are
    # filtered to run_date <= as_of inside load() — a later-dated run never enters provenance.
    m, sessions, meta = load(db, as_of=as_of_ts)
    st = os.stat(db)
    live_all = m[m.run_type == "live"]
    scorer_mix = {}
    if len(live_all):
        scorer_mix = {str(k): int(v) for k, v in
                      live_all["model_type"].fillna("None").value_counts().items()}
    out = {
        "manifest": {
            "db_path": str(db), "db_sha256": _sha256(db), "db_size_bytes": st.st_size,
            "db_mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "schema_version": meta["schema_version"],
            "code_commit": _code_commit(),
            "cli_args": {"book_size": book_size, "mu_floor": mu_floor,
                         "min_overlap_ratio": min_overlap_ratio, "min_xsec": min_xsec,
                         "as_of": str(as_of_ts.date()), "placebo_shuffles": placebo_shuffles},
            "as_of": str(as_of_ts.date()),
            "runs_filtered_to_run_date_le_as_of": True,
            "n_sessions_in_calendar": len(sessions),
            "session_calendar_first": (str(pd.Timestamp(sessions[0]).date()) if sessions else None),
            "session_calendar_last": (str(pd.Timestamp(sessions[-1]).date()) if sessions else None),
            "ambiguous_dates_rejected": meta["ambiguous_dates_rejected"],
            "resolved_runs": meta["resolved_runs"],
            "live_scorer_mix": scorer_mix,
        },
        "as_of": str(as_of_ts.date()),
        "book_size": book_size, "mu_floor": mu_floor, "min_overlap_ratio": min_overlap_ratio,
        "overlap_ratio_unblock_note": OVERLAP_RATIO_UNBLOCK_NOTE,
        "foreign_leakage_floor_reference_DO_NOT_USE_AS_BAR": FOREIGN_LEAKAGE_FLOOR_REFERENCE,
        "run_type_dates": {rt: int(m[m.run_type == rt]["date"].nunique())
                           for rt in sorted(m["run_type"].dropna().unique())},
    }

    def lens(sub, label, *, run_placebo):
        # run_placebo: the dependence-preserving placebo runs ONLY on the faithful homogeneous
        # LIVE cohort (Finding 2) — never on the explicitly unfaithful SIM cohort.
        res = {"label": label, "ic": {}, "placebo": {}, "trend": {}, "staleness": {}}
        for h in HORIZONS:
            cut = _aged_cutoff(sessions, _HORIZON_N[h], as_of_ts)
            aged = sub[sub["date"] <= cut]
            res["ic"][h] = {"mu": rank_ic(aged, h, "mu", min_xsec=min_xsec),
                            "raw_score": rank_ic(aged.dropna(subset=["raw_score"]), h,
                                                 "raw_score", min_xsec=min_xsec),
                            "aged_cutoff": str(pd.Timestamp(cut).date())}
            if run_placebo:
                res["placebo"][h] = placebo_ic(aged, h, "mu", min_xsec=min_xsec,
                                               n_shuffles=placebo_shuffles)
            else:
                res["placebo"][h] = {"n_shuffles": 0, "p_value": None,
                                     "note": "placebo NOT run on the unfaithful SIM cohort "
                                             "(Finding 2: faithful cohorts only)"}
        cut = _aged_cutoff(sessions, _HORIZON_N[PRIMARY], as_of_ts)
        aged_p = sub[sub["date"] <= cut]
        res["trend"][PRIMARY] = recall_precision_gate(
            aged_p, horizon=PRIMARY, book_size=book_size, mu_floor=mu_floor, min_xsec=min_xsec)
        res["killed_sensitivity"] = killed_winner_sensitivity(
            aged_p, horizon=PRIMARY, min_xsec=min_xsec)
        # deployed selection summary uses the ALL-aged frame (own denominator, labelled)
        res["deployed_selection"] = deployed_selection_summary(aged_p, min_xsec=min_xsec)
        # staleness: DESCRIPTIVE ONLY — confounded, NOT a freshness-causes-decline claim.
        ic_dates = []
        g = aged_p.dropna(subset=[PRIMARY, "mu"])
        g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
        for dt, s in g.groupby("date"):
            if s["mu"].nunique() > 2 and s[PRIMARY].nunique() > 1:
                ic_dates.append((dt, float(s[["mu", PRIMARY]].corr("spearman").iloc[0, 1])))
        ic_dates.sort()
        if len(ic_dates) >= 4:
            half = len(ic_dates) // 2
            older = pd.Series([v for _, v in ic_dates[:half]])
            recent = pd.Series([v for _, v in ic_dates[half:]])
            res["staleness"][PRIMARY] = {
                "DESCRIPTIVE_ONLY_confounded": True,
                "older_mean_ic": float(older.mean()), "older_n": len(older),
                "recent_mean_ic": float(recent.mean()), "recent_n": len(recent),
                "recent_minus_older": float(recent.mean() - older.mean()),
                "note": "confounds age with regime/scorer/universe/overlap; NOT a freshness "
                        "effect — see the controlled paired-experiment design in the doc"}
        else:
            res["staleness"][PRIMARY] = {"status": "thin", "n_dates": len(ic_dates)}
        # OVERLAP-RATIO descriptor (Finding 3): a conservative DESCRIPTOR, NOT power/N_eff and
        # NOT a verdict unlock. Even when it clears the bar it may at most unlock IC
        # descriptives — never a model-vs-gate ranking.
        n_dates = res["trend"][PRIMARY].get("n_dates", 0)
        ratio = _overlap_ratio(n_dates, _HORIZON_N[PRIMARY])
        res["primary_aged_dates"] = n_dates
        res["primary_overlap_ratio"] = round(ratio, 2)
        res["ic_descriptives_unlocked"] = bool(ratio >= min_overlap_ratio)
        return res

    out["live"] = lens(live_all, "LIVE (scorer MIXTURE — xgboost-dominant, few PatchTST rows)",
                       run_placebo=True)
    out["sim_reference_NOT_validation_grade"] = lens(
        m[m.run_type == "sim"], "SIM (NULL scorer / non-PatchTST raw — reference only)",
        run_placebo=False)

    live_ratio = out["live"]["primary_overlap_ratio"]
    live_n = out["live"]["primary_aged_dates"]
    ic_unlocked = out["live"]["ic_descriptives_unlocked"]
    # CENTRAL GATE (Finding 1): the bottleneck verdict is UNDETERMINED UNCONDITIONALLY. There is
    # NO code path that produces a model-vs-gate lever ranking from the synthetic decomposition
    # (it is scorer-mixed, k-dependent, non-causal, and NOT the deployed path). More dates do
    # NOT repair the estimand. A faithful verdict needs a future STATEFUL production replay
    # (homogeneous artifact provenance + paired counterfactuals + block-aware uncertainty) that
    # this script does not perform. The overlap-ratio may at most unlock IC *descriptives*.
    out["bottleneck_verdict"] = "UNDETERMINED"
    out["lever_ranking"] = None
    out["lever_ranking_note"] = (
        "ALWAYS null: this script can NEVER emit a model-vs-gate ranking from the synthetic "
        "(book_size, mu_floor) decomposition — it is scorer-mixed, k-dependent, non-causal, "
        "and not the deployed path. Only a future faithful STATEFUL production replay "
        "(homogeneous artifact provenance + paired counterfactuals + block-aware uncertainty) "
        "may produce one. Sufficiency is necessary, not sufficient.")
    detail = (
        f"{live_n} aged LIVE dates (~{live_ratio} overlap-ratio blocks) for {PRIMARY}; "
        f"min_overlap_ratio={min_overlap_ratio}. The overlap-ratio is a conservative "
        f"DESCRIPTOR, NOT power/N_eff, and it NEVER unlocks a model-vs-gate verdict — at most "
        f"IC descriptives (ic_descriptives_unlocked={ic_unlocked}). The live cohort is a "
        f"SCORER MIXTURE (xgboost-dominant, few PatchTST rows), not a clean PatchTST-primary "
        f"baseline; the SIM ledger is NOT faithful (NULL scorer, non-PatchTST raw) and is "
        f"reference-only (no placebo run on it). The descriptive numbers are DATA-QUALITY "
        f"DIAGNOSTICS only. " + OVERLAP_RATIO_UNBLOCK_NOTE)
    out["data_sufficiency"] = {
        "live_primary_aged_dates": live_n,
        "live_primary_overlap_ratio": live_ratio,
        "min_overlap_ratio": min_overlap_ratio,
        "ic_descriptives_unlocked": ic_unlocked,
        "verdict": "UNDETERMINED_UNCONDITIONAL",
        "detail": detail}
    return out


def _fmt_ic(d):
    if d.get("mean_ic") is None:
        return "n=0 (insufficient)"
    return (f"IC={d['mean_ic']:+.4f} IC_IR={d['ic_ir']:+.3f} "
            f"({d['n_dates']}d ≈{d.get('overlap_ratio')} overlap)" if d.get("ic_ir") is not None
            else f"IC={d['mean_ic']:+.4f} ({d['n_dates']}d ≈{d.get('overlap_ratio')} overlap)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--book-size", type=int, default=8)
    p.add_argument("--mu-floor", type=float, default=0.03)
    p.add_argument("--min-overlap-ratio", type=float, default=6.0,
                   help="conservative DESCRIPTIVE overlap-ratio (n_dates/horizon) on the primary "
                        "horizon below which IC descriptives are flagged thin; NOT power/N_eff "
                        "and NEVER unlocks a model-vs-gate verdict (always UNDETERMINED)")
    p.add_argument("--min-xsec", type=int, default=10)
    p.add_argument("--as-of", default=None)
    p.add_argument("--placebo-shuffles", type=int, default=0,
                   help="dependence-preserving on-cohort placebo shifts (0 = skip; ~200 for a "
                        "bar); runs on the faithful LIVE cohort only")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    db = Path(args.runs_db)
    if not db.exists():
        print(f"SKIP: ledger DB not found at {db} (read-only field study; needs the live "
              f"decision ledger). Nothing to compute.")
        return 0
    res = evaluate(db, book_size=args.book_size, mu_floor=args.mu_floor,
                   min_overlap_ratio=args.min_overlap_ratio, min_xsec=args.min_xsec,
                   as_of=args.as_of, placebo_shuffles=args.placebo_shuffles)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0
    ds = res["data_sufficiency"]
    print(f"as_of={res['as_of']}  run_type_dates={res['run_type_dates']}")
    print(f"BOTTLENECK VERDICT: {res['bottleneck_verdict']} (UNCONDITIONAL)  "
          f"(data {ds['verdict']}: {ds['live_primary_aged_dates']} aged dates "
          f"≈ {ds['live_primary_overlap_ratio']} overlap-ratio, "
          f"min_overlap_ratio={ds['min_overlap_ratio']}, "
          f"ic_descriptives_unlocked={ds['ic_descriptives_unlocked']})")
    print("  -> UNDETERMINED unconditionally: NO model-vs-gate lever ranking is EVER emitted, "
          "NO retraining recommendation. The numbers below are DATA-QUALITY DIAGNOSTICS only.")
    for key in ("live", "sim_reference_NOT_validation_grade"):
        r = res[key]
        print(f"\n=== {r['label']} ===")
        for h in HORIZONS:
            mu = r["ic"][h]["mu"]
            raw = r["ic"][h]["raw_score"]
            pb = r["placebo"].get(h, {})
            pbtxt = (f" | placebo p={pb['p_value']:.3f}" if pb.get("p_value") is not None
                     else " | placebo: not run")
            print(f"  {h}: mu {_fmt_ic(mu)} | raw {_fmt_ic(raw)}{pbtxt}")
        t = r["trend"][PRIMARY]
        if t.get("n_dates"):
            print(f"  TREND ({PRIMARY}, {t['n_dates']}d ≈{t.get('overlap_ratio')} overlap, "
                  f"book={t['book_size']}): recall_topk={t.get('recall_topk')!r} "
                  f"(random k/n={t.get('recall_random')!r}, "
                  f"selected-book={t.get('recall_selected_book')!r}) "
                  f"prec_topk_pos={t.get('prec_topk_pos')!r} "
                  f"(market-sign={t.get('prec_market_sign')!r})")
            sens = r.get("killed_sensitivity", {})
            print(f"    KILLED-WINNER split is K-DEPENDENT (NOT causal): "
                  f"missed/killed ratio spans [{sens.get('ratio_min')!r}, "
                  f"{sens.get('ratio_max')!r}] across the (book,floor) grid")
            dep = r.get("deployed_selection", {})
            if dep.get("n_dates"):
                print(f"    DEPLOYED selection (actual): mean_selected/date="
                      f"{dep.get('mean_selected_per_date')!r}, "
                      f"zero-selected dates={dep.get('dates_with_zero_selected_frac')!r}")
        st = r["staleness"].get(PRIMARY, {})
        if "recent_minus_older" in st:
            print(f"    STALENESS (DESCRIPTIVE ONLY, confounded): older="
                  f"{st['older_mean_ic']:+.4f} recent={st['recent_mean_ic']:+.4f} "
                  f"Δ={st['recent_minus_older']:+.4f} — NOT a freshness effect")
    print(f"\n>>> {ds['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
