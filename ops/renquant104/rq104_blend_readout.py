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
import os
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
                             # 40 sessions before their label can exist).
                             # ACTIVE GATE: enforced by `_aged_dates()` below,
                             # not by `fwd_60d IS NOT NULL` alone — see that
                             # function's docstring (Codex BLOCKER, PR #598).
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


def log_skip(path: Path, why: str) -> None:
    """Say WHY a candidate table was refused. The prior code skipped silently,
    so an operator could not tell 'no shadow ran' from 'we could not tell which
    shadow ran'."""
    print(f"  skip {path.parent.name}/{path.name}: {why}")


def _resolve_shadow_name(df: pd.DataFrame, path: Path) -> str | None:
    """Which shadow produced this table? None means UNKNOWABLE, never 'fine'.

    Two sources, in order of authority:
      1. a ``shadow_name`` column in the payload (present on newer writers);
      2. the MLflow run tag ``<run_dir>/tags/shadow_name`` — the run directory is
         found by walking up from the artifact until a ``tags`` directory exists,
         because comparison.json sits under ``<run>/artifacts/...`` at a depth
         this function should not hardcode.

    Returning None is the fail-closed signal. A caller must NOT treat an
    unresolved identity as a match.
    """
    if "shadow_name" in df.columns and len(df):
        value = df["shadow_name"].iloc[0]
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    for parent in list(path.parents)[:6]:
        tag = parent / "tags" / "shadow_name"
        try:
            if tag.is_file():
                text = tag.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None


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
        # Identity must be ESTABLISHED, not merely un-contradicted.
        #
        # This read `if "shadow_name" in df.columns and df[...] != SHADOW_NAME:
        # continue` — so a table with NO shadow_name column fell through and was
        # accepted as the clf's. Measured 2026-07-30: 0 of the 40 newest
        # comparison.json files carry a `shadow_name` (or `run_date`) column, so
        # the only model-identity check in this path NEVER EXECUTED.
        #
        # That is not a theoretical exposure. Three shadows write `shadow_score`
        # tables: on 2026-07-28 the two newest of the day were
        # `xgb_alpha158_fund_previous_primary`, not the clf; and on 2026-07-29 the
        # clf and PatchTST tables were logged 25.7 MILLISECONDS apart with
        # identical 78-row shapes, so the mtime fallback above cannot possibly
        # discriminate between them. Identity resolution is the only discriminator
        # there is. And because `append_ledger` is idempotent per run_date, a
        # mis-attribution is written once and never corrected — permanently and
        # silently wrong.
        #
        # Identity IS available: MLflow records it as the run tag
        # `<run_dir>/tags/shadow_name`, which this function never read.
        name = _resolve_shadow_name(df, p)
        if name is None:
            log_skip(p, "identity unresolved (no shadow_name column and no "
                        "MLflow tags/shadow_name) — refusing to attribute")
            continue
        if name != SHADOW_NAME:
            log_skip(p, f"shadow_name={name!r} != {SHADOW_NAME!r}")
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


def _aged_dates(db: sqlite3.Connection, min_tdays: int) -> set[str]:
    """Trading dates whose full ``min_tdays``-session forward label has elapsed.

    ``ticker_forward_returns.fwd_60d IS NOT NULL`` on a row does NOT by itself
    prove the date is aged: the same table can carry a row written before its
    full horizon elapsed (see ``scripts/research_panel_exit_predictiveness.py``'s
    "TRADING-SESSION AGING" note — Codex r2 #2 finding — on this exact table).
    We age against the table's own distinct ``as_of_date`` session calendar
    instead, same technique as that script's ``_session_calendar``/
    ``_aged_cutoff``: a date is aged iff at least ``min_tdays`` LATER sessions
    are already present in the calendar.
    """
    sessions = pd.read_sql_query(
        "SELECT DISTINCT as_of_date FROM ticker_forward_returns "
        "ORDER BY as_of_date", db,
    )["as_of_date"].astype(str).str[:10].tolist()
    if len(sessions) <= min_tdays:
        return set()
    return set(sessions[: len(sessions) - min_tdays])


def mature_fill(ledger: Path, db: sqlite3.Connection) -> int:
    """Fill realized fwd_60d spreads for rows old enough, in place.

    HORIZON: fwd_60d, changed from fwd_20d on 2026-07-29, quoted as an
    operator decision but not independently checkable from this repo (see
    doc/progress/2026-07-29-blend-readout-horizon.md's `best-known?` field).
    The certified effect (+0.0687, CI lower +0.0156) and BOTH scored models are
    fwd_60d recipes; a 20-day spread measures a different quantity, so the
    120-session forward ledger would have answered a question the certification
    never asked. GOAL-6 Stage 0 separately measured that the shorter horizon
    buys no statistical power either (H2 NOT SUPPORTED: ~3x the independent
    blocks, proportionately smaller effect, flat ratio) — so there was not even
    a speed argument for keeping it.

    Cost, stated: a session now matures after 60 trading days instead of 20,
    so realized rows arrive ~40 trading days later than they would have.

    MATURITY GATE (Codex BLOCKER, PR #598): a row only realizes once its
    ``run_date`` is in ``_aged_dates(db, MATURITY_TDAYS)`` — i.e. at least
    ``MATURITY_TDAYS`` later trading sessions already exist in
    ``ticker_forward_returns``. This is enforced IN ADDITION to (not instead
    of) the existing all-picks-resolvable check, so a prematurely-written
    ``fwd_60d`` value cannot realize a session before its label window has
    actually elapsed.
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
    aged = _aged_dates(db, MATURITY_TDAYS)
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
        row["aged"] = d in aged
        if row["aged"] and all(v is not None for v in rp + rb):
            row["spread_prod"] = float(np.mean(rp))
            row["spread_blend"] = float(np.mean(rb))
            row["realized"] = True
            filled += 1
    # WHENEVER ANYTHING CHANGED — now actually. This comment has said "write whenever
    # anything changed" since the function was written, and the line under it wrote
    # UNCONDITIONALLY: no comparison, no `if`. Measured 2026-08-01 by running the readout
    # on a non-session day with `filled == 0` — the live ledger's mtime moved anyway.
    #
    # Two consequences, neither cosmetic:
    #   * READING THE EVIDENCE MUTATED IT. Any diagnostic invocation rewrote an
    #     append-only ledger. That is how an analysis pass becomes a write to a live data
    #     surface — the thing the append-only design exists to prevent.
    #   * A CRASH TRUNCATED IT. `write_text` truncates and then writes; an interrupt
    #     between those leaves an empty or partial ledger, and no other copy of these
    #     sessions exists.
    #
    # Fixed by comparing rendered bytes against what is on disk — which preserves the
    # original intent exactly, since a telemetry-only update still differs and still
    # writes — and by temp file + `os.replace`, atomic on POSIX, so an interrupted run
    # leaves the previous ledger intact.
    rendered = "".join(json.dumps(r) + "\n" for r in rows)
    try:
        current = ledger.read_text()
    except OSError:
        current = None          # unreadable/absent -> write; NOT "assume it matches"
    if current != rendered:
        tmp = ledger.with_name(ledger.name + ".tmp")
        tmp.write_text(rendered)
        os.replace(tmp, ledger)
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
