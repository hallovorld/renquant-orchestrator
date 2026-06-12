#!/usr/bin/env python3
"""Decision-level P&L attribution prototype (#108 III.6, self-discovered gap #6).

Question no one could answer until now: what did each GATE/VETO decision
earn or cost? Method: join historical candidate_scores rows (selected vs
blocked, with blocked_by reason) to realized forward returns from
ticker_forward_returns — per-decision attribution becomes a query.
Read-only on the REAL run DB.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"

if __name__ == "__main__":
    c = sqlite3.connect(DB)
    cs = pd.read_sql(
        "SELECT run_id, ticker, selected, blocked_by, rank_score "
        "FROM candidate_scores WHERE rank_score IS NOT NULL", c)
    fr = pd.read_sql("SELECT * FROM ticker_forward_returns", c)
    datecol = [x for x in fr.columns if "date" in x.lower()][0]
    retcols = [x for x in fr.columns if x.startswith("fwd_") or "ret" in x.lower()]
    cs["date"] = cs.run_id.str.slice(0, 10)
    j = cs.merge(fr, left_on=["date", "ticker"],
                 right_on=[datecol, "ticker"], how="inner")
    ret = retcols[0]
    j = j.dropna(subset=[ret])
    print(f"joined decision-outcome rows: {len(j)} "
          f"({j['date'].nunique()} days; outcome metric = {ret})")
    print("\n=== realized outcome by DECISION CLASS ===")
    j["cls"] = j.apply(
        lambda r: "SELECTED" if r.selected else
        ("veto:" + str(r.blocked_by).split(":")[0] if r.blocked_by else "passed-not-selected"),
        axis=1)
    g = j.groupby("cls")[ret].agg(["count", "mean", "median"]).sort_values("count", ascending=False)
    print(g.head(10).to_string(float_format=lambda x: f"{x:+.4f}"))
    sel = j[j.cls == "SELECTED"][ret]
    blk = j[j.cls.str.startswith("veto")][ret]
    if len(sel) > 10 and len(blk) > 10:
        print(f"\nheadline: SELECTED mean {sel.mean():+.4f} vs VETOED mean {blk.mean():+.4f} "
              f"→ selection edge {sel.mean()-blk.mean():+.4f} per decision "
              f"(n={len(sel)}/{len(blk)})")
    print("\nproduction wiring: orders carry decision_id; realized P&L written "
          "back on close → this table becomes continuous, per-gate, queryable.")
