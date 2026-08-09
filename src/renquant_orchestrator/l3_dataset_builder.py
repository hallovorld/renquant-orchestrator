"""L3 meta-label dataset builder (allocation machine, orch#918 L3).

Builds the ENTRY-labeled dataset for the meta-label filter: one row per BUY
with its entry-time features and the realized outcome of the round trip it
opened. Read-only over the runs DB; writes one CSV.

PROVENANCE IS A COLUMN, NEVER A FILTER DEFAULT. The trades table commingles
sim and live rows (measured: ~99% carry source=None and are sim; 36 rows are
LiveBroker, and ALL 5,989 pnl-carrying sells lack a broker_order_id — so
outcome labels are effectively sim-only today). Every row carries
entry_live/exit_live flags and provenance = "live" iff BOTH legs carry a
broker_order_id, else "sim". A consumer that trains on the mix does so
EXPLICITLY; stdout reports the counts so the imbalance is never a surprise.

DATE SOURCE (measured): trade_date is NULL on 12,391/12,493 rows (the sim
rows never stamp it); the run_id prefix is a valid date on ALL rows. Dates
therefore use COALESCE(trade_date, substr(run_id,1,10)) — recorded here so
the choice is reviewable, not silent.

PAIRING RULE (v1, deliberately minimal and stated): a buy pairs with the NEXT
sell row of the same ticker with a later trade_date. Buys with no subsequent
sell (still-open or truncated) are EXCLUDED AND COUNTED — the count is in the
manifest line, never silent. Multiple concurrent lots of one ticker pair
first-buy-to-first-sell; the ambiguity count is reported.

Features carried (entry-time, from the buy row itself — nothing recomputed):
regime, confidence, panel_score, mu, sigma, expected_return, sector,
active_scorer, rank_score, kelly_target_pct. Label: win = sell.pnl_pct > 0,
plus pnl_pct and hold_days as continuous targets.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from .runtime_paths import default_data_root

SCHEMA = "l3_meta_label_dataset.v1"
FEATURES = ("regime", "confidence", "panel_score", "mu", "sigma",
            "expected_return", "sector", "active_scorer", "rank_score",
            "kelly_target_pct")


def build_rows(db_path: Path) -> tuple[list[dict], dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = ", ".join(FEATURES)
        date_expr = "COALESCE(trade_date, substr(run_id,1,10))"
        buys = con.execute(
            f"SELECT rowid, ticker, {date_expr}, broker_order_id, {cols} "
            f"FROM trades WHERE action='buy' AND {date_expr} IS NOT NULL "
            f"ORDER BY {date_expr}").fetchall()
        sells = con.execute(
            f"SELECT ticker, {date_expr}, pnl_pct, hold_days, exit_reason, "
            f"broker_order_id FROM trades WHERE action='sell' AND "
            f"{date_expr} IS NOT NULL AND pnl_pct IS NOT NULL "
            f"ORDER BY {date_expr}").fetchall()
    finally:
        con.close()

    sells_by_ticker: dict[str, list] = {}
    for t, d, pnl, hold, reason, sell_oid in sells:
        sells_by_ticker.setdefault(t, []).append((d, pnl, hold, reason, sell_oid))

    rows: list[dict] = []
    n_unclosed = 0
    used: dict[str, int] = {}   # ticker -> index of next unconsumed sell
    for rowid, ticker, bdate, order_id, *feats in buys:
        pool = sells_by_ticker.get(ticker, [])
        i = used.get(ticker, 0)
        while i < len(pool) and pool[i][0] <= bdate:
            i += 1
        if i >= len(pool):
            used[ticker] = i
            n_unclosed += 1
            continue
        sdate, pnl, hold, reason, sell_oid = pool[i]
        used[ticker] = i + 1
        entry_live, exit_live = bool(order_id), bool(sell_oid)
        row = {"buy_rowid": rowid, "ticker": ticker, "entry_date": bdate,
               "exit_date": sdate,
               "entry_live": int(entry_live), "exit_live": int(exit_live),
               "provenance": "live" if (entry_live and exit_live) else "sim",
               "win": int(pnl > 0), "pnl_pct": pnl, "hold_days": hold,
               "exit_reason": reason}
        row.update(dict(zip(FEATURES, feats)))
        rows.append(row)

    manifest = {
        "schema": SCHEMA,
        "n_rows": len(rows),
        "n_unclosed_buys_excluded": n_unclosed,
        "provenance_counts": {
            "live": sum(1 for r in rows if r["provenance"] == "live"),
            "sim": sum(1 for r in rows if r["provenance"] == "sim"),
        },
        "win_rate_by_provenance": {
            p: (round(sum(r["win"] for r in rows if r["provenance"] == p)
                      / max(1, sum(1 for r in rows if r["provenance"] == p)), 4))
            for p in ("live", "sim")
        },
        "pairing_rule": "first-buy-to-first-later-sell per ticker, v1",
    }
    return rows, manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    data_root = args.data_root or default_data_root()
    db = args.db or data_root / "data" / "runs.alpaca.db"
    try:
        rows, manifest = build_rows(db)
        if not rows:
            raise RuntimeError("zero paired rows — refusing an empty dataset")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        sidecar = args.out.with_suffix(".manifest.json")
        sidecar.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — fail-closed with the reason
        print(json.dumps({"status": "REFUSED", "why": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "BUILT", "out": str(args.out), **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
