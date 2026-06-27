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

Method (leakage-robust, dependence-aware, aging-enforced — Codex #195 r1 #3, r2 #1/#2)
--------------------------------------------------------------------------------------
* ONE run per date (the full-pool run with the most candidate rows) so a date is not weighted by
  how many times it was re-run.
* TRADING-SESSION AGING (``--as-of``, Codex r2 #2). ``fwd_60d`` is a 60-TRADING-SESSION label
  (a ``shift(-60)`` over daily bars), NOT a 60-calendar-day label — 60 sessions ≈ 84 calendar
  days. A row can carry a non-NULL ``fwd_60d`` that was written before its full horizon elapsed,
  so ``fwd_60d IS NOT NULL`` alone does NOT prove a date is aged. We age against the ledger's own
  session calendar (the sorted distinct ``ticker_forward_returns.as_of_date`` — exactly the bars
  the label is defined over): a ledger date is aged iff >= ``horizon`` later sessions fall in
  ``(date, as_of]``. That is the ``horizon``-th session counting back from ``as_of``.
* All statistics are WITHIN-DATE and aggregated as a PER-DATE BLOCK: each trading date contributes
  one number (e.g. the within-date mean-fwd gap between the AND-fired names and the names you would
  keep). A uniform per-date level/leakage offset cancels inside each date, and treating each date
  (not each overlapping ``(date,ticker)`` row) as the unit of inference avoids the anti-conservative
  row bootstrap the first version used.
* DEPENDENCE (Codex r2 #1). Adjacent dates' 60-session forward windows heavily OVERLAP and share
  common regime/market shocks, so the per-date block series is NOT iid — ``mean / SEM over dates``
  still overstates significance. Significance is therefore reported via a MOVING-BLOCK BOOTSTRAP
  (block = the label horizon in sessions, the span of the overlap); the naive iid t is retained
  only as a labelled, known-anti-conservative reference. A regime is called PREDICTIVE/INVERTED
  only when the block-bootstrap 95% CI excludes zero.
* Regime is the pipeline's own per-run label (``pipeline_runs.regime``), so the BULL_CALM split is
  the live regime tag, not a re-derived argmax.

This is an EXPLORATORY DIAGNOSTIC: the ledger evidence SUGGESTS a direction; it is not a
deployment decision. A pipeline change still requires the path-dependent shadow replay below.

Read-only. Usage:
    research_panel_exit_predictiveness.py [--runs-db PATH] [--horizon 60] [--floor 0.20]
        [--mu-ceiling 0.0] [--min-xsec 8] [--as-of YYYY-MM-DD] [--json]
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


def _session_calendar(con, horizon: int):
    """Sorted distinct ``ticker_forward_returns.as_of_date`` = the bars the label is defined over.

    The 60-session ``fwd_60d`` label is a ``shift(-60)`` over these bars, so this table's own
    date index IS the trading-session calendar we age against.
    """
    import pandas as pd  # noqa: PLC0415

    s = pd.read_sql("SELECT DISTINCT as_of_date FROM ticker_forward_returns ORDER BY as_of_date", con)
    return pd.DatetimeIndex(pd.to_datetime(s["as_of_date"]))


def _aged_cutoff(session_idx, horizon: int, as_of):
    """The newest ledger date whose full ``horizon``-session label has elapsed by ``as_of``.

    A date is aged iff >= ``horizon`` later sessions fall in ``(date, as_of]`` — i.e. it is at
    least the ``horizon``-th session counting back from ``as_of``. Returns a Timestamp cutoff;
    ledger dates ``<= cutoff`` are fully aged.
    """
    import pandas as pd  # noqa: PLC0415

    sidx = session_idx[session_idx <= as_of]
    if len(sidx) > horizon:
        return sidx[-(horizon + 1)]
    # not enough sessions have elapsed for ANY date to be aged
    return (sidx[0] - pd.Timedelta(days=1)) if len(sidx) else (pd.Timestamp(as_of) - pd.Timedelta(days=1))


def load_panel_ledger(db: Path, horizon: int, as_of=None):
    """Read-only join of REAL panel_score + mu to realized forward returns, one run per date.

    Enforces TRADING-SESSION aging: only ledger dates whose full ``horizon``-session label has
    elapsed as of ``as_of`` are returned, regardless of whether ``fwd_60d`` is non-NULL (Codex r2
    #2). Returns ``(df, meta)`` where meta carries the as_of / cutoff / session-count provenance.
    """
    import datetime as _dt  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    fwd = f"fwd_{horizon}d"
    con = sqlite3.connect(str(db))
    cols = {r[1] for r in con.execute("PRAGMA table_info(ticker_forward_returns)")}
    if fwd not in cols:
        con.close()
        raise ValueError(f"{fwd} not in ticker_forward_returns ({sorted(cols)})")
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(_dt.date.today())
    session_idx = _session_calendar(con, horizon)
    cutoff = _aged_cutoff(session_idx, horizon, as_of_ts)
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
    n_before = int(df["date"].nunique())
    # TRADING-SESSION aging cutoff: drop dates whose label horizon has not fully elapsed,
    # even if fwd_60d happens to be non-NULL (it may have been written early).
    df = df[df["date"] <= cutoff].copy()
    # one run per date: the run with the most candidate rows (the full pool)
    sz = df.groupby(["date", "run_id"]).size().reset_index(name="n")
    keep = sz.sort_values("n").groupby("date").tail(1)[["date", "run_id"]]
    df = df.merge(keep, on=["date", "run_id"])
    meta = {
        "as_of": str(as_of_ts.date()),
        "aged_cutoff": str(cutoff.date()),
        "aging": "trading_sessions",
        "n_sessions_le_as_of": int((session_idx <= as_of_ts).sum()),
        "dates_before_aging": n_before,
        "dates_dropped_not_aged": n_before - int(df["date"].nunique()),
    }
    return df, meta


def _moving_block_bootstrap(per_date_vals, *, block: int, n_boot: int = 2000, seed: int = 0):
    """Moving-block-bootstrap SE/CI for the mean of a serially-dependent per-date series.

    The per-date gap/IC series is NOT iid: adjacent dates share ~``block``-session overlapping
    forward windows and common regime shocks, so ``mean / SEM`` overstates significance (Codex
    r2 #1). A moving-block bootstrap resamples contiguous blocks of length ``block`` (= the label
    horizon in sessions, the span of the overlap), preserving that local dependence, and gives an
    honest SE / 95% percentile CI. Returns ``(se, lo, hi)`` or ``(None, None, None)`` when too short.
    """
    import numpy as np  # noqa: PLC0415

    a = np.asarray([v for v in per_date_vals if np.isfinite(v)], dtype=float)
    n = len(a)
    if n < 2 or block < 1:
        return None, None, None
    # With overlapping ``block``-session windows, a series shorter than (or equal to) one block
    # has no independent blocks to resample — the moving-block bootstrap would draw the SAME single
    # block every time and report a degenerate zero-width CI that falsely looks significant. Refuse
    # it: such regimes are too thin for an overlap-aware CI and must read as thin, not "sig".
    if n <= block:
        return None, None, None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    max_start = n - block  # inclusive
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = a[idx].mean()
    se = float(means.std(ddof=1))
    lo, hi = (float(v) for v in np.percentile(means, [2.5, 97.5]))
    return se, lo, hi


def _block_stat(per_date_vals, *, block: int) -> dict:
    """Per-date block stat: mean over dates + a MOVING-BLOCK-BOOTSTRAP CI (the trustworthy one).

    Surfaces the naive iid t only as a labelled, anti-conservative reference; the
    block-bootstrap 95% CI (block = label horizon in sessions) is what significance keys on.
    """
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    x = pd.Series([v for v in per_date_vals if np.isfinite(v)], dtype=float)
    mean = float(x.mean()) if len(x) else None
    sem = float(x.sem()) if len(x) > 1 else 0.0
    se_b, lo_b, hi_b = _moving_block_bootstrap(x.to_numpy(), block=block)
    return {
        "mean": mean,
        "t_iid_anticonservative": (float(mean / sem) if (sem > 0 and mean is not None) else None),
        "block_sessions": block,
        "block_bootstrap_se": se_b,
        "ci95_block_bootstrap": ([lo_b, hi_b] if se_b is not None else None),
        "t_block_bootstrap": (float(mean / se_b)
                              if (se_b not in (None, 0.0) and mean is not None) else None),
        # significant iff the block-bootstrap 95% CI excludes 0
        "significant_block_bootstrap": bool(lo_b is not None and (lo_b > 0 or hi_b < 0)),
        "n_dates": int(len(x)),
        "pct_days_negative": (float((x < 0).mean()) if len(x) else None),
    }


def _within_date_gaps(g, floor: float, mu_ceiling: float):
    """Per-date: (AND-fired mean fwd − kept mean fwd), and per-date rank-IC(panel, fwd)."""
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
             mu_ceiling: float = 0.0, min_xsec: int = 8, as_of=None) -> dict:
    """Per-regime within-date predictiveness of the AND-rule exit trigger. Read-only.

    Inference is overlap-aware (moving-block bootstrap) and aging is enforced by trading sessions.
    """
    df, meta = load_panel_ledger(db, horizon, as_of=as_of)
    df = df[df.groupby("date")["ticker"].transform("count") >= min_xsec].copy()
    out = {
        "horizon_days": horizon, "bottom_floor": floor, "mu_ceiling": mu_ceiling,
        "min_xsec": min_xsec, "ledger_dates": int(df["date"].nunique()),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())]
        if len(df) else [None, None],
        **meta,
        "by_regime": {},
    }
    for reg in ["ALL", *REGIME_ORDER]:
        sub = df if reg == "ALL" else df[df["regime"] == reg]
        if sub.empty:
            out["by_regime"][reg] = {"n_dates": 0, "status": "no_data"}
            continue
        gaps, ics, fmm = _within_date_gaps(sub, floor, mu_ceiling)
        gap = _block_stat(gaps, block=horizon)
        rec = {
            # within-date: AND-fired names' fwd minus the names you would keep
            "and_fired_minus_kept_fwd": gap,
            # within-date: AND-fired names' fwd minus the median name you'd hold instead
            "and_fired_minus_median_fwd": _block_stat(fmm, block=horizon),
            # per-date Spearman(panel_score, fwd): does the panel rank forward returns at all?
            "xsection_rank_ic": _block_stat(ics, block=horizon),
        }
        m = gap["mean"]
        sig = gap["significant_block_bootstrap"]
        ci = gap["ci95_block_bootstrap"]
        if m is None or gap["n_dates"] < 8 or ci is None:
            # ci is None when the regime has too few dates for a block (<= horizon) to give an
            # overlap-aware CI — too thin to call, even if a naive iid t looks large.
            rec["reading"] = "thin coverage — too few dates for an overlap-aware CI (not decision-grade)"
        elif m < 0 and sig:
            rec["reading"] = ("ledger SUGGESTS exit predictive (AND-fired names underperform; "
                              "block-bootstrap 95% CI < 0)")
        elif m > 0 and sig:
            rec["reading"] = ("ledger SUGGESTS exit inverted (AND-fired names OUTperform; "
                              "block-bootstrap 95% CI > 0 — exiting would forfeit alpha)")
        else:
            ci_s = f"[{ci[0]:+.4f},{ci[1]:+.4f}]" if ci else "thin"
            rec["reading"] = f"not significant (block-bootstrap 95% CI {ci_s} includes 0)"
        out["by_regime"][reg] = rec

    bc = out["by_regime"].get("BULL_CALM", {})
    bc_gap = bc.get("and_fired_minus_kept_fwd", {})
    bc_sig = bool(bc_gap.get("significant_block_bootstrap"))
    bc_mean = bc_gap.get("mean")
    # SUGGESTIVE language only — the block-bootstrap CI, not a naive t, decides direction.
    if bc_mean is None or not bc_sig:
        out["bull_calm_verdict"] = "BULL_CALM_INCONCLUSIVE"
    elif bc_mean < 0:
        out["bull_calm_verdict"] = "BULL_CALM_SUGGESTS_PREDICTIVE"
    else:
        out["bull_calm_verdict"] = "BULL_CALM_SUGGESTS_MISFIRE"
    out["caveat"] = (
        "EXPLORATORY DIAGNOSTIC — the ledger evidence SUGGESTS a direction, it does not decide a "
        "deployment. Within-date per-date-block inference over the live/sim ledger (1 run/date), "
        "aged by trading sessions, with overlap-aware moving-block-bootstrap CIs (block = the "
        "label horizon in sessions); regime is the pipeline's own per-run tag. The σ-blind / "
        "QP-override portfolio critique (the rule dumps low-σ ballast the QP wants to keep) is "
        "SEPARATE from this predictiveness test and is not settled by it. A pipeline change still "
        "needs a pre-registered, path-dependent shadow replay.")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--horizon", type=int, default=60)
    p.add_argument("--floor", type=float, default=0.20)
    p.add_argument("--mu-ceiling", type=float, default=0.0)
    p.add_argument("--min-xsec", type=int, default=8)
    p.add_argument("--as-of", default=None,
                   help="treat this date as 'today' for the trading-session aging cutoff "
                        "(default: today). A ledger date counts as aged only once >= horizon "
                        "TRADING sessions (from ticker_forward_returns.as_of_date) fall in "
                        "(date, as_of].")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    res = evaluate(Path(args.runs_db), args.horizon, args.floor,
                   args.mu_ceiling, args.min_xsec, as_of=args.as_of)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"ledger_dates={res['ledger_dates']}  range={res['date_range'][0]}..{res['date_range'][1]}"
          f"  horizon={res['horizon_days']}d  floor={res['bottom_floor']}  mu_ceiling={res['mu_ceiling']}")
    print(f"aging=trading_sessions  as_of={res['as_of']}  aged_cutoff={res['aged_cutoff']}  "
          f"dropped_not_aged={res['dates_dropped_not_aged']} (of {res['dates_before_aging']})")
    print("\nAND-rule (bottom-{:.0%} panel AND mu<={}) exited names vs the names you'd KEEP, "
          "within-date, per-regime (block-bootstrap CIs):".format(res["bottom_floor"], res["mu_ceiling"]))
    for reg, rec in res["by_regime"].items():
        if rec.get("status") == "no_data" or rec.get("n_dates") == 0:
            print(f"  [{reg:13s}] no data")
            continue
        g = rec["and_fired_minus_kept_fwd"]
        if g["mean"] is None:
            print(f"  [{reg:13s}] thin")
            continue
        ic = rec["xsection_rank_ic"]
        ci = g["ci95_block_bootstrap"]
        ci_s = f"95%CI[{ci[0]:+.4f},{ci[1]:+.4f}]" if ci else "CI:thin(<1 block)"
        sig_s = "sig" if g["significant_block_bootstrap"] else "ns"
        print(f"  [{reg:13s}] fired−kept fwd{res['horizon_days']} = {g['mean']:+.4f} "
              f"{ci_s} {sig_s} ({g['n_dates']}d, {100*g['pct_days_negative']:.0f}% days fired<kept; "
              f"t_iid={g['t_iid_anticonservative']:+.2f} [anti-cons])  rank-IC={ic['mean']:+.3f}\n"
              f"                  → {rec['reading']}")
    print(f"\nBULL_CALM verdict: {res['bull_calm_verdict']}")
    print(f"⚠ {res['caveat']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
