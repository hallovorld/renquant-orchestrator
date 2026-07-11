#!/usr/bin/env python3
"""Offline one-share-floor ON-vs-OFF replay over the production decision ledger.

Replays the exact A-3 rescue semantics of
renquant-pipeline/src/renquant_pipeline/kernel/pipeline/task_selection.py
(SizeAndEmitTask, floor branch at lines 571-611 + deferred pass 641-673):

  A candidate blocked at the sizing stage with `size_insufficient_cash`
  (i.e. whole-share rounding produced shares < 1) is rescued to exactly
  ONE share iff:
    (a) max_pct > 0                    (kelly_target_pct > 0 in the ledger)
    (b) override_pct is None           (no BEAR defensive slot; regime != BEAR)
    (c) price <= regime max_position_pct * PV + 1e-6   (regime cap)
    (d) price <= leftover investable = remaining_cash - reserve_pct*PV + 1e-6
  Rescues run in a DEFERRED pass, in rank order, consuming leftover cash
  only after every normal candidate has sized (n_buys tells us how many
  normal buys happened; in this window it is 0 everywhere).

Price source: daily close of the run date (intent-time quote unavailable
offline; caveat recorded in the packet).

Two modes (Codex review of orchestrator#471, 2026-07-11 — r1 hardcoded a
one-off /private/tmp scratch path and /Users/renhao/git/github/RenQuant,
and picked each date's "representative" run by MAXIMUM outcome among all
same-day rows with a denominator mismatched against that selection):

  --extract   READ-ONLY: queries the live decision ledger (--db-path) and
              OHLCV parquet (--ohlcv-dir), predeclares exactly one
              canonical run_id per date via a STRUCTURAL rule blind to
              outcome (the unique pipeline_runs row with n_candidates>0
              that date — real daily-full candidate-scoring sessions,
              distinct from renquant105's zero-candidate intraday
              decisioning ticks), fails closed to EXCLUDED on any date
              with zero or 2+ such rows, and writes a self-contained
              sealed bundle (--out-bundle) — no DB/OHLCV access needed to
              reproduce results from it afterward.

  (default)   Computes results PURELY from a sealed bundle (--bundle,
              e.g. a renquant-artifacts store:// checkout) — no DB,
              OHLCV file, or umbrella path needed. This is the
              reproducible, verifiable path; a clean checkout with only
              this script and the sealed bundle produces byte-identical
              results.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REGIME_CAP = {"BULL_CALM": 0.12, "BULL_VOLATILE": 0.20, "CHOPPY": 0.15, "BEAR": 0.0}
RESERVE = {"BULL_CALM": 0.0, "BULL_VOLATILE": 0.2, "CHOPPY": 0.3, "BEAR": 1.0}


def build_canonical_manifest(conn: sqlite3.Connection, start: str, end: str) -> dict:
    """Predeclare exactly one canonical (real daily-full, candidate-scoring)
    run_id per calendar date — a structural rule blind to outcome, never
    chosen by which run looks best. Fails closed (EXCLUDED, with the
    concrete reason) on any date with zero or 2+ qualifying rows."""
    all_dates = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM pipeline_runs WHERE run_date >= ? AND run_date <= ? ORDER BY run_date",
            (start, end),
        ).fetchall()
    ]
    cand_runs = conn.execute(
        """SELECT run_date, run_id, created_at, n_candidates FROM pipeline_runs
           WHERE run_date >= ? AND run_date <= ? AND n_candidates > 0
           ORDER BY run_date, created_at""",
        (start, end),
    ).fetchall()
    by_date: dict[str, list] = defaultdict(list)
    for r in cand_runs:
        by_date[r[0]].append({"run_id": r[1], "created_at": r[2], "n_candidates": r[3]})

    dates: dict[str, dict] = {}
    for d in all_dates:
        runs = by_date.get(d, [])
        if len(runs) == 0:
            dates[d] = {
                "status": "EXCLUDED_NO_CANDIDATE_RUN",
                "reason": "no pipeline_runs row with n_candidates>0 on this date "
                          "(no daily-full candidate-scoring session found)",
            }
        elif len(runs) == 1:
            dates[d] = {"status": "CANONICAL", "run_id": runs[0]["run_id"], "created_at": runs[0]["created_at"]}
        else:
            dates[d] = {
                "status": "EXCLUDED_AMBIGUOUS",
                "reason": f"{len(runs)} candidate-scoring runs on this date with no principled "
                          "tie-break rule available; excluded per fail-closed policy rather "
                          "than picking by outcome",
                "candidate_run_ids": runs,
            }
    return {"window": f"{start}..{end}", "dates": dates}


def extract_bundle(db_path: str, ohlcv_dir: str, start: str, end: str) -> dict:
    import pandas as pd

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    manifest = build_canonical_manifest(conn, start, end)
    canonical_run_ids = [v["run_id"] for v in manifest["dates"].values() if v["status"] == "CANONICAL"]
    if not canonical_run_ids:
        raise SystemExit("no canonical runs found in window — refusing to seal an empty bundle")
    placeholders = ",".join("?" * len(canonical_run_ids))

    run_meta = {
        r["run_id"]: dict(r)
        for r in conn.execute(
            f"SELECT run_id, run_date, regime, portfolio_value, cash, n_buys "
            f"FROM pipeline_runs WHERE run_id IN ({placeholders})",
            canonical_run_ids,
        ).fetchall()
    }
    blocked_rows = [
        dict(r)
        for r in conn.execute(
            f"""SELECT run_id, ticker, kelly_target_pct, mu, sigma, rank_score
                FROM candidate_scores
                WHERE run_id IN ({placeholders}) AND blocked_by = 'size_insufficient_cash' AND role = 'candidate'
                ORDER BY run_id, rank_score DESC""",
            canonical_run_ids,
        ).fetchall()
    ]

    needed = {(row["ticker"], run_meta[row["run_id"]]["run_date"]) for row in blocked_rows}
    closes: dict[str, dict] = {}
    ohlcv_root = Path(ohlcv_dir)
    for ticker, date in sorted(needed):
        df = pd.read_parquet(ohlcv_root / ticker / "1d.parquet")
        s = df["close"]
        s.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        key = f"{ticker}|{date}"
        if date in s.index:
            closes[key] = {"close": float(s.loc[date]), "source": "close(run_date)"}
        else:
            prior = s[s.index <= date]
            closes[key] = (
                {"close": float(prior.iloc[-1]), "source": f"close({prior.index[-1]},last<=run_date)"}
                if len(prior)
                else {"close": None, "source": "missing"}
            )

    return {
        "window": f"{start}..{end}",
        "canonical_run_selection_rule": (
            "For each calendar date, the canonical production run is the UNIQUE "
            "pipeline_runs row with n_candidates>0 on that date (structural, "
            "outcome-blind). Zero such rows = no daily-full session that day "
            "(excluded). 2+ such rows = AMBIGUOUS, excluded per fail-closed "
            "policy rather than picked by any heuristic."
        ),
        "canonical_run_manifest": manifest,
        "pipeline_run_metadata": run_meta,
        "candidate_rows_blocked_by_size": blocked_rows,
        "ohlcv_closes": closes,
    }


def compute_replay(bundle: dict) -> dict:
    """Pure function: no DB, no OHLCV file, no live path — everything it
    needs is already inline in `bundle`."""
    manifest = bundle["canonical_run_manifest"]
    run_meta = bundle["pipeline_run_metadata"]
    closes = bundle["ohlcv_closes"]

    by_run: dict[str, list] = defaultdict(list)
    for row in bundle["candidate_rows_blocked_by_size"]:
        by_run[row["run_id"]].append(row)

    per_date: dict[str, dict] = {}
    for run_id, cands in by_run.items():
        meta = run_meta[run_id]
        regime = meta["regime"]
        pv = float(meta["portfolio_value"])
        cash = float(meta["cash"])
        cap_pct = REGIME_CAP.get(regime, 0.15)
        res_pct = RESERVE.get(regime, 0.0)
        cap_dollars = cap_pct * pv
        leftover = max(cash - res_pct * pv, 0.0)
        rescued, not_rescued = [], []
        for c in cands:
            key = f"{c['ticker']}|{meta['run_date']}"
            price = closes.get(key, {}).get("close")
            if price is None:
                not_rescued.append({"ticker": c["ticker"], "reason": "UNPRICED"})
                continue
            if not (c["kelly_target_pct"] or 0) > 0:
                not_rescued.append({"ticker": c["ticker"], "reason": "max_pct==0"})
                continue
            if regime == "BEAR":
                not_rescued.append({"ticker": c["ticker"], "reason": "BEAR override"})
                continue
            if price > cap_dollars + 1e-6:
                not_rescued.append({"ticker": c["ticker"], "reason": f"1sh ${price:.2f} > cap ${cap_dollars:.2f}"})
                continue
            if price > leftover + 1e-6:
                not_rescued.append({"ticker": c["ticker"], "reason": f"1sh > leftover ${leftover:.2f}"})
                continue
            leftover -= price
            rescued.append({"ticker": c["ticker"], "price": price})
        per_date[meta["run_date"]] = {
            "run_id": run_id,
            "regime": regime,
            "rescued": rescued,
            "not_rescued": not_rescued,
            "delta_usd": sum(r["price"] for r in rescued),
        }

    deltas = [v["delta_usd"] for v in per_date.values() if v["delta_usd"] > 0]
    canonical_dates = [d for d, v in manifest["dates"].items() if v["status"] == "CANONICAL"]
    # The sealed renquant-artifacts RUN-LOCK.json only carries "window" nested
    # under canonical_run_manifest; this script's own --extract-produced
    # bundle also stamps a top-level copy. Accept either.
    window = bundle.get("window") or manifest.get("window")
    return {
        "window": window,
        "canonical_unambiguous_dates": len(canonical_dates),
        "canonical_dates_with_blocked_candidate": len(per_date),
        "canonical_dates_with_rescue": sum(1 for v in per_date.values() if v["rescued"]),
        "per_session_deployment_delta_usd": {
            "min": min(deltas) if deltas else 0,
            "max": max(deltas) if deltas else 0,
            "mean": sum(deltas) / len(deltas) if deltas else 0,
        },
        "per_date": per_date,
        "excluded_dates": {d: v for d, v in manifest["dates"].items() if v["status"] != "CANONICAL"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extract", action="store_true", help="Build the sealed bundle from the live ledger + OHLCV.")
    parser.add_argument("--db-path", help="Decision-ledger sqlite path (required with --extract).")
    parser.add_argument("--ohlcv-dir", help="OHLCV parquet root, <dir>/<TICKER>/1d.parquet (required with --extract).")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-10")
    parser.add_argument("--bundle", help="Sealed bundle JSON to compute from (required without --extract).")
    parser.add_argument("--out-bundle", help="Where to write the extracted bundle (with --extract).")
    parser.add_argument("--out", default="/dev/stdout", help="Where to write the computed results JSON.")
    args = parser.parse_args()

    if args.extract:
        if not args.db_path or not args.ohlcv_dir:
            parser.error("--extract requires --db-path and --ohlcv-dir (no default runtime)")
        bundle = extract_bundle(args.db_path, args.ohlcv_dir, args.start, args.end)
        if args.out_bundle:
            with open(args.out_bundle, "w") as f:
                json.dump(bundle, f, indent=1, sort_keys=True, default=str)
            print(f"wrote bundle: {args.out_bundle}", file=sys.stderr)
        results = compute_replay(bundle)
    else:
        if not args.bundle:
            parser.error("--bundle is required unless --extract is given (no default runtime)")
        with open(args.bundle) as f:
            bundle = json.load(f)
        results = compute_replay(bundle)

    with open(args.out, "w") as f:
        json.dump(results, f, indent=1, sort_keys=True, default=str)
    print(f"wrote results: {args.out}", file=sys.stderr)
    print(json.dumps(results["per_session_deployment_delta_usd"], indent=1), file=sys.stderr)


if __name__ == "__main__":
    main()
