"""L3 TRAINING dataset: candidate-level, forward-return labelled, no pairing.

The valid L3 label construction the paired audit's refusal message prescribes:
``candidate_scores`` joined point-in-time to ``ticker_forward_returns`` at an
EXPLICITLY DECLARED horizon. One row per (run_date, ticker) from the widest
run of each date (equal-width ties: latest ``created_at`` wins — the
canonical same-day run); the outcome is the market's forward return from
that date —
not the book's realized round trip — so there is no lot pairing and therefore
no ambiguity, by construction.

DECLARED HORIZON (frozen): primary label = ``fwd_20d`` (the densest column);
``fwd_60d`` is carried alongside because the panel's thesis horizon is 60d
(label_col fwd_60d_excess, min_holding 60). A consumer choosing 60d does so
on a column that exists, not by rebuilding.

WHY CANDIDATE-LEVEL, NOT BUY-LEVEL: the meta-label filter must learn "when do
the panel's picks win" — that needs the names the panel scored and did NOT
act on as negatives-by-abstention context. ``selected`` and ``blocked_by``
are carried so acted/not-acted is a COLUMN, never a filter default (the same
doctrine as provenance in the paired audit).

RUN PROVENANCE: run_type (live/sim/…) from pipeline_runs is a column. The
2024-2025 "sim" runs carry 1–13 candidates/day (measured); n-per-date is in
the row so a consumer can floor cross-section width explicitly.

REGIME: candidate_scores does not stamp regime; it joins from
live_state_snapshots (best row per run_date) with an explicit
``regime_source`` column = 'snapshot' | 'absent' — an absent join is a
recorded fact, never an invented value.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from .runtime_paths import default_data_root

SCHEMA = "l3_candidate_dataset.v1"
PRIMARY_HORIZON = "fwd_20d"
FEATURES = ("panel_score", "raw_score", "rank_score", "mu", "sigma",
            "expected_return", "sector", "active_scorer", "selected",
            "blocked_by", "kelly_target_pct")


def build_candidate_rows(db_path: Path) -> tuple[list[dict], dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # widest run per date, candidates only; equal-width ties break to the
        # latest created_at — the canonical same-day run (the same dedup rule
        # as doc/research/2026-07-02-m3-haircut-replay.md), never SQLite row
        # order, which could silently train on a superseded retry
        best = {}
        for rdate, rid, created, n in con.execute(
                "SELECT p.run_date, cs.run_id, p.created_at, COUNT(*) "
                "FROM pipeline_runs p "
                "JOIN candidate_scores cs ON cs.run_id = p.run_id "
                "WHERE cs.role='candidate' AND cs.panel_score IS NOT NULL "
                "GROUP BY p.run_date, cs.run_id"):
            if (n, created or "") > best.get(rdate, (0, "", ""))[:2]:
                best[rdate] = (n, created or "", rid)
        run_type = dict(con.execute(
            "SELECT run_id, run_type FROM pipeline_runs"))
        regime = {}
        for rdate, reg, conf in con.execute(
                "SELECT run_date, regime, confidence FROM live_state_snapshots "
                "ORDER BY created_at"):
            regime[rdate] = (reg, conf)      # last snapshot of the date wins
        fwd = {}
        for t, d, f20, f60 in con.execute(
                "SELECT ticker, as_of_date, fwd_20d, fwd_60d "
                "FROM ticker_forward_returns WHERE fwd_20d IS NOT NULL"):
            fwd[(t, d)] = (f20, f60)
        cols = ", ".join(FEATURES)
        rows: list[dict] = []
        n_no_label = 0
        for rdate in sorted(best):
            n_date, _, rid = best[rdate]
            reg = regime.get(rdate)
            for r in con.execute(
                    f"SELECT ticker, {cols} FROM candidate_scores "
                    "WHERE run_id=? AND role='candidate' "
                    "AND panel_score IS NOT NULL ORDER BY ticker", (rid,)):
                ticker, *feats = r
                lab = fwd.get((ticker, rdate))
                if lab is None:
                    n_no_label += 1
                    continue
                f20, f60 = lab
                row = {"run_date": rdate, "ticker": ticker, "run_id": rid,
                       "run_type": run_type.get(rid),
                       "n_candidates_that_date": n_date,
                       "regime": reg[0] if reg else None,
                       "regime_confidence": reg[1] if reg else None,
                       "regime_source": "snapshot" if reg else "absent",
                       "fwd_20d": f20, "fwd_60d": f60,
                       "win": int(f20 > 0)}
                row.update(dict(zip(FEATURES, feats)))
                rows.append(row)
    finally:
        con.close()
    n_live = sum(1 for r in rows if r["run_type"] == "live")
    manifest = {
        "schema": SCHEMA,
        "primary_horizon": PRIMARY_HORIZON,
        "n_rows": len(rows),
        "n_dates": len({r["run_date"] for r in rows}),
        "n_candidates_without_forward_row_excluded": n_no_label,
        "rows_by_run_type": {
            rt: sum(1 for r in rows if r["run_type"] == rt)
            for rt in sorted({r["run_type"] for r in rows}, key=str)},
        "n_selected": sum(1 for r in rows if r.get("selected")),
        "win_rate_fwd20_all": (round(sum(r["win"] for r in rows) / len(rows), 4)
                               if rows else None),
        "label_note": ("outcome = market forward return at the score date; "
                       "no pairing, no lot ambiguity by construction; "
                       "acted/not-acted is the selected/blocked_by columns"),
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
        rows, manifest = build_candidate_rows(db)
        if not rows:
            raise RuntimeError("zero labelled candidate rows — refusing an "
                               "empty dataset")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        args.out.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — fail-closed with the reason
        print(json.dumps({"status": "REFUSED", "why": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "BUILT", "out": str(args.out), **manifest},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
