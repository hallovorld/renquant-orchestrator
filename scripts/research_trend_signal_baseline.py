#!/usr/bin/env python3
"""Read-only BASELINE for renquant105's goal: catch MORE (recall) and MORE-ACCURATE
(precision) multi-period TREND signals — and locate the bottleneck (MODEL vs GATE).

renquant105's real objective is multi-period DIRECTIONAL trend signal quality, not a
single deployment knob. This study measures, from the now-wired decision ledger
(``data/runs.alpaca.db``) and entirely READ-ONLY, where the system stands today on three
axes and which one is the binding constraint:

  1. Signal accuracy (PRECISION lens) — cross-sectional rank-IC of the model score
     (``raw_score`` and calibrated ``mu``) vs forward returns at fwd_5/10/20/60d, pooled
     and per-date (mean ± IC_IR), compared to the documented ~0.036 shuffled-label
     leakage floor (doc/.../wf-gate-embargo-leakage-floor).
  2. Trend RECALL — of the realized up-trends on a date (top-decile positive fwd_20d),
     what fraction does the model rank in its top-k (book size k) / top-quintile?
  3. Trend PRECISION — of the model's top-k ranked names, what fraction realized a
     positive / top-tercile fwd_20d?
  4. GATE impact — apply the live conviction gate
     ``(mu - cross_sectional_mean(mu)) >= mu_floor`` (mu_floor=0.03, demean=True). Of the
     realized up-trends, how many does the GATE throw away, and decompose recall loss into
     (a) the model ranked them low vs (b) the gate rejected model-ranked-high names. This
     is the MODEL-bottleneck-vs-GATE-bottleneck answer.
  5. STALENESS — rank-IC split recent vs older to size the freshness/retrain lever.

CRITICAL DATA-SUFFICIENCY GATE (do not fabricate)
-------------------------------------------------
The faithful, production-scorer cross-section is the LIVE ledger (``run_type='live'``,
one run per date, a single ``mu`` per ticker). The SIM ledger (``run_type='sim'``) is NOT
a faithful per-name production-PatchTST history: ``model_type``/``active_scorer`` are NULL
on every sim row, ``raw_score`` ranges to >+200 (not PatchTST-native, which is
intrinsically negative ~-0.198), and a date carries far MORE distinct ``mu`` values than
tickers (multiple conflicting sim run_ids per name/date). So this study reports the SIM
numbers ONLY as a clearly-labelled, NOT-validation-grade reference and bases every verdict
on the LIVE subset. ``fwd_20d`` (the primary trend horizon) and especially ``fwd_60d`` need
20 / 60 TRADING SESSIONS to elapse; the faithful live ledger only began ~2026-05-04, so the
live realized-trend window is a few weeks — the study reports the actual aged-date count and
STOPS short of a fabricated baseline when it is below ``--min-dates``.

Aging is enforced by TRADING SESSIONS, not calendar days (an fwd_Nd label is a shift(-N)
over daily bars; N sessions != N calendar days), against the ledger's own session calendar
(distinct ``ticker_forward_returns.as_of_date``).

Read-only. The DB is opened ``mode=ro``; the script never writes to any canonical path.
Usage:
    research_trend_signal_baseline.py [--runs-db PATH] [--book-size 8] [--mu-floor 0.03]
        [--min-dates 30] [--min-xsec 10] [--as-of YYYY-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/renhao/git/github/RenQuant")
DEF_DB = REPO / "data" / "runs.alpaca.db"
HORIZONS = ["fwd_5d", "fwd_10d", "fwd_20d", "fwd_60d"]
PRIMARY = "fwd_20d"
# documented shuffled-label / embargo leakage floor (MEMORY: wf-gate-embargo-leakage-floor)
LEAKAGE_FLOOR = 0.036


def _connect_ro(db: Path):
    """Open the ledger strictly read-only (never mutate a canonical path)."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def load(db: Path):
    """Load the per-name score ledger joined to forward returns, keeping ``run_type``.

    One run per (date, run_type): the run_id with the most candidate rows (the full pool),
    so a date is not weighted by how many times it was re-run. Returns the merged frame plus
    the session calendar (sorted distinct forward-return as_of dates).
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
    con.close()
    cs["date"] = pd.to_datetime(cs["run_date"], errors="coerce")
    fr["date"] = pd.to_datetime(fr["date"], errors="coerce")
    cs = cs.dropna(subset=["date"])
    n = cs.groupby(["date", "run_type", "run_id"]).size().reset_index(name="n")
    main = n.sort_values("n").groupby(["date", "run_type"]).tail(1)
    cs = cs.merge(main[["date", "run_type", "run_id"]], on=["date", "run_type", "run_id"])
    sessions = sorted(fr["date"].dropna().unique())
    m = cs.merge(fr, on=["date", "ticker"], how="left")
    return m, sessions


def _aged_cutoff(sessions, horizon_n: int, as_of):
    """Newest date whose ``horizon_n``-session label is fully realized as of ``as_of``."""
    import pandas as pd  # noqa: PLC0415
    as_of_ts = pd.Timestamp(as_of)
    idx = pd.DatetimeIndex([s for s in sessions if pd.Timestamp(s) <= as_of_ts])
    if len(idx) > horizon_n:
        return idx[-(horizon_n + 1)]
    return (idx[0] - pd.Timedelta(days=1)) if len(idx) else as_of_ts


_HORIZON_N = {"fwd_5d": 5, "fwd_10d": 10, "fwd_20d": 20, "fwd_60d": 60}


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
        return {"n_dates": 0, "mean_ic": None, "ic_ir": None, "median_ic": None}
    sd = float(ics.std())
    return {"n_dates": int(len(ics)), "mean_ic": float(ics.mean()),
            "ic_ir": (float(ics.mean() / sd) if sd > 0 else None),
            "median_ic": float(ics.median()),
            "above_leakage_floor": bool(ics.mean() > LEAKAGE_FLOOR)}


def recall_precision_gate(frame, *, horizon, book_size, mu_floor, min_xsec):
    """Trend recall/precision for the model ranking AND the gate-admitted set.

    A realized "trend" = a name in the top-decile of POSITIVE ``horizon`` return on a date.
    For each aged date with >= ``min_xsec`` realized names:
      * model top-k = the ``book_size`` highest-``mu`` names; top-quintile likewise.
      * gate-admitted = ``(mu - mean(mu)) >= mu_floor`` (demean=True), the live rule.
    Recall = fraction of real trends caught; precision = fraction of caught that are real.
    Killed-winners: real trends the model RANKED HIGH (top-k) but the GATE rejected, vs real
    trends the model ranked LOW (model bottleneck). Aggregated as a per-date block (mean over
    dates), so a uniform per-date offset cancels and dates (not rows) are the unit.
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = frame.dropna(subset=[horizon]).copy()
    g = g[g.groupby("date")["ticker"].transform("count") >= min_xsec]
    if g.empty:
        return {"n_dates": 0}
    rows = []
    for _dt, s in g.groupby("date"):
        s = s.copy()
        n = len(s)
        dec_n = max(1, int(round(n * 0.10)))
        quint_n = max(1, int(round(n * 0.20)))
        # realized up-trends: positive return AND in the top-decile of the day
        ret_rank = s[horizon].rank(ascending=False, method="first")
        real_trend = (s[horizon] > 0) & (ret_rank <= dec_n)
        n_real = int(real_trend.sum())
        # model ranking by mu
        mu_rank = s["mu"].rank(ascending=False, method="first")
        model_topk = mu_rank <= book_size
        model_topq = mu_rank <= quint_n
        # live gate
        dem = s["mu"] - s["mu"].mean()
        admit = dem >= mu_floor
        pos_tercile = s[horizon] > s[horizon].quantile(2 / 3)
        rows.append({
            "n": n, "n_real": n_real, "n_admit": int(admit.sum()),
            "recall_topk": (float((model_topk & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_topq": (float((model_topq & real_trend).sum() / n_real) if n_real else np.nan),
            "recall_gate": (float((admit & real_trend).sum() / n_real) if n_real else np.nan),
            # precision: of model top-k / gate admits, fraction realized positive & top-tercile
            "prec_topk_pos": (float((model_topk & (s[horizon] > 0)).sum() / book_size)),
            "prec_topk_terc": (float((model_topk & pos_tercile).sum() / book_size)),
            "prec_gate_pos": (float((admit & (s[horizon] > 0)).sum() / admit.sum()) if admit.sum() else np.nan),
            "prec_gate_terc": (float((admit & pos_tercile).sum() / admit.sum()) if admit.sum() else np.nan),
            # KILLED-WINNER decomposition (real trends lost):
            #  gate-bottleneck = real trend, model ranked top-k, gate rejected
            #  model-bottleneck = real trend, model ranked OUTSIDE top-k
            "killed_by_gate": (float(((real_trend) & (model_topk) & (~admit)).sum() / n_real) if n_real else np.nan),
            "missed_by_model": (float(((real_trend) & (~model_topk)).sum() / n_real) if n_real else np.nan),
        })
    df = pd.DataFrame(rows)
    out = {"n_dates": int(len(df)), "book_size": book_size, "mu_floor": mu_floor,
           "mean_names": float(df["n"].mean()), "mean_real_trends": float(df["n_real"].mean()),
           "mean_gate_admits": float(df["n_admit"].mean())}
    for c in ["recall_topk", "recall_topq", "recall_gate", "prec_topk_pos", "prec_topk_terc",
              "prec_gate_pos", "prec_gate_terc", "killed_by_gate", "missed_by_model"]:
        v = df[c].dropna()
        out[c] = float(v.mean()) if len(v) else None
    return out


def evaluate(db: Path, *, book_size, mu_floor, min_dates, min_xsec, as_of=None):
    import datetime as _dt  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    m, sessions = load(db)
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(_dt.date.today())
    out = {"as_of": str(as_of_ts.date()), "leakage_floor": LEAKAGE_FLOOR,
           "book_size": book_size, "mu_floor": mu_floor, "min_dates": min_dates,
           "run_type_dates": {rt: int(m[m.run_type == rt]["date"].nunique())
                              for rt in sorted(m["run_type"].dropna().unique())},
           "live_scorer_mix": {}}
    live_all = m[m.run_type == "live"]
    if len(live_all):
        out["live_scorer_mix"] = {str(k): int(v) for k, v in
                                  live_all["model_type"].fillna("None").value_counts().items()}

    def lens(sub, label):
        res = {"label": label, "ic": {}, "trend": {}, "staleness": {}}
        for h in HORIZONS:
            cut = _aged_cutoff(sessions, _HORIZON_N[h], as_of_ts)
            aged = sub[sub["date"] <= cut]
            res["ic"][h] = {"mu": rank_ic(aged, h, "mu", min_xsec=min_xsec),
                            "raw_score": rank_ic(aged.dropna(subset=["raw_score"]), h,
                                                 "raw_score", min_xsec=min_xsec),
                            "aged_cutoff": str(pd.Timestamp(cut).date())}
        cut = _aged_cutoff(sessions, _HORIZON_N[PRIMARY], as_of_ts)
        aged_p = sub[sub["date"] <= cut]
        res["trend"][PRIMARY] = recall_precision_gate(
            aged_p, horizon=PRIMARY, book_size=book_size, mu_floor=mu_floor, min_xsec=min_xsec)
        # staleness: split primary-horizon IC dates into older vs recent halves
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
                "older_mean_ic": float(older.mean()), "older_n": len(older),
                "recent_mean_ic": float(recent.mean()), "recent_n": len(recent),
                "recent_minus_older": float(recent.mean() - older.mean())}
        else:
            res["staleness"][PRIMARY] = {"status": "thin", "n_dates": len(ic_dates)}
        # sufficiency on the primary horizon
        np = res["trend"][PRIMARY].get("n_dates", 0)
        res["primary_aged_dates"] = np
        res["sufficient"] = bool(np >= min_dates)
        return res

    out["live"] = lens(live_all, "LIVE (faithful production scorer)")
    out["sim_reference_NOT_validation_grade"] = lens(
        m[m.run_type == "sim"], "SIM (NULL scorer / non-PatchTST raw — reference only)")

    live_ok = out["live"]["sufficient"]
    live_n = out["live"]["primary_aged_dates"]
    if live_ok:
        detail = f"{live_n} aged LIVE dates with realized {PRIMARY} >= {min_dates}."
    else:
        detail = (
            f"only {live_n} aged LIVE dates have a realized {PRIMARY} "
            f"(need >= {min_dates}); the faithful live ledger began ~2026-05-04 and a {PRIMARY} "
            f"label needs 20 trading sessions to elapse, so the realized-trend window is still a "
            f"few weeks. The SIM ledger is NOT a faithful production-PatchTST per-name history "
            f"(NULL model_type/active_scorer, non-PatchTST raw_score) and is reported as reference "
            f"only. UNBLOCK: let the live ledger age (~mid-Aug-2026 for >=30 aged {PRIMARY} dates) "
            f"or wire faithful per-name PatchTST score history (#133 follow-through).")
    out["data_sufficiency"] = {
        "live_primary_aged_dates": live_n,
        "min_dates": min_dates,
        "verdict": ("SUFFICIENT" if live_ok else "INSUFFICIENT_LIVE_HISTORY"),
        "detail": detail}
    return out


def _fmt_ic(d):
    if d.get("mean_ic") is None:
        return "n=0 (insufficient)"
    fl = " >floor" if d.get("above_leakage_floor") else " <=floor"
    return (f"IC={d['mean_ic']:+.4f} IC_IR={d['ic_ir']:+.3f} "
            f"({d['n_dates']}d){fl}" if d.get("ic_ir") is not None
            else f"IC={d['mean_ic']:+.4f} ({d['n_dates']}d){fl}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--book-size", type=int, default=8)
    p.add_argument("--mu-floor", type=float, default=0.03)
    p.add_argument("--min-dates", type=int, default=30)
    p.add_argument("--min-xsec", type=int, default=10)
    p.add_argument("--as-of", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    db = Path(args.runs_db)
    if not db.exists():
        # CI / no-DB guard: this is a read-only field study over the live ledger.
        print(f"SKIP: ledger DB not found at {db} (read-only field study; needs the live "
              f"decision ledger). Nothing to compute.")
        return 0
    res = evaluate(db, book_size=args.book_size, mu_floor=args.mu_floor,
                   min_dates=args.min_dates, min_xsec=args.min_xsec, as_of=args.as_of)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
        return 0
    ds = res["data_sufficiency"]
    print(f"as_of={res['as_of']}  run_type_dates={res['run_type_dates']}")
    print(f"DATA SUFFICIENCY (live, primary {PRIMARY}): {ds['verdict']} "
          f"({ds['live_primary_aged_dates']} aged dates, need >= {ds['min_dates']})")
    for key in ("live", "sim_reference_NOT_validation_grade"):
        r = res[key]
        print(f"\n=== {r['label']} ===")
        for h in HORIZONS:
            mu = r["ic"][h]["mu"]
            raw = r["ic"][h]["raw_score"]
            print(f"  {h}: mu {_fmt_ic(mu)} | raw {_fmt_ic(raw)}")
        t = r["trend"][PRIMARY]
        if t.get("n_dates"):
            print(f"  TREND ({PRIMARY}, {t['n_dates']}d, book={t['book_size']}): "
                  f"recall_topk={t.get('recall_topk')!r} recall_gate={t.get('recall_gate')!r} "
                  f"prec_topk_pos={t.get('prec_topk_pos')!r}")
            print(f"    KILLED-WINNER decomp: missed_by_model={t.get('missed_by_model')!r} "
                  f"killed_by_gate={t.get('killed_by_gate')!r} "
                  f"(mean real trends/date={t.get('mean_real_trends')!r}, "
                  f"gate admits/date={t.get('mean_gate_admits')!r})")
        st = r["staleness"].get(PRIMARY, {})
        if "recent_minus_older" in st:
            print(f"    STALENESS ({PRIMARY} IC): older={st['older_mean_ic']:+.4f} "
                  f"recent={st['recent_mean_ic']:+.4f} Δ={st['recent_minus_older']:+.4f}")
    print(f"\n>>> {ds['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
