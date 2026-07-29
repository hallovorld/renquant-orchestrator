#!/usr/bin/env python
"""Blend shadow readout — pipeline#213 rollout piece 3/3.

Daily after the 104 run: join the production candidate scores
(runs.alpaca.db::candidate_scores) with the shadow classifier's recorded
comparison table (MLflow artifact), compute the frozen blend
z(prod)+z(clf) per date, append both arms' top-10 picks to an append-only
ledger, and back-fill realized fwd_60d spreads from ticker_forward_returns
once rows mature. Alarms (non-zero exit → launchd surfaces) when a live
run exists but the shadow leg is missing — the GOAL-1 AC3 silent-feed
guard the #213 design requires.

READ-ONLY against every production surface; writes ONLY the ledger under
``data/rq104_blend_readout/`` (additive). The INFO/GATE reads themselves
are ANALYSIS runs over this ledger per the frozen rule — this job only
accumulates the evidence.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

TOP_N = 10
SHADOW_NAME = "topdecile_clf_blend_leg"
MATURITY_TDAYS = 61          # fwd_60d + 1 session settle (was 21 for
                             # fwd_20d; changed with the horizon 2026-07-29 —
                             # leaving it at 21 would have marked rows mature
                             # 40 sessions before their label can exist)
MIN_FULL_RUN_CANDIDATES = 80  # matches scripts/kpi_scorecard.py / poc_transfer_coefficient.py


def zsum_blend(prod: pd.Series, clf: pd.Series) -> pd.Series:
    """The FROZEN blend: per-date z(prod) + z(clf) on common tickers.
    Tickers missing a clf score keep z(prod) only (clf term 0) — mirrors
    the confirmatory construction's NaN handling."""
    common = prod.index
    def z(s: pd.Series) -> pd.Series:
        sd = s.std()
        return (s - s.mean()) / (sd if sd and not np.isnan(sd) else 1.0)
    zp = z(prod)
    zc = z(clf.reindex(common)).fillna(0.0)
    return zp + zc


def top_n(scores: pd.Series, n: int = TOP_N) -> list[str]:
    """Deterministic top-N: score desc, ticker asc as the tie-break."""
    df = scores.rename("s").reset_index()
    df.columns = ["ticker", "s"]
    df = df.sort_values(["s", "ticker"], ascending=[False, True])
    return df.head(n)["ticker"].tolist()


def latest_live_run(db: sqlite3.Connection) -> tuple[str, str] | None:
    """Canonical latest FULL live run: join `pipeline_runs` (run_type='live'),
    restrict to runs whose `candidate_scores` row count >= MIN_FULL_RUN_CANDIDATES,
    and pick the one with the latest `created_at`. NOT raw `candidate_scores`
    rowid order — an intraday/partial run can insert rows after the post-close
    full run and must never silently supersede it (same class of bug/fix as
    scripts/kpi_scorecard.py:142-159 and scripts/poc_transfer_coefficient.py:201-218)."""
    counts = pd.read_sql_query(
        "SELECT run_id, COUNT(*) n FROM candidate_scores GROUP BY run_id "
        f"HAVING n >= {MIN_FULL_RUN_CANDIDATES}", db)
    if counts.empty:
        return None
    runs = pd.read_sql_query(
        "SELECT run_id, run_date, created_at FROM pipeline_runs "
        "WHERE run_type = 'live' AND run_id IN ({})".format(
            ",".join("?" * len(counts))),
        db, params=counts["run_id"].tolist())
    if runs.empty:
        return None
    runs["created_at"] = pd.to_datetime(runs["created_at"])
    row = runs.sort_values("created_at").iloc[-1]
    return row["run_id"], str(row["run_date"])[:10]


def prod_scores(db: sqlite3.Connection, run_id: str) -> pd.Series:
    df = pd.read_sql_query(
        "SELECT ticker, panel_score FROM candidate_scores "
        "WHERE run_id = ? AND panel_score IS NOT NULL", db, params=(run_id,))
    return df.set_index("ticker")["panel_score"]


def shadow_scores_for(run_date: str, mlruns: Path) -> pd.Series | None:
    """Find the shadow comparison table logged for `run_date` and return the
    clf scores. v1 locator: newest comparison.json whose payload row-set
    tags the date (falls back to file mtime date match)."""
    candidates = sorted(mlruns.rglob("comparison.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates[:20]:
        try:
            raw = json.loads(p.read_text())
            df = pd.DataFrame(raw["data"], columns=raw["columns"])
        except Exception:
            continue
        if "shadow_score" not in df.columns or "ticker" not in df.columns:
            continue
        if "run_date" in df.columns and str(df["run_date"].iloc[0])[:10] != run_date:
            continue
        if "run_date" not in df.columns:
            mdate = date.fromtimestamp(p.stat().st_mtime).isoformat()
            if mdate != run_date:
                continue
        if "shadow_name" in df.columns and \
                df["shadow_name"].iloc[0] != SHADOW_NAME:
            continue
        return df.set_index("ticker")["shadow_score"].astype(float)
    return None


def append_ledger(ledger: Path, row: dict) -> bool:
    """Append-only, idempotent per run_date."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if line and json.loads(line).get("run_date") == row["run_date"]:
                return False
    with ledger.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return True


def mature_fill(ledger: Path, db: sqlite3.Connection) -> int:
    """Fill realized fwd_60d spreads for rows old enough, in place.

    HORIZON: fwd_60d, changed from fwd_20d on 2026-07-29 by operator decision.
    The certified effect (+0.0687, CI lower +0.0156) and BOTH scored models are
    fwd_60d recipes; a 20-day spread measures a different quantity, so the
    120-session forward ledger would have answered a question the certification
    never asked. GOAL-6 Stage 0 separately measured that the shorter horizon
    buys no statistical power either (H2 NOT SUPPORTED: ~3x the independent
    blocks, proportionately smaller effect, flat ratio) — so there was not even
    a speed argument for keeping it.

    Cost, stated: a session now matures after 60 trading days instead of 20,
    so realized rows arrive ~40 trading days later than they would have.
    """
    if not ledger.exists():
        return 0
    rows = [json.loads(x) for x in ledger.read_text().splitlines() if x]
    try:
        fwd = pd.read_sql_query(
            "SELECT ticker, as_of_date, fwd_60d FROM ticker_forward_returns "
            "WHERE fwd_60d IS NOT NULL", db)
    except Exception:
        return 0
    fwd["as_of_date"] = fwd["as_of_date"].astype(str).str[:10]
    fmap = {(r.ticker, r.as_of_date): r.fwd_60d for r in fwd.itertuples(index=False)}
    filled = 0
    for row in rows:
        if row.get("realized"):
            continue
        d = row["run_date"]
        rp = [fmap.get((t, d)) for t in row["picks_prod"]]
        rb = [fmap.get((t, d)) for t in row["picks_blend"]]
        # Telemetry, recorded on EVERY pass and for every row, resolved or not.
        # Realization is all-or-nothing by design (a spread over a partial pick
        # set is a different statistic and the readout rule is frozen), which
        # means one unresolvable ticker silently drops that session from the
        # evidence FOREVER. Coverage is 100% on every realized date measured
        # 2026-07-29, but the same table also holds dates carrying only 2-3
        # tickers — a session landing on one of those would vanish without a
        # trace. These counters make that visible without altering the
        # statistic or the realization criterion.
        row["n_resolvable_prod"] = sum(v is not None for v in rp)
        row["n_resolvable_blend"] = sum(v is not None for v in rb)
        row["n_picks_prod"] = len(rp)
        row["n_picks_blend"] = len(rb)
        if all(v is not None for v in rp + rb):
            row["spread_prod"] = float(np.mean(rp))
            row["spread_blend"] = float(np.mean(rb))
            row["realized"] = True
            filled += 1
    # Write whenever anything changed — including telemetry-only updates, so a
    # session that is stuck unresolvable shows WHY on the next pass rather than
    # looking untouched.
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return filled


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-dir", default="/Users/renhao/git/github/RenQuant")
    ap.add_argument("--ledger", default=None)
    args = ap.parse_args()
    repo = Path(args.repo_dir)
    ledger = Path(args.ledger) if args.ledger else \
        repo / "data" / "rq104_blend_readout" / "ledger.jsonl"

    db = sqlite3.connect(str(repo / "data" / "runs.alpaca.db"))
    run = latest_live_run(db)
    if run is None:
        print("no live runs in candidate_scores — nothing to do")
        return 0
    run_id, run_date = run
    today = date.today().isoformat()

    n_filled = mature_fill(ledger, db)
    if n_filled:
        print(f"matured: filled {n_filled} ledger row(s)")

    if run_date != today:
        print(f"latest live run is {run_date} (not today) — no new session")
        return 0

    prod = prod_scores(db, run_id)
    if prod.empty:
        print(f"run {run_id}: no prod candidate scores — skip")
        return 0
    clf = shadow_scores_for(run_date, repo / "mlruns")
    if clf is None:
        print(f"ALARM: live run {run_id} exists but NO shadow comparison "
              f"for {SHADOW_NAME} was recorded — silent shadow feed "
              f"(GOAL-1 AC3). Investigate shadow health record.")
        return 2
    blend = zsum_blend(prod, clf)
    row = {"run_date": run_date, "run_id": run_id,
           "n_candidates": int(len(prod)),
           "n_clf_scored": int(clf.reindex(prod.index).notna().sum()),
           "picks_prod": top_n(prod), "picks_blend": top_n(blend),
           "realized": False}
    appended = append_ledger(ledger, row)
    if appended:
        print(f"session appended: {run_date} "
              f"(prod∩blend picks overlap "
              f"{len(set(row['picks_prod']) & set(row['picks_blend']))}/10)")
        _notify_picks(row)
    else:
        print(f"session {run_date} already in ledger — idempotent skip")
    return 0


def _notify_picks(row: dict) -> None:
    """Operator-visibility INFO ntfy (2026-07-27 operator directive): the
    day's hypothetical blend top-10 vs prod, sent once per appended session
    (idempotent-skip paths never re-notify). Best-effort — a notify failure
    must never fail the ledger job."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from liveness_common import alert  # noqa: PLC0415
        prod_set = set(row["picks_prod"])
        blend_set = set(row["picks_blend"])
        added = [t for t in row["picks_blend"] if t not in prod_set]
        dropped = [t for t in row["picks_prod"] if t not in blend_set]
        alert(
            f"rq104 blend 假想前10 — {row['run_date']}",
            (f"blend: {' '.join(row['picks_blend'])}\n"
             f"prod:  {' '.join(row['picks_prod'])}\n"
             f"分歧 {len(added)}/10: +{' +'.join(added) if added else '-'} / "
             f"-{' -'.join(dropped) if dropped else '-'}\n"
             f"clf 覆盖 {row['n_clf_scored']}/{row['n_candidates']}（陪跑记账，仅假想，不下单）"),
            rq_root=None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"notify skipped (non-fatal): {exc}")


if __name__ == "__main__":
    sys.exit(main())
