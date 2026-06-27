#!/usr/bin/env python3
"""Data-backed validation of a conviction-gate change on REALIZED outcomes.

The postmortem (doc/design/2026-06-24-model-fixes-cant-reach-production-postmortem.md)
says a model-gate change is only "done" when it is exercised live with a ledger
accruing the evidence to make it live. This is that evidence engine: it joins the
accumulating decision ledger (``candidate_scores`` — per-run, per-name calibrated
``expected_return`` a.k.a. mu) to the panel dataset's REALIZED ``fwd_60d_excess``,
then compares what each admission rule WOULD have admitted and how those names
actually performed — per regime.

Two lenses (2026-06-26):
  1. ABSOLUTE-FLOOR admission (the original): RAW (mu >= mu_floor) vs DEMEAN
     (mu - full_cross_section_mean(mu) >= mu_floor, pipeline #147), comparing the
     admitted sets' realized fwd_60d_excess, per regime. On the sim ledger only a
     few names clear an absolute 0.03 floor and admitted-set means are
     leakage-inflated in-sample — so this lens stays directional and is most
     trustworthy once enough aged LIVE dates accrue.
  2. ``rank_evidence`` — FLOOR-FREE and leakage-robust. Per-date Spearman(mu, fwd)
     and the within-date mean-fwd gap between the names demean REFUSES (mu>0 but
     below the cross-sectional mean) and the names it KEEPS. Both cancel a uniform
     per-date level/leakage offset, so they read cleanly even in-sample. This is
     the decision-relevant question: does demean drop relative losers or winners?
     Significance is reported via a MOVING-BLOCK BOOTSTRAP (block = the label
     horizon in sessions) because adjacent dates share overlapping forward windows
     and are not iid; the naive iid t is retained only as a labelled, known-
     anti-conservative reference.

The ledger now spans 2024→ (sim ``mu`` + live), so lens 2 is available immediately;
lens 1 reports INSUFFICIENT_AGED_LEDGER until >= min_dates aged dates accrue.

Read-only. Usage:
    validate_conviction_gate.py [--runs-db PATH] [--dataset PATH] \
        [--mu-floor 0.03] [--horizon-days 60] [--min-dates 30] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/renhao/git/github/RenQuant")
DEF_DB = REPO / "data" / "runs.alpaca.db"
DEF_DS = REPO / "data" / "alpha158_291_fund_regime_dataset.parquet"
REGIME_COLS = ["regime_p_bull_calm", "regime_p_bear", "regime_p_bull_volatile"]
REGIME_NAMES = ["BULL_CALM", "BEAR", "BULL_VOLATILE"]


def load_ledger(db: Path):
    import pandas as pd  # noqa: PLC0415
    con = sqlite3.connect(str(db))
    # 2026-06-26: prefer ``mu`` (populated on the full sim+live ledger, ~201k
    # rows back to 2024) and fall back to ``expected_return`` (live-only, ~9k
    # rows). Pre-fix this keyed on ``expected_return`` alone, which is NULL on
    # every sim row, so the validator only ever saw the ~2-month live ledger and
    # reported INSUFFICIENT_AGED_LEDGER even though 2+ years of aged sim mu were
    # present. mu and expected_return are the same calibrated ER where both set.
    cols = {r[1] for r in con.execute("PRAGMA table_info(candidate_scores)")}
    score = ("coalesce(mu, expected_return)" if "mu" in cols else "expected_return")
    cs = pd.read_sql(
        f"select run_id, ticker, {score} as expected_return "
        f"from candidate_scores where {score} is not null", con)
    con.close()
    cs["date"] = pd.to_datetime(
        cs["run_id"].str.extract(r"(\d{4}-\d{2}-\d{2})")[0], errors="coerce")
    cs = cs.dropna(subset=["date"])
    # one run per date: the one with the most candidate rows (the full pool)
    main = (cs.groupby(["date", "run_id"]).size().reset_index(name="n")
            .sort_values("n").groupby("date").tail(1))
    return cs.merge(main[["date", "run_id"]], on=["date", "run_id"])


def _block_bootstrap_se(x, *, block: int, n_boot: int = 2000, seed: int = 0):
    """Moving-block bootstrap SE/CI for the mean of a serially-dependent series.

    The per-date statistics below (rank-IC, refused−kept gap) are NOT iid across
    dates: adjacent dates share ~60-session overlapping forward-return windows and
    common market/regime shocks, so a naive ``mean/sem`` t hugely overstates
    significance (Codex #196 #2). A moving-block bootstrap resamples contiguous
    blocks of length ``block`` (set to the label horizon in sessions, the span of
    the overlap), preserving that local dependence, and gives an honest SE/CI.

    Returns ``(se, lo, hi)`` for a 95% percentile CI, or ``(None, None, None)``
    when the series is too short for a block bootstrap.
    """
    import numpy as np  # noqa: PLC0415
    a = np.asarray(x, dtype=float)
    a = a[~np.isnan(a)]
    n = len(a)
    if n < 2 or block < 1:
        return None, None, None
    block = min(block, n)
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


def _rank_evidence(m, *, score="expected_return", ret="fwd_60d_excess",
                   min_xsec=8, block_sessions=60) -> dict:
    """Floor-free, leakage-robust evidence for the demean transform.

    The admitted-set means (RAW vs DEMEAN at an absolute mu_floor) are
    leakage-inflated in-sample and, on the sim ledger, only a handful of names
    clear a 0.03 floor — too thin to read. The decision-relevant question is
    *relational*: does removing the cross-sectional mean (what demean does) keep
    the names that out-perform and drop the ones that under-perform? Two
    WITHIN-DATE statistics answer that and are robust to a uniform per-date
    leakage/level offset (it cancels inside each date):

    * ``xsection_rank_ic`` — per-date Spearman(score, realized fwd) averaged over
      dates. >0 means the score ranks forward returns; demean sharpens that rank.
    * ``within_date_refused_minus_kept`` — within each date, mean realized fwd of
      the names demean REFUSES (score>0 but below the cross-sectional mean) minus
      the names it KEEPS. <0 means demean drops the relative losers (good); >0
      means it drops winners (bad → revert).

    Significance: adjacent dates have heavily overlapping ~60-session forward
    windows, so date-level observations are NOT iid (Codex #196 #2). We report a
    MOVING-BLOCK-BOOTSTRAP SE and 95% CI (block = the label horizon in sessions)
    alongside the naive iid t. The naive t is kept only as a (clearly-labelled,
    anti-conservative) reference; the bootstrap CI is the one to trust.
    """
    import numpy as np, pandas as pd  # noqa: PLC0415
    g = m[m.groupby("date")["ticker"].transform("count") >= min_xsec].copy()
    if g.empty:
        return {"status": "thin", "n_dates": 0}
    g["dem"] = g[score] - g.groupby("date")[score].transform("mean")
    ics, diffs = [], []
    for _dt, s in g.sort_values("date").groupby("date", sort=True):
        if s[score].nunique() > 2:
            ics.append(float(s[[score, ret]].corr("spearman").iloc[0, 1]))
        ref = s[(s[score] > 0) & (s["dem"] < 0)][ret]
        kep = s[(s[score] > 0) & (s["dem"] >= 0)][ret]
        if len(ref) >= 1 and len(kep) >= 1:
            diffs.append(float(ref.mean() - kep.mean()))
    ics = pd.Series([x for x in ics if x == x])
    diffs = pd.Series([x for x in diffs if x == x])

    def _stat(x):
        mean = float(x.mean()) if len(x) else None
        sem = float(x.sem()) if len(x) > 1 else 0.0
        se_b, lo_b, hi_b = _block_bootstrap_se(x.to_numpy(), block=block_sessions)
        # bootstrap t = mean / block-bootstrap SE (honest); naive t kept labelled
        return {"mean": mean,
                "t_iid_anticonservative": (float(mean / sem) if sem > 0 else None),
                "block_bootstrap_se": se_b,
                "ci95_block_bootstrap": ([lo_b, hi_b] if se_b is not None else None),
                "t_block_bootstrap": (float(mean / se_b)
                                      if (se_b not in (None, 0.0) and mean is not None)
                                      else None),
                # significant iff the block-bootstrap 95% CI excludes 0
                "significant_block_bootstrap": (
                    bool(lo_b is not None and (lo_b > 0 or hi_b < 0))),
                "block_sessions": block_sessions,
                "n_dates": int(len(x))}

    out = {"xsection_rank_ic": _stat(ics),
           "within_date_refused_minus_kept": _stat(diffs)}
    out["within_date_refused_minus_kept"]["pct_days_refused_below_kept"] = (
        float((diffs < 0).mean()) if len(diffs) else None)
    out["reading"] = (
        "demean drops relative UNDER-performers (good)"
        if (out["within_date_refused_minus_kept"]["mean"] or 0) < 0
        else "demean drops relative OUT-performers (bad → revert)")
    return out


def evaluate(db: Path, ds: Path, mu_floor: float, horizon_days: int,
             min_dates: int, as_of=None) -> dict:
    import datetime as _dt  # noqa: PLC0415
    import numpy as np, pandas as pd  # noqa: PLC0415
    cs = load_ledger(db)
    d = pd.read_parquet(ds, columns=["date", "ticker", "fwd_60d_excess", *REGIME_COLS])
    d["date"] = pd.to_datetime(d["date"])
    realized = d.dropna(subset=["fwd_60d_excess"]).copy()
    realized["regime"] = realized[REGIME_COLS].values.argmax(1)
    m = cs.merge(realized[["date", "ticker", "fwd_60d_excess", "regime"]],
                 on=["date", "ticker"], how="inner")
    # AGE CUTOFF (Codex #196): a ledger date is only "aged" once the FULL forward
    # horizon of its label has elapsed as of `as_of`. `fwd_60d_excess` is a
    # 60-TRADING-SESSION label — it is built as `c.shift(-60)/c - 1` over daily
    # bars in renquant-base-data alpha158_qlib_panel._compute_excess_label_frame
    # (a row/bar shift, confirmed by purged_cv.py's "purge in BARS, not calendar
    # days" audit note), NOT a 60-calendar-day label — 60 sessions ≈ 84 calendar
    # days. The previous
    # cutoff (`as_of - Timedelta(days=horizon_days)`, i.e. 60 *calendar* days)
    # therefore admitted dates only ~42 sessions old, counting not-yet-realized
    # labels as evidence. We now age against the dataset's own sorted trading-date
    # index: a ledger date is aged iff >= `horizon_days` trading dates from that
    # index fall in (ledger_date, as_of]. (We use the dataset dates as the session
    # calendar because they are exactly the bars over which the label is defined.)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(_dt.date.today())
    session_idx = pd.DatetimeIndex(sorted(d["date"].unique()))
    session_idx = session_idx[session_idx <= as_of_ts]
    # The newest ledger date whose label is fully realized: it must have at least
    # `horizon_days` later sessions on-or-before as_of. That is the
    # `horizon_days`-th session counting back from as_of.
    if len(session_idx) > horizon_days:
        cutoff = session_idx[-(horizon_days + 1)]
    else:
        cutoff = session_idx[0] - pd.Timedelta(days=1) if len(session_idx) else as_of_ts
    m = m[m["date"] <= cutoff]
    aged_dates = int(m["date"].nunique())
    out = {"ledger_dates": int(cs["date"].nunique()), "aged_joined_dates": aged_dates,
           "mu_floor": mu_floor, "horizon_days": horizon_days,
           "as_of": str(as_of_ts.date()), "aged_cutoff": str(cutoff.date()),
           "aging": "trading_sessions"}
    # Floor-free, leakage-robust evidence — reported even when the absolute-floor
    # admission lens below is too thin (few names clear mu_floor on the sim mu).
    # block length = the label's forward horizon in sessions, i.e. the span over
    # which adjacent dates' labels overlap (Codex #196 #2).
    out["rank_evidence"] = _rank_evidence(m, block_sessions=horizon_days)
    if aged_dates < min_dates:
        out["status"] = "INSUFFICIENT_AGED_LEDGER"
        out["detail"] = (f"only {aged_dates} ledger dates are <= {cutoff.date()} "
                         f"(as_of {as_of_ts.date()} - {horizon_days}d) with realized "
                         f"returns (need >= {min_dates}); the mu column populates going "
                         f"forward, so this closes as the ledger ages.")
        return out
    m["full_mean"] = m.groupby("date")["expected_return"].transform("mean")
    m["raw"] = m["expected_return"] >= mu_floor
    m["dem"] = (m["expected_return"] - m["full_mean"]) >= mu_floor

    def agg(frame, mask):
        s = frame.loc[mask, "fwd_60d_excess"]
        return {"n": int(len(s)), "mean": float(s.mean()) if len(s) else None,
                "median": float(s.median()) if len(s) else None}

    def triple(frame):
        return {"raw_admitted": agg(frame, frame["raw"]),
                "demean_admitted": agg(frame, frame["dem"]),
                "dropped_by_demean": agg(frame, frame["raw"] & ~frame["dem"])}

    out["status"] = "OK"
    out["all_regimes"] = triple(m)
    out["by_regime"] = {name: triple(m[m.regime == ri])
                        for ri, name in enumerate(REGIME_NAMES)}
    raw_mean = out["all_regimes"]["raw_admitted"]["mean"]
    dem_mean = out["all_regimes"]["demean_admitted"]["mean"]
    out["demean_minus_raw_mean_fwd"] = (
        (dem_mean - raw_mean) if (raw_mean is not None and dem_mean is not None) else None)
    # Causal number: realized return of the names demean DROPS but raw keeps. If
    # demean is helping, these were losers (mean < 0) — more decision-relevant
    # than the admitted-set delta, which mixes in the names both rules keep.
    out["dropped_by_demean_mean_fwd"] = out["all_regimes"]["dropped_by_demean"]["mean"]
    out["verdict"] = (
        "DEMEAN_BETTER" if (out["demean_minus_raw_mean_fwd"] or 0) > 0 else "NOT_BETTER")
    # The verdict is DIRECTIONAL over `aged_dates` dates — NOT a significance
    # test. This enable engine must not flip production config on a sign alone;
    # a bootstrap CI + per-regime consistency are required first.
    out["caveat"] = (
        f"directional over {aged_dates} aged dates; not significance-tested — do "
        "not enable without a bootstrap CI and per-regime consistency")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs-db", default=str(DEF_DB))
    p.add_argument("--dataset", default=str(DEF_DS))
    p.add_argument("--mu-floor", type=float, default=0.03)
    p.add_argument("--horizon-days", type=int, default=60)
    p.add_argument("--min-dates", type=int, default=30)
    p.add_argument("--as-of", default=None,
                   help="treat this date as 'today' for the age cutoff (default: today). "
                        "A ledger date counts as aged only once >= horizon_days TRADING "
                        "sessions (from the dataset's date index) fall in (date, as_of].")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    res = evaluate(Path(args.runs_db), Path(args.dataset), args.mu_floor,
                   args.horizon_days, args.min_dates, as_of=args.as_of)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"status={res['status']}  ledger_dates={res['ledger_dates']}  "
              f"aged_joined_dates={res['aged_joined_dates']}")
        re = res.get("rank_evidence", {})
        ic = re.get("xsection_rank_ic", {})
        rk = re.get("within_date_refused_minus_kept", {})

        def _ci(stat):
            ci = stat.get("ci95_block_bootstrap")
            sig = " sig" if stat.get("significant_block_bootstrap") else " ns"
            return (f"95%CI[{ci[0]:+.4f},{ci[1]:+.4f}]{sig}" if ci
                    else "CI:thin")

        if ic.get("mean") is not None:
            print(f"  [robust] x-sec rank-IC(mu, fwd60) = {ic['mean']:+.4f} "
                  f"{_ci(ic)} ({ic['n_dates']}d, block-bootstrap)")
        if rk.get("mean") is not None:
            print(f"  [robust] within-date (demean-refused − kept) fwd60 = "
                  f"{rk['mean']:+.4f} {_ci(rk)} ({rk['n_dates']}d, "
                  f"{100*rk['pct_days_refused_below_kept']:.0f}% days refused<kept) "
                  f"→ {re.get('reading','')}")
        if res["status"] == "OK":
            a = res["all_regimes"]
            print(f"  RAW    admitted: n={a['raw_admitted']['n']} mean_fwd60={a['raw_admitted']['mean']:+.4f}")
            print(f"  DEMEAN admitted: n={a['demean_admitted']['n']} mean_fwd60={a['demean_admitted']['mean']:+.4f}")
            dbd = res["dropped_by_demean_mean_fwd"]
            print(f"  dropped-by-demean realized mean_fwd60 = {dbd:+.4f}"
                  if dbd is not None else "  dropped-by-demean: n=0")
            print(f"  demean-raw mean fwd60 = {res['demean_minus_raw_mean_fwd']:+.4f} → {res['verdict']}")
            print(f"  ⚠ {res['caveat']}")
        else:
            print(f"  {res['detail']}")
    # exit 0 always (read-only report); the verdict is in the payload
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
