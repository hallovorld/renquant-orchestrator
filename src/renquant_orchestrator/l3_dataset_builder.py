"""Paired-trade descriptive audit for the L3 research track.

Builds a descriptive, FIFO-paired view of BUY rows and later sells. It is
read-only over the runs DB and writes one CSV.

THIS IS NOT AN L3 TRAINING DATASET. The source trades table does not identify
lots: the measured production build marks 99.7% of paired rows as ambiguous.
The CLI therefore refuses unless the caller explicitly acknowledges that it is
requesting a surrogate-label audit. A valid L3 training label must be built
point-in-time from ``candidate_scores`` joined to
``ticker_forward_returns`` at an explicitly chosen horizon.

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

PAIRING RULE (v1, deliberately minimal and stated): FIFO — a buy pairs with
the NEXT unconsumed sell of the same ticker dated after it; ordering is
(date, rowid) in BOTH queries, so the assignment is deterministic. Buys with
no subsequent sell (still-open or truncated) are EXCLUDED AND COUNTED.

AMBIGUITY IS A COLUMN (codex on orch#924; measured: 6,084 buys occur while an
earlier same-ticker buy is still open). With no lot identity on the labelled
sells, FIFO is a surrogate, not ground truth. Every row therefore carries
``pairing_ambiguous = 1`` iff its [entry_date, exit_date] interval overlaps
ANY other lot of the same ticker (a paired lot before/after it, or a
still-open buy) — the symmetric definition: when episodes overlap, WHICH exit
belongs to WHICH entry is unobservable, so both sides are flagged. The
manifest reports the count; an audit caller must CHOOSE to include these rows
— the builder never chooses silently.

Features carried (entry-time, from the buy row itself — nothing recomputed):
regime, confidence, panel_score, mu, sigma, expected_return, sector,
active_scorer, rank_score, kelly_target_pct. Paired outcome fields: win =
sell.pnl_pct > 0, plus pnl_pct and hold_days. They are descriptive fields,
not valid L3 supervised-learning targets.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from .runtime_paths import default_data_root

SCHEMA = "paired_trade_audit.v1"
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
            f"ORDER BY {date_expr}, rowid").fetchall()
        sells = con.execute(
            f"SELECT ticker, {date_expr}, pnl_pct, hold_days, exit_reason, "
            f"broker_order_id FROM trades WHERE action='sell' AND "
            f"{date_expr} IS NOT NULL AND pnl_pct IS NOT NULL "
            f"ORDER BY {date_expr}, rowid").fetchall()
    finally:
        con.close()

    sells_by_ticker: dict[str, list] = {}
    for t, d, pnl, hold, reason, sell_oid in sells:
        sells_by_ticker.setdefault(t, []).append((d, pnl, hold, reason, sell_oid))

    rows: list[dict] = []
    n_unclosed = 0
    open_by_ticker: dict[str, list[str]] = {}   # unclosed buys' entry dates
    lots_by_ticker: dict[str, list[tuple[str, str, int]]] = {}  # (entry, exit, row_idx)
    used: dict[str, int] = {}   # ticker -> index of next unconsumed sell
    for rowid, ticker, bdate, order_id, *feats in buys:
        pool = sells_by_ticker.get(ticker, [])
        i = used.get(ticker, 0)
        while i < len(pool) and pool[i][0] <= bdate:
            i += 1
        if i >= len(pool):
            used[ticker] = i
            n_unclosed += 1
            open_by_ticker.setdefault(ticker, []).append(bdate)
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
        lots_by_ticker.setdefault(ticker, []).append((bdate, sdate, len(rows)))
        rows.append(row)

    # symmetric overlap flag: a lot is ambiguous iff its interval overlaps any
    # other lot (paired or still open) of the same ticker
    n_ambiguous = 0
    for ticker, lots in lots_by_ticker.items():
        opens = open_by_ticker.get(ticker, [])
        for j, (entry, exit_, idx) in enumerate(lots):
            overlap = any(
                (o_entry <= exit_ and entry <= o_exit)
                for k, (o_entry, o_exit, _) in enumerate(lots) if k != j)
            overlap = overlap or any(o <= exit_ for o in opens)
            rows[idx]["pairing_ambiguous"] = int(overlap)
            n_ambiguous += int(overlap)

    manifest = {
        "schema": SCHEMA,
        "n_rows": len(rows),
        "n_unclosed_buys_excluded": n_unclosed,
        "n_pairing_ambiguous": n_ambiguous,
        "provenance_counts": {
            "live": sum(1 for r in rows if r["provenance"] == "live"),
            "sim": sum(1 for r in rows if r["provenance"] == "sim"),
        },
        "win_rate_by_provenance": {
            p: (round(sum(r["win"] for r in rows if r["provenance"] == p)
                      / max(1, sum(1 for r in rows if r["provenance"] == p)), 4))
            for p in ("live", "sim")
        },
        "pairing_rule": "FIFO by (date,rowid), v1; pairing_ambiguous flags symmetric interval overlap",
    }
    return rows, manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--allow-surrogate-paired-labels",
        action="store_true",
        help=("acknowledge this is a descriptive FIFO-pairing audit, not an "
              "L3 training-label dataset"),
    )
    args = ap.parse_args(argv)
    if not args.allow_surrogate_paired_labels:
        print(json.dumps({
            "status": "REFUSED",
            "why": ("paired FIFO outcomes are surrogate labels; this audit cannot "
                    "supply L3 training labels. Use candidate_scores joined to "
                    "ticker_forward_returns with a declared forward horizon."),
        }, indent=2))
        return 2
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
