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

Three modes (Codex review of orchestrator#471, 2026-07-11 — r1 hardcoded a
one-off /private/tmp scratch path and /Users/renhao/git/github/RenQuant,
and picked each date's "representative" run by MAXIMUM outcome among all
same-day rows with a denominator mismatched against that selection; r2
fixed both but Codex's r3 review found two more validity gaps: the
canonical query never constrained run_type='live' (a shadow/candidate-
scoring run could become "the representative" solely on n_candidates>0),
and the regime cap/reserve values were a hardcoded table with no
fingerprinted proof they were the operative pinned config — this revision
fixes both, plus adds an explicit n_buys==0 assertion the "zero admission
distortion" claim depends on but never checked):

  --extract   READ-ONLY: queries the live decision ledger (--db-path),
              OHLCV parquet (--ohlcv-dir), and the renquant-strategy-104
              git history (--strategy-repo) to resolve, per canonical run,
              the EXACT pinned regime_params.{max_position_pct,
              cash_reserve_pct} operative at that run's created_at
              timestamp (git commit + file content sha256 sealed
              alongside the extracted values — never a hand-copied
              table). Predeclares exactly one canonical run_type='live'
              run_id per date via a STRUCTURAL rule blind to outcome (the
              unique pipeline_runs row with run_type='live' AND
              n_candidates>0 that date), fails closed to EXCLUDED on any
              date with zero or 2+ such LIVE rows, and writes a
              self-contained sealed bundle (--out-bundle) — no DB/OHLCV/
              strategy-config access needed to reproduce results from it
              afterward.

  (default)   Computes results PURELY from a sealed bundle (--bundle,
              e.g. a renquant-artifacts store:// checkout) — no DB,
              OHLCV file, strategy-config checkout, or umbrella path
              needed. This is the reproducible, verifiable path; a clean
              checkout with only this script and the sealed bundle
              produces byte-identical results. Fails closed (excludes the
              date, does not silently continue) on any canonical run
              whose sealed n_buys != 0 — the "zero admission distortion"
              claim depends on n_buys==0 and this script does not
              reconstruct normal-buy cash state for the nonzero case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def resolve_regime_sizing_config(strategy_repo: str, created_at: str, regime: str) -> dict:
    """Resolve the EXACT pinned regime_params.{max_position_pct,
    cash_reserve_pct} operative in renquant-strategy-104's
    configs/strategy_config.json as of `created_at` (the commit most
    recently touching that file at or before the run's timestamp) — never
    a hand-copied constant. Seals the commit sha + file content sha256 as
    an independently-verifiable ref alongside the extracted values."""
    commit = subprocess.run(
        ["git", "-C", strategy_repo, "log", "-1", "--format=%H",
         f"--before={created_at}", "--", "configs/strategy_config.json"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not commit:
        raise SystemExit(
            f"no configs/strategy_config.json commit found at or before "
            f"{created_at!r} in {strategy_repo!r} — cannot resolve the "
            "operative sizing config, refusing to guess"
        )
    file_bytes = subprocess.run(
        ["git", "-C", strategy_repo, "show", f"{commit}:configs/strategy_config.json"],
        capture_output=True, check=True,
    ).stdout
    cfg = json.loads(file_bytes)
    regime_cfg = cfg.get("regime_params", {}).get(regime)
    if regime_cfg is None or "max_position_pct" not in regime_cfg or "cash_reserve_pct" not in regime_cfg:
        raise SystemExit(
            f"commit {commit} configs/strategy_config.json has no "
            f"regime_params.{regime}.{{max_position_pct,cash_reserve_pct}} "
            "— cannot resolve the operative sizing config, refusing to guess"
        )
    return {
        "config_commit_sha": commit,
        "config_file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "max_position_pct": float(regime_cfg["max_position_pct"]),
        "cash_reserve_pct": float(regime_cfg["cash_reserve_pct"]),
    }


def build_canonical_manifest(conn: sqlite3.Connection, start: str, end: str) -> dict:
    """Predeclare exactly one canonical (real daily-full, LIVE,
    candidate-scoring) run_id per calendar date — a structural rule blind
    to outcome, never chosen by which run looks best. run_type='live' is
    an explicit filter (Codex r3): a shadow/other candidate-scoring run
    must never become "the representative" solely because it has
    candidates. Fails closed (EXCLUDED, with the concrete reason) on any
    date with zero or 2+ qualifying LIVE rows."""
    all_dates = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM pipeline_runs "
            "WHERE run_date >= ? AND run_date <= ? AND run_type = 'live' ORDER BY run_date",
            (start, end),
        ).fetchall()
    ]
    cand_runs = conn.execute(
        """SELECT run_date, run_id, created_at, n_candidates FROM pipeline_runs
           WHERE run_date >= ? AND run_date <= ? AND run_type = 'live' AND n_candidates > 0
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
                "reason": "no run_type='live' pipeline_runs row with n_candidates>0 on this "
                          "date (no daily-full live candidate-scoring session found)",
            }
        elif len(runs) == 1:
            dates[d] = {
                "status": "CANONICAL", "run_id": runs[0]["run_id"],
                "created_at": runs[0]["created_at"], "run_type": "live",
            }
        else:
            dates[d] = {
                "status": "EXCLUDED_AMBIGUOUS",
                "reason": f"{len(runs)} run_type='live' candidate-scoring runs on this date "
                          "with no principled tie-break rule available; excluded per "
                          "fail-closed policy rather than picking by outcome",
                "candidate_run_ids": runs,
            }
    return {"window": f"{start}..{end}", "dates": dates}


def extract_bundle(db_path: str, ohlcv_dir: str, strategy_repo: str, start: str, end: str) -> dict:
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
            f"SELECT run_id, run_date, run_type, regime, portfolio_value, cash, n_buys, created_at "
            f"FROM pipeline_runs WHERE run_id IN ({placeholders})",
            canonical_run_ids,
        ).fetchall()
    }
    for run_id, meta in run_meta.items():
        meta["regime_sizing_config"] = resolve_regime_sizing_config(
            strategy_repo, meta["created_at"], meta["regime"],
        )
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
            "run_type='live' pipeline_runs row with n_candidates>0 on that date "
            "(structural, outcome-blind). Zero such rows = no daily-full live "
            "session that day (excluded). 2+ such rows = AMBIGUOUS, excluded per "
            "fail-closed policy rather than picked by any heuristic."
        ),
        "canonical_run_manifest": manifest,
        "pipeline_run_metadata": run_meta,
        "candidate_rows_blocked_by_size": blocked_rows,
        "ohlcv_closes": closes,
    }


def compute_replay(bundle: dict) -> dict:
    """Pure function: no DB, no OHLCV file, no strategy-config checkout,
    no live path — everything it needs is already inline in `bundle`."""
    manifest = bundle["canonical_run_manifest"]
    run_meta = bundle["pipeline_run_metadata"]
    closes = bundle["ohlcv_closes"]

    by_run: dict[str, list] = defaultdict(list)
    for row in bundle["candidate_rows_blocked_by_size"]:
        by_run[row["run_id"]].append(row)

    per_date: dict[str, dict] = {}
    excluded_nonzero_n_buys: dict[str, dict] = {}
    for run_id, cands in by_run.items():
        meta = run_meta[run_id]
        # The "zero admission distortion" claim (a deferred floor rescue
        # never displaces a normal-sized buy) structurally depends on
        # n_buys==0 for this run — this script does not reconstruct the
        # normal-buy cash state for the nonzero case, so it fails closed
        # (excludes the date) rather than silently assuming non-
        # displacement (Codex r3 review).
        if int(meta.get("n_buys") or 0) != 0:
            excluded_nonzero_n_buys[meta["run_date"]] = {
                "run_id": run_id, "n_buys": meta["n_buys"],
                "reason": "n_buys != 0 — zero-admission-distortion claim unverified for "
                          "this run without cash-state reconstruction (not implemented); "
                          "excluded rather than assumed",
            }
            continue
        regime = meta["regime"]
        pv = float(meta["portfolio_value"])
        cash = float(meta["cash"])
        sizing = meta["regime_sizing_config"]
        cap_pct = sizing["max_position_pct"]
        res_pct = sizing["cash_reserve_pct"]
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
            "regime_sizing_config": sizing,
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
        "canonical_dates_with_blocked_candidate": len(per_date) + len(excluded_nonzero_n_buys),
        "canonical_dates_with_rescue": sum(1 for v in per_date.values() if v["rescued"]),
        "per_session_deployment_delta_usd": {
            "min": min(deltas) if deltas else 0,
            "max": max(deltas) if deltas else 0,
            "mean": sum(deltas) / len(deltas) if deltas else 0,
        },
        "per_date": per_date,
        "excluded_dates": {d: v for d, v in manifest["dates"].items() if v["status"] != "CANONICAL"},
        "excluded_nonzero_n_buys": excluded_nonzero_n_buys,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extract", action="store_true", help="Build the sealed bundle from the live ledger + OHLCV.")
    parser.add_argument("--db-path", help="Decision-ledger sqlite path (required with --extract).")
    parser.add_argument("--ohlcv-dir", help="OHLCV parquet root, <dir>/<TICKER>/1d.parquet (required with --extract).")
    parser.add_argument("--strategy-repo", help="renquant-strategy-104 git checkout, for resolving the exact pinned "
                                                 "regime cap/reserve config per run (required with --extract).")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-10")
    parser.add_argument("--bundle", help="Sealed bundle JSON to compute from (required without --extract).")
    parser.add_argument("--out-bundle", help="Where to write the extracted bundle (with --extract).")
    parser.add_argument("--out", default="/dev/stdout", help="Where to write the computed results JSON.")
    args = parser.parse_args()

    if args.extract:
        if not args.db_path or not args.ohlcv_dir or not args.strategy_repo:
            parser.error("--extract requires --db-path, --ohlcv-dir, and --strategy-repo (no default runtime)")
        bundle = extract_bundle(args.db_path, args.ohlcv_dir, args.strategy_repo, args.start, args.end)
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
