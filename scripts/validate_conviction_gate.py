#!/usr/bin/env python3
"""Data-backed validation of a conviction-gate change on REALIZED outcomes.

The postmortem (doc/design/2026-06-24-model-fixes-cant-reach-production-postmortem.md)
says a model-gate change is only "done" when it is exercised live with a ledger
accruing the evidence to make it live. This is that evidence engine: it joins the
accumulating decision ledger (``candidate_scores`` — per-run, per-name calibrated
``expected_return`` a.k.a. mu) to the panel dataset's REALIZED ``fwd_60d_excess``,
then compares what each admission rule WOULD have admitted and how those names
actually performed — per regime.

Rules compared (counterfactual, on the recorded mu):
  * RAW    : admit iff mu >= mu_floor
  * DEMEAN : admit iff mu - full_cross_section_mean(mu) >= mu_floor   (pipeline #147)

A change is justified to ENABLE when DEMEAN-admitted realized returns beat
RAW-admitted by a margin that holds across enough aged dates. Until the ledger
has >= min_dates dates whose mu rows are >= horizon_days old (so fwd_60d is
realized), it reports INSUFFICIENT_AGED_LEDGER rather than a misleading number —
this is expected right after the calibration/ledger feature ships (the mu column
only populates going forward).

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
    cs = pd.read_sql(
        "select run_id, ticker, expected_return from candidate_scores "
        "where expected_return is not null", con)
    con.close()
    cs["date"] = pd.to_datetime(
        cs["run_id"].str.extract(r"(\d{4}-\d{2}-\d{2})")[0], errors="coerce")
    cs = cs.dropna(subset=["date"])
    # one run per date: the one with the most candidate rows (the full pool)
    main = (cs.groupby(["date", "run_id"]).size().reset_index(name="n")
            .sort_values("n").groupby("date").tail(1))
    return cs.merge(main[["date", "run_id"]], on=["date", "run_id"])


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
    # AGE CUTOFF (Codex #190): a ledger date is only "aged" once its full
    # `horizon_days` has ELAPSED as of `as_of` — a dataset can carry a
    # fwd_60d_excess value for a date whose 60d window has not closed yet
    # (backfill / lookahead), and counting those would let the validator return
    # OK on un-realized returns. Filter to date <= as_of - horizon_days.
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(_dt.date.today())
    cutoff = as_of_ts - pd.Timedelta(days=horizon_days)
    m = m[m["date"] <= cutoff]
    aged_dates = int(m["date"].nunique())
    out = {"ledger_dates": int(cs["date"].nunique()), "aged_joined_dates": aged_dates,
           "mu_floor": mu_floor, "horizon_days": horizon_days,
           "as_of": str(as_of_ts.date()), "aged_cutoff": str(cutoff.date())}
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
                        "Only ledger dates <= as_of - horizon_days count as aged.")
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
