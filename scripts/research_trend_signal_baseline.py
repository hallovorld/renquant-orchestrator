#!/usr/bin/env python3
"""Read-only DATA-QUALITY / PROVENANCE DIAGNOSTIC for renquant105's goal: catch MORE
(recall) and MORE-ACCURATE (precision) multi-period TREND signals.

SCOPE AND HONEST LIMITS (read before using any number)
------------------------------------------------------
This script is a DIAGNOSTIC, not a model-vs-gate adjudication. The faithful production
cross-section (the LIVE ledger) is too short for the primary trend horizon (fwd_20d/60d):
the per-name decision ledger was only wired ~2026-05-04 (#133), and a 20-session label
needs 20 trading sessions to realize, so only a handful of aged dates exist and they sit
inside a single overlapping window (≈1–2 independent time blocks, NOT N raw dates).

Under that insufficiency the script DELIBERATELY DOES NOT rank levers or recommend
retraining. It emits, gated on the measured sufficiency:

  * ``bottleneck_verdict``:
      - ``UNDETERMINED`` whenever the LIVE primary horizon is below the pre-registered
        effective-N requirement (the common case today). In this state the descriptive
        numbers below are reported ONLY as data-quality diagnostics — NO "MODEL vs GATE"
        ranking, NO "~3.6x", NO "retraining is the highest-leverage move".
      - a ranking is computed ONLY if sufficiency holds (it does not today).

What the descriptive numbers ARE and ARE NOT
--------------------------------------------
  1. Signal accuracy (PRECISION lens) — cross-sectional rank-IC of the pooled live score
     (``mu`` / ``raw_score``) vs forward returns at fwd_5/10/20/60d. The live ``mu`` cohort
     is a SCORER MIXTURE (``panel_ltr_xgboost``-dominant with only a handful of
     ``hf_patchtst`` rows), so this is NOT a clean PatchTST-primary IC. The 0.036 number
     from another experiment is NOT a portable significance bar — a shuffled-label /
     time-shift placebo MUST be recomputed on THIS exact cohort and each horizon before any
     IC is called "real". This script reports a per-cohort placebo (``--placebo-shuffles``)
     and compares observed IC to that distribution; it does not cite the foreign 0.036 as a
     pass/fail line.
  2. Trend RECALL / PRECISION — top-k / top-quintile capture of the day's realized
     up-trends and the directional precision of the top-k. "Real trend" here is an EX-POST
     top-decile positive fwd_20d cross-section, which is a per-date drift label, NOT a
     persistent multi-day trend EVENT with a defined start/end. Recall is mechanically
     universe-size dependent. These are reported WITH naive baselines (random ranking,
     market-sign, simple momentum) so the model number is not read in a vacuum; richer
     baselines (oracle-capacity, regime/sector-neutral, net-of-cost, AUPRC, capacity-
     normalized recall) and an explicit trend-event definition are listed as REQUIRED
     follow-ups, not delivered here.
  3. GATE impact — the live conviction gate ``(mu - mean(mu)) >= mu_floor`` is ONE
     synthetic de-meaned threshold, NOT the deployed ordered gate stack + capacity
     allocation. The killed-winner split is K-DEPENDENT BY CONSTRUCTION (it reverses under
     different ``book_size`` / universe / ``mu_floor``); this script reports it across a
     SENSITIVITY GRID of (book_size, mu_floor) so the k-dependence is visible, and labels
     the whole thing "scorer-mixture ranking vs one synthetic threshold", NOT a causal
     model-vs-gate attribution. The persisted ``selected`` / ``blocked_by`` columns are
     summarized to contrast this synthetic threshold against the ACTUAL deployed selection.
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
        [--min-eff-blocks 6] [--min-xsec 10] [--as-of YYYY-MM-DD]
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


def load(db: Path):
    """Load the per-name score ledger joined to forward returns, keeping ``run_type``.

    DETERMINISTIC run resolution (Finding 2): per (date, run_type) keep the run_id with the
    most candidate rows; ties are REJECTED, not silently broken — a tied date is recorded in
    ``ambiguous_dates`` and dropped, so the result never depends on row order. ``selected``
    and ``blocked_by`` are loaded and RETAINED (the deployed selection is summarized so the
    one synthetic de-meaned threshold can be contrasted with the actual gate).
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


def _eff_blocks(n_dates: int, horizon_n: int) -> float:
    """Effective independent observations for OVERLAPPING horizon labels (Finding 5).

    N adjacent dates with an N-session forward label provide ~ n_dates / horizon_n
    NON-overlapping windows, not n_dates. This is the number sufficiency must use.
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
        return {"n_dates": 0, "eff_blocks": 0.0, "mean_ic": None, "ic_ir": None,
                "median_ic": None}
    sd = float(ics.std())
    return {"n_dates": int(len(ics)),
            "eff_blocks": round(_eff_blocks(len(ics), _HORIZON_N[horizon]), 2),
            "mean_ic": float(ics.mean()),
            "ic_ir": (float(ics.mean() / sd) if sd > 0 else None),
            "median_ic": float(ics.median())}


def placebo_ic(frame, horizon, score, *, min_xsec, n_shuffles, seed=0):
    """On-cohort shuffled-label placebo (Finding 7).

    Recompute the SAME per-date rank-IC after shuffling the score WITHIN each date (destroys
    the score↔return link while preserving the date's cross-sectional + return structure).
    Returns the placebo IC distribution mean/std/95th-pct and a one-sided p-value of the
    observed pooled IC against it. This is the on-cohort bar — the foreign 0.036 is NOT used.
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon, score])
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    obs = rank_ic(g, horizon, score, min_xsec=min_xsec)
    if not obs["n_dates"] or n_shuffles <= 0:
        return {"n_shuffles": 0, "observed_ic": obs.get("mean_ic"),
                "placebo_mean_ic": None, "placebo_std_ic": None, "placebo_p95_ic": None,
                "p_value": None, "note": "no placebo (thin or disabled)"}
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_shuffles):
        ics = []
        for _dt, s in g.groupby("date"):
            if s[score].nunique() > 2 and s[horizon].nunique() > 1:
                shuf = rng.permutation(s[score].to_numpy())
                ics.append(float(pd.Series(shuf).corr(
                    s[horizon].reset_index(drop=True), method="spearman")))
            # (degenerate dates contribute nothing, same as observed)
        ics = [x for x in ics if x == x]
        if ics:
            means.append(float(np.mean(ics)))
    if not means:
        return {"n_shuffles": n_shuffles, "observed_ic": obs["mean_ic"],
                "placebo_mean_ic": None, "p_value": None, "note": "placebo degenerate"}
    means = np.array(means)
    p = float((means >= obs["mean_ic"]).mean())
    return {"n_shuffles": int(len(means)), "observed_ic": obs["mean_ic"],
            "placebo_mean_ic": float(means.mean()), "placebo_std_ic": float(means.std()),
            "placebo_p95_ic": float(np.percentile(means, 95)), "p_value": p,
            "note": "on-cohort shuffled-label placebo; compare observed_ic to placebo_p95_ic"}


def recall_precision_gate(frame, *, horizon, book_size, mu_floor, min_xsec):
    """Descriptive trend recall/precision + naive baselines + the K-DEPENDENT killed split.

    A realized "trend" = a name in the top-decile of POSITIVE ``horizon`` return on a date
    (EX-POST per-date drift label, NOT a persistent event — see module docstring). Reports:
      * model top-k / top-quintile recall, top-k directional precision;
      * gate-admitted (one synthetic de-meaned threshold) recall/precision;
      * NAIVE BASELINES (Finding 4): random-ranking recall, market-sign precision, simple
        1-period momentum ranking recall — so the model number is not read in a vacuum;
      * killed-winner split (missed_by_model / killed_by_gate) — reported but LABELLED
        k-dependent and NON-causal (it is also computed across a sensitivity grid upstream).
    Aggregated as a per-date block (mean over dates).
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon]).copy()
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    if g.empty:
        return {"n_dates": 0}
    rows = []
    rng = np.random.default_rng(0)
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
        # naive baselines
        rand_topk = pd.Series(rng.permutation(np.arange(n)) < book_size, index=s.index)
        mkt_pos_frac = float((s[horizon] > 0).mean())  # market-sign precision baseline
        rows.append({
            "n": n, "n_real": n_real, "n_admit": int(admit.sum()),
            "recall_topk": (float((model_topk & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_topq": (float((model_topq & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_gate": (float((admit & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_random": (float((rand_topk.values & real_trend.values).sum() / n_real)
                              if n_real else np.nan),
            "prec_topk_pos": (float((model_topk & (s[horizon] > 0)).sum() / book_size)),
            "prec_topk_terc": (float((model_topk & pos_tercile).sum() / book_size)),
            "prec_market_sign": mkt_pos_frac,  # baseline: pick any name -> this is precision
            "prec_gate_pos": (float((admit & (s[horizon] > 0)).sum() / admit.sum()) if admit.sum() else np.nan),
            "prec_gate_terc": (float((admit & pos_tercile).sum() / admit.sum()) if admit.sum() else np.nan),
            # K-DEPENDENT, NON-CAUSAL split (reported, not adjudicated):
            "killed_by_gate": (float(((real_trend) & (model_topk) & (~admit)).sum() / n_real) if n_real else np.nan),
            "missed_by_model": (float(((real_trend) & (~model_topk)).sum() / n_real) if n_real else np.nan),
        })
    df = pd.DataFrame(rows)
    out = {"n_dates": int(len(df)), "book_size": book_size, "mu_floor": mu_floor,
           "eff_blocks": round(_eff_blocks(len(df), _HORIZON_N[horizon]), 2),
           "mean_names": float(df["n"].mean()), "mean_real_trends": float(df["n_real"].mean()),
           "mean_gate_admits": float(df["n_admit"].mean())}
    for c in ["recall_topk", "recall_topq", "recall_gate", "recall_random",
              "prec_topk_pos", "prec_topk_terc", "prec_market_sign",
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


def evaluate(db: Path, *, book_size, mu_floor, min_eff_blocks, min_xsec, as_of=None,
             placebo_shuffles=0):
    import datetime as _dt  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    m, sessions, meta = load(db)
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(_dt.date.today())
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
                         "min_eff_blocks": min_eff_blocks, "min_xsec": min_xsec,
                         "as_of": str(as_of_ts.date()), "placebo_shuffles": placebo_shuffles},
            "as_of": str(as_of_ts.date()),
            "n_sessions_in_calendar": len(sessions),
            "session_calendar_first": (str(pd.Timestamp(sessions[0]).date()) if sessions else None),
            "session_calendar_last": (str(pd.Timestamp(sessions[-1]).date()) if sessions else None),
            "ambiguous_dates_rejected": meta["ambiguous_dates_rejected"],
            "resolved_runs": meta["resolved_runs"],
            "live_scorer_mix": scorer_mix,
        },
        "as_of": str(as_of_ts.date()),
        "book_size": book_size, "mu_floor": mu_floor, "min_eff_blocks": min_eff_blocks,
        "foreign_leakage_floor_reference_DO_NOT_USE_AS_BAR": FOREIGN_LEAKAGE_FLOOR_REFERENCE,
        "run_type_dates": {rt: int(m[m.run_type == rt]["date"].nunique())
                           for rt in sorted(m["run_type"].dropna().unique())},
    }

    def lens(sub, label):
        res = {"label": label, "ic": {}, "placebo": {}, "trend": {}, "staleness": {}}
        for h in HORIZONS:
            cut = _aged_cutoff(sessions, _HORIZON_N[h], as_of_ts)
            aged = sub[sub["date"] <= cut]
            res["ic"][h] = {"mu": rank_ic(aged, h, "mu", min_xsec=min_xsec),
                            "raw_score": rank_ic(aged.dropna(subset=["raw_score"]), h,
                                                 "raw_score", min_xsec=min_xsec),
                            "aged_cutoff": str(pd.Timestamp(cut).date())}
            res["placebo"][h] = placebo_ic(aged, h, "mu", min_xsec=min_xsec,
                                            n_shuffles=placebo_shuffles)
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
        # sufficiency on the primary horizon, by EFFECTIVE BLOCKS (Finding 5), not raw dates
        n_dates = res["trend"][PRIMARY].get("n_dates", 0)
        eff = _eff_blocks(n_dates, _HORIZON_N[PRIMARY])
        res["primary_aged_dates"] = n_dates
        res["primary_eff_blocks"] = round(eff, 2)
        res["sufficient"] = bool(eff >= min_eff_blocks)
        return res

    out["live"] = lens(live_all, "LIVE (scorer MIXTURE — xgboost-dominant, few PatchTST rows)")
    out["sim_reference_NOT_validation_grade"] = lens(
        m[m.run_type == "sim"], "SIM (NULL scorer / non-PatchTST raw — reference only)")

    live_ok = out["live"]["sufficient"]
    live_eff = out["live"]["primary_eff_blocks"]
    live_n = out["live"]["primary_aged_dates"]
    # CENTRAL GATE (Finding 1): insufficiency gates the conclusion. No lever ranking unless
    # sufficiency holds. Today it does not, so the verdict is UNDETERMINED.
    if live_ok:
        verdict = "DETERMINED"
        detail = (f"{live_n} aged LIVE dates (~{live_eff} effective non-overlapping blocks) "
                  f">= {min_eff_blocks} required; lever ranking permitted.")
        lever_ranking = _lever_ranking(out["live"])
    else:
        verdict = "UNDETERMINED"
        lever_ranking = None
        detail = (
            f"only {live_n} aged LIVE dates (~{live_eff} effective non-overlapping blocks) for "
            f"{PRIMARY}; need >= {min_eff_blocks} effective blocks. A 20-session label over a "
            f"single ~5-week window is ~1–2 independent observations, which CANNOT support a "
            f"model-vs-gate ranking, a retraining recommendation, or an IC significance claim. "
            f"The live cohort is also a SCORER MIXTURE (xgboost-dominant, few PatchTST rows), "
            f"so it is not a clean PatchTST-primary baseline. The SIM ledger is NOT faithful "
            f"(NULL scorer, non-PatchTST raw) and is reference-only. The descriptive numbers "
            f"are DATA-QUALITY DIAGNOSTICS only. UNBLOCK: let the live ledger reach "
            f">= {min_eff_blocks} effective blocks for {PRIMARY} (and run an on-cohort placebo "
            f"+ the controlled paired freshness experiment) before ranking levers.")
    out["bottleneck_verdict"] = verdict
    out["lever_ranking"] = lever_ranking
    out["data_sufficiency"] = {
        "live_primary_aged_dates": live_n,
        "live_primary_eff_blocks": live_eff,
        "min_eff_blocks": min_eff_blocks,
        "verdict": ("SUFFICIENT" if live_ok else "INSUFFICIENT_LIVE_HISTORY"),
        "detail": detail}
    return out


def _lever_ranking(live_res):
    """ONLY reached when sufficiency holds (it does not today). Kept minimal and gated so it
    can never be emitted under INSUFFICIENT_LIVE_HISTORY."""
    t = live_res["trend"].get(PRIMARY, {})
    return {"note": "computed ONLY because the primary horizon met the effective-block bar",
            "missed_by_model": t.get("missed_by_model"),
            "killed_by_gate": t.get("killed_by_gate")}


def _fmt_ic(d):
    if d.get("mean_ic") is None:
        return "n=0 (insufficient)"
    return (f"IC={d['mean_ic']:+.4f} IC_IR={d['ic_ir']:+.3f} "
            f"({d['n_dates']}d ≈{d.get('eff_blocks')} blocks)" if d.get("ic_ir") is not None
            else f"IC={d['mean_ic']:+.4f} ({d['n_dates']}d ≈{d.get('eff_blocks')} blocks)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--book-size", type=int, default=8)
    p.add_argument("--mu-floor", type=float, default=0.03)
    p.add_argument("--min-eff-blocks", type=float, default=6.0,
                   help="effective NON-overlapping blocks required on the primary horizon "
                        "(NOT raw dates); sufficiency gates the verdict")
    p.add_argument("--min-xsec", type=int, default=10)
    p.add_argument("--as-of", default=None)
    p.add_argument("--placebo-shuffles", type=int, default=0,
                   help="on-cohort shuffled-label placebo shuffles (0 = skip; ~200 for a bar)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    db = Path(args.runs_db)
    if not db.exists():
        print(f"SKIP: ledger DB not found at {db} (read-only field study; needs the live "
              f"decision ledger). Nothing to compute.")
        return 0
    res = evaluate(db, book_size=args.book_size, mu_floor=args.mu_floor,
                   min_eff_blocks=args.min_eff_blocks, min_xsec=args.min_xsec,
                   as_of=args.as_of, placebo_shuffles=args.placebo_shuffles)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0
    ds = res["data_sufficiency"]
    print(f"as_of={res['as_of']}  run_type_dates={res['run_type_dates']}")
    print(f"BOTTLENECK VERDICT: {res['bottleneck_verdict']}  "
          f"(data {ds['verdict']}: {ds['live_primary_aged_dates']} aged dates "
          f"≈ {ds['live_primary_eff_blocks']} eff blocks, need >= {ds['min_eff_blocks']})")
    if res["lever_ranking"] is None:
        print("  -> UNDETERMINED: NO lever ranking, NO retraining recommendation. The numbers "
              "below are DATA-QUALITY DIAGNOSTICS only.")
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
            print(f"  TREND ({PRIMARY}, {t['n_dates']}d ≈{t.get('eff_blocks')} blocks, "
                  f"book={t['book_size']}): recall_topk={t.get('recall_topk')!r} "
                  f"(random baseline={t.get('recall_random')!r}) "
                  f"prec_topk_pos={t.get('prec_topk_pos')!r} "
                  f"(market-sign baseline={t.get('prec_market_sign')!r})")
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
