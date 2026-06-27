#!/usr/bin/env python3
"""Read-only ledger test of the CrossSectionalPanelExit (`panel_conviction_xs`) rule.

The rule (renquant-pipeline ``task_panel_conviction_xs.py``) exits a held name when it is in
the bottom ``xs_panel_percentile_floor`` (0.20) of today's panel-score cross-section AND
``mu <= mu_sell_ceiling`` (0.0) — the AND-rule — or when ``mu <= mu_strong_sell_ceiling`` (-0.05)
alone (the OR-bypass). It is σ-blind, runs pre-QP, and overrides the QP. Question: does the
AND-rule's "bottom-20% + mu<=0" trigger (AMZN's 2026-06-25 case) actually predict forward
underperformance, and does that depend on the regime — in particular, does it MIS-FIRE in
BULL_CALM (today's regime), as an earlier XGB-proxy + small covid-cut PatchTST analysis claimed?

Why this is a rewrite (Codex review on PR #195)
------------------------------------------------
The previous version TRAINED an ``XGBRegressor`` inside ``renquant-orchestrator`` and leaned on
an uncommitted ad-hoc PatchTST cut. Both violate this repo's boundary (it orchestrates; it does
not implement model-training / signal internals) and were not reproducible. This rewrite is
READ-ONLY over the now-wired decision ledger (``data/runs.alpaca.db``): it joins the REAL live/sim
``panel_score`` + ``mu`` that the pipeline actually scored (``candidate_scores``) to REALIZED
forward returns (``ticker_forward_returns``), keyed by run date. No model is trained here; the
panel scores are the pinned scorer's own outputs.

Method (leakage-robust, dependence-aware — Codex #3)
----------------------------------------------------
* ONE run per date (the full-pool run with the most candidate rows) so a date is not weighted by
  how many times it was re-run.
* All statistics are WITHIN-DATE and aggregated as a PER-DATE BLOCK: each trading date contributes
  one number (e.g. the within-date mean-fwd gap between the AND-fired names and the names you would
  keep), and the reported t-stat is mean / SEM **over dates**. A uniform per-date level/leakage
  offset cancels inside each date, and treating each date (not each overlapping ``(date,ticker)``
  row) as the unit of inference avoids the anti-conservative row bootstrap the prior version used.
  The effective sample is the number of independent dates, reported per regime.
* Regime is the pipeline's own per-run label (``pipeline_runs.regime``), so the BULL_CALM split is
  the live regime tag, not a re-derived argmax.

Read-only. Usage:
    research_panel_exit_predictiveness.py [--runs-db PATH] [--horizon 60] [--floor 0.20]
        [--mu-ceiling 0.0] [--min-xsec 8] [--json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

REPO = Path("/Users/renhao/git/github/RenQuant")
DEF_DB = REPO / "data" / "runs.alpaca.db"
# Regimes are reported in this order; BULL_CALM first because it is the PR's question.
REGIME_ORDER = ["BULL_CALM", "BULL_VOLATILE", "BEAR", "CHOPPY"]


def load_panel_ledger(db: Path, horizon: int):
    """Read-only join of REAL panel_score + mu to realized forward returns, one run per date."""
    import pandas as pd  # noqa: PLC0415

    fwd = f"fwd_{horizon}d"
    con = sqlite3.connect(str(db))
    cols = {r[1] for r in con.execute("PRAGMA table_info(ticker_forward_returns)")}
    if fwd not in cols:
        con.close()
        raise ValueError(f"{fwd} not in ticker_forward_returns ({sorted(cols)})")
    df = pd.read_sql(
        f"""
        SELECT cs.run_id, pr.run_date AS date, pr.regime, cs.ticker,
               cs.panel_score, cs.mu, t.{fwd} AS fwd
        FROM candidate_scores cs
        JOIN pipeline_runs pr ON cs.run_id = pr.run_id
        JOIN ticker_forward_returns t
             ON t.as_of_date = pr.run_date AND t.ticker = cs.ticker
        WHERE cs.panel_score IS NOT NULL AND cs.mu IS NOT NULL AND t.{fwd} IS NOT NULL
        """,
        con,
    )
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    # one run per date: the run with the most candidate rows (the full pool)
    sz = df.groupby(["date", "run_id"]).size().reset_index(name="n")
    keep = sz.sort_values("n").groupby("date").tail(1)[["date", "run_id"]]
    return df.merge(keep, on=["date", "run_id"])


def _block_stat(per_date_vals) -> dict:
    """Per-date block stat: mean over dates, t = mean / SEM over dates, n = #dates."""
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    x = pd.Series([v for v in per_date_vals if np.isfinite(v)], dtype=float)
    sem = float(x.sem()) if len(x) > 1 else 0.0
    return {
        "mean": (float(x.mean()) if len(x) else None),
        "t": (float(x.mean() / sem) if sem > 0 else None),
        "n_dates": int(len(x)),
        "pct_days_negative": (float((x < 0).mean()) if len(x) else None),
    }


def _within_date_gaps(g, floor: float, mu_ceiling: float):
    """Per-date: (AND-fired mean fwd − kept mean fwd), and per-date rank-IC(panel, fwd)."""
    import numpy as np  # noqa: PLC0415

    gaps, ics, fired_minus_median = [], [], []
    for _dt, s in g.groupby("date"):
        s = s.copy()
        s["pctile"] = s["panel_score"].rank(pct=True)
        fired = s[(s["pctile"] < floor) & (s["mu"] <= mu_ceiling)]["fwd"]
        kept = s[~((s["pctile"] < floor) & (s["mu"] <= mu_ceiling))]["fwd"]
        if len(fired) >= 1 and len(kept) >= 1:
            gaps.append(float(fired.mean() - kept.mean()))
            fired_minus_median.append(float(fired.mean() - s["fwd"].median()))
        if s["panel_score"].nunique() > 2:
            ics.append(float(s[["panel_score", "fwd"]].corr("spearman").iloc[0, 1]))
    return gaps, ics, fired_minus_median


def evaluate(db: Path, horizon: int = 60, floor: float = 0.20,
             mu_ceiling: float = 0.0, min_xsec: int = 8) -> dict:
    """Per-regime within-date predictiveness of the AND-rule exit trigger. Read-only."""
    df = load_panel_ledger(db, horizon)
    df = df[df.groupby("date")["ticker"].transform("count") >= min_xsec].copy()
    out = {
        "horizon_days": horizon, "bottom_floor": floor, "mu_ceiling": mu_ceiling,
        "min_xsec": min_xsec, "ledger_dates": int(df["date"].nunique()),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())]
        if len(df) else [None, None],
        "by_regime": {},
    }
    for reg in ["ALL", *REGIME_ORDER]:
        sub = df if reg == "ALL" else df[df["regime"] == reg]
        if sub.empty:
            out["by_regime"][reg] = {"n_dates": 0, "status": "no_data"}
            continue
        gaps, ics, fmm = _within_date_gaps(sub, floor, mu_ceiling)
        gap = _block_stat(gaps)
        rec = {
            # within-date: AND-fired names' fwd minus the names you would keep
            "and_fired_minus_kept_fwd": gap,
            # within-date: AND-fired names' fwd minus the median name you'd hold instead
            "and_fired_minus_median_fwd": _block_stat(fmm),
            # per-date Spearman(panel_score, fwd): does the panel rank forward returns at all?
            "xsection_rank_ic": _block_stat(ics),
        }
        m = gap["mean"]
        t = gap["t"]
        if m is None or t is None or gap["n_dates"] < 8:
            rec["reading"] = "thin coverage — not decision-grade"
        elif m < 0 and t < -2:
            rec["reading"] = "exit PREDICTIVE (AND-fired names significantly underperform)"
        elif m > 0 and t > 2:
            rec["reading"] = "exit INVERTED (AND-fired names OUTperform — exiting loses alpha)"
        else:
            rec["reading"] = "exit NOT predictive (gap CI/sign not significant)"
        out["by_regime"][reg] = rec

    bc = out["by_regime"].get("BULL_CALM", {})
    bc_gap = bc.get("and_fired_minus_kept_fwd", {})
    out["bull_calm_verdict"] = (
        "BULL_CALM_MISFIRE" if (bc_gap.get("mean") is not None and bc_gap.get("t") is not None
                                and not (bc_gap["mean"] < 0 and bc_gap["t"] < -2))
        else "BULL_CALM_PREDICTIVE")
    out["caveat"] = (
        "within-date per-date-block inference over the live/sim ledger (1 run/date); regime is the "
        "pipeline's own per-run tag. The σ-blind / QP-override portfolio critique (the rule dumps "
        "low-σ ballast the QP wants to keep) is SEPARATE from this predictiveness test and is not "
        "settled by it. A pipeline change still needs a path-dependent shadow replay.")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--horizon", type=int, default=60)
    p.add_argument("--floor", type=float, default=0.20)
    p.add_argument("--mu-ceiling", type=float, default=0.0)
    p.add_argument("--min-xsec", type=int, default=8)
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    res = evaluate(Path(args.runs_db), args.horizon, args.floor,
                   args.mu_ceiling, args.min_xsec)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"ledger_dates={res['ledger_dates']}  range={res['date_range'][0]}..{res['date_range'][1]}"
          f"  horizon={res['horizon_days']}d  floor={res['bottom_floor']}  mu_ceiling={res['mu_ceiling']}")
    print("\nAND-rule (bottom-{:.0%} panel AND mu<={}) exited names vs the names you'd KEEP, "
          "within-date, per-regime:".format(res["bottom_floor"], res["mu_ceiling"]))
    for reg, rec in res["by_regime"].items():
        if rec.get("status") == "no_data" or rec.get("n_dates") == 0:
            print(f"  [{reg:13s}] no data")
            continue
        g = rec["and_fired_minus_kept_fwd"]
        if g["mean"] is None:
            print(f"  [{reg:13s}] thin")
            continue
        ic = rec["xsection_rank_ic"]
        print(f"  [{reg:13s}] fired−kept fwd{res['horizon_days']} = {g['mean']:+.4f} "
              f"(t={g['t']:+.2f}, {g['n_dates']}d, {100*g['pct_days_negative']:.0f}% days fired<kept)  "
              f"rank-IC={ic['mean']:+.3f}  → {rec['reading']}")
    print(f"\nBULL_CALM verdict: {res['bull_calm_verdict']}")
    print(f"⚠ {res['caveat']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
