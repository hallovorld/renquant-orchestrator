#!/usr/bin/env python3
"""Build the SHADOW training panel = prod alpha158-fund panel + one analyst feature.

Adds `an_rev3` (3-month change in the analyst rating-consensus, from FMP
grades-historical) as a single extra column, merged point-in-time (merge_asof
backward by date, per ticker) so there is NO lookahead. Revision-ONLY by design:
the 2026-06-25 per-regime placebo-clean decomposition showed the consensus LEVEL
hurts BULL_VOLATILE while the revision (rev3) is benign-to-mildly-positive — so we
carry the revision and drop the level. The combined analyst signal is weak/inside
the leakage-floor noise, which is exactly why it belongs in the SHADOW (isolated,
no live-book risk) to accrue live OOS evidence, not the primary model.

Writes to a SEPARATE shadow data-dir; the production panel is never modified
(hard rule — never touch canonical prod inputs). The GBDT trainer auto-discovers
`an_rev3` as a feature (panel cols minus the meta/label set), and the scorer reads
the feature list from the artifact, so NO renquant-model code change is needed.

  build_shadow_analyst_panel.py \
      --repo /Users/renhao/git/github/RenQuant \
      --out  /Users/renhao/git/github/RenQuant/data/shadow_analyst
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

PANEL = "alpha158_291_fundamental_dataset.parquet"
STATS = "alpha158_qlib_dataset.stats.json"
FUND = "sec_fundamentals_daily.parquet"
GRADES = "fmp_harvest/grades_historical_291.parquet"
RC = ("analystRatingsStrongBuy", "analystRatingsBuy", "analystRatingsHold",
      "analystRatingsSell", "analystRatingsStrongSell")


def build_an_rev3(grades_path: Path) -> pd.DataFrame:
    """Per-(ticker, date) analyst revision: Δ3-month consensus. Point-in-time —
    `date` is the rating-distribution month, used only via a backward as-of join."""
    g = pd.read_parquet(grades_path)
    g["date"] = pd.to_datetime(g["date"])
    tot = sum(g[c] for c in RC)
    # consensus in [-2, 2]: 2*strongBuy + buy - sell - 2*strongSell, normalized by count
    g["an_consensus"] = np.where(
        tot > 0, (2 * g[RC[0]] + g[RC[1]] - g[RC[3]] - 2 * g[RC[4]]) / tot, np.nan)
    g = g.sort_values(["ticker", "date"])
    g["an_rev3"] = g.groupby("ticker")["an_consensus"].diff(3)
    return g[["ticker", "date", "an_rev3"]].dropna(subset=["an_rev3"])


def merge_panel(panel: pd.DataFrame, rev: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    out = []
    for t, sub in panel.groupby("ticker", sort=False):
        sub = sub.sort_values("date")
        rt = rev[rev["ticker"] == t][["date", "an_rev3"]].sort_values("date")
        if len(rt):
            out.append(pd.merge_asof(sub, rt, on="date", direction="backward"))
        else:
            out.append(sub.assign(an_rev3=np.nan))
    return pd.concat(out, ignore_index=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="/Users/renhao/git/github/RenQuant")
    ap.add_argument("--out", default=None, help="shadow data-dir (default: <repo>/data/shadow_analyst)")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    data = repo / "data"
    out = Path(args.out) if args.out else data / "shadow_analyst"
    out.mkdir(parents=True, exist_ok=True)

    rev = build_an_rev3(data / GRADES)
    panel = pd.read_parquet(data / PANEL)
    merged = merge_panel(panel, rev)
    cov = merged["an_rev3"].notna().mean()
    ntk = merged.loc[merged["an_rev3"].notna(), "ticker"].nunique()
    assert "an_rev3" in merged.columns and len(merged) == len(panel), "merge changed row count"

    merged.to_parquet(out / PANEL, index=False)
    # symlink the other required inputs (read-only) so the trainer's --data-dir is self-contained
    for f in (STATS, FUND):
        link = out / f
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(data / f, link)
    print(f"shadow panel → {out/PANEL}")
    print(f"  rows={len(merged)} cols={merged.shape[1]} (+an_rev3) "
          f"an_rev3 cov={cov*100:.0f}% ({ntk} tickers)")
    print(f"  linked: {STATS}, {FUND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
