"""S-TC: standing transfer coefficient measurement per run.

Replaces the reasoned ≈0.4 TC in the #231 §0 state vector with a measured
baseline. Scheduled as a daily batch job after live runs complete.

TC = corr(w_actual, w* ∝ kelly_target_pct) over admission-surviving candidates
per canonical daily run (Clarke–de Silva–Thorley 2002: IR = TC × IC × √BR).

Input: ~/renquant-data/runs.alpaca.db (read-only, candidate_scores + trades).
Output: ~/renquant-data/decision_ledger.db tc_metrics table (append-only).

See scripts/poc_transfer_coefficient.py for the methodology (rounds 1–3 of
Codex review). This module extracts the core computation; the POC remains the
reference for the admission taxonomy rationale.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .decision_ledger import DEFAULT_DB as LEDGER_DB

log = logging.getLogger(__name__)

MU_FLOOR = 0.03
MIN_FULL_RUN_CANDIDATES = 80
MIN_ELIGIBLE = 4
MIN_CORR_POP = 4

_PRE_SELECTION_BLOCKERS = frozenset({
    "wash_sale", "sector", "correlation", "tier", "defensive_non_bear",
    "candidate_not_selected",
})
_SIZING_FAILURES = frozenset({
    "buy_blocked", "skip_buys", "size_bad_price", "size_insufficient_cash",
    "size_cash_invariant", "kelly_zero:capped_zero", "bear_defensive_slot_cap",
    "bear_defensive_insufficient_cash",
})
_SELECTED_SUBMITTED = frozenset({"broker_pending_submitted"})
_BROKER_OUTCOME_PREFIX = "broker_skip:"

TC_DDL = """
CREATE TABLE IF NOT EXISTS tc_metrics (
  run_id TEXT PRIMARY KEY,
  run_date TEXT NOT NULL,
  category TEXT NOT NULL,
  buy_side_tc REAL,
  exposure_transfer_ratio REAL,
  n_eligible INTEGER NOT NULL,
  n_survived_admission INTEGER NOT NULL,
  n_corr_population INTEGER NOT NULL,
  n_bought INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tc_date ON tc_metrics(run_date);
"""


def _classify_reason(reason: str) -> str:
    if reason in _PRE_SELECTION_BLOCKERS:
        return "pre_selection_blocked"
    if reason in _SIZING_FAILURES:
        return "sizing_failed"
    if reason in _SELECTED_SUBMITTED:
        return "selected_submitted"
    if reason.startswith(_BROKER_OUTCOME_PREFIX):
        return "broker_outcome"
    return "unclassified"


def _canonical_daily_runs(runs_conn: sqlite3.Connection) -> list[dict[str, str]]:
    counts = pd.read_sql(
        "SELECT run_id, count(*) n FROM candidate_scores "
        "WHERE run_id LIKE '%-live-%' GROUP BY run_id "
        f"HAVING n >= {MIN_FULL_RUN_CANDIDATES}", runs_conn)
    if counts.empty:
        return []
    runs = pd.read_sql(
        "SELECT run_id, run_date, created_at FROM pipeline_runs "
        "WHERE run_id IN ({})".format(",".join("?" * len(counts))),
        runs_conn, params=counts["run_id"].tolist())
    runs = runs.merge(counts, on="run_id")
    runs["created_at"] = pd.to_datetime(runs["created_at"])
    idx = runs.groupby("run_date")["created_at"].idxmax()
    canonical = runs.loc[idx].sort_values("run_date")
    return [
        {"run_id": r["run_id"], "run_date": r["run_date"]}
        for _, r in canonical.iterrows()
    ]


def compute_buy_side_tc(runs_conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    cs = pd.read_sql(
        "SELECT ticker, role, mu, kelly_target_pct, blocked_by "
        "FROM candidate_scores WHERE run_id=? AND role='candidate'",
        runs_conn, params=(run_id,))
    elig = cs[(cs["mu"] >= MU_FLOOR) & cs["kelly_target_pct"].notna()].copy()
    if len(elig) < MIN_ELIGIBLE:
        return None

    has_reason = elig["blocked_by"].notna() & (elig["blocked_by"].str.len() > 0)
    elig = elig.copy()
    elig["_stage"] = "selected_filled"
    elig.loc[has_reason, "_stage"] = elig.loc[has_reason, "blocked_by"].map(_classify_reason)

    pre_selection_mask = elig["_stage"] == "pre_selection_blocked"
    unclassified_mask = elig["_stage"] == "unclassified"
    survived = elig.loc[~(pre_selection_mask | unclassified_mask)].copy()
    n_survived = int(len(survived))

    if n_survived < MIN_CORR_POP:
        return {
            "run_id": run_id,
            "category": "insufficient_sizing_population",
            "buy_side_tc": None,
            "exposure_transfer_ratio": None,
            "n_eligible": int(len(elig)),
            "n_survived_admission": n_survived,
            "n_corr_population": 0,
            "n_bought": 0,
        }

    tr = pd.read_sql(
        "SELECT ticker, target_pct FROM trades WHERE run_id=? AND action LIKE 'buy%'",
        runs_conn, params=(run_id,))
    actual = dict(zip(tr["ticker"], tr["target_pct"]))
    survived["w_actual"] = survived["ticker"].map(actual)

    pending_mask = (
        (survived["_stage"] == "selected_submitted") & survived["w_actual"].isna()
    )
    survived["w_actual"] = survived["w_actual"].fillna(0.0)
    corr_pop = survived.loc[~pending_mask].copy()
    n_bought = int((corr_pop["w_actual"] > 0).sum())

    if len(corr_pop) < MIN_CORR_POP:
        category = "insufficient_corr_population"
        tc = None
    elif n_bought == 0:
        category = "no_deployment"
        tc = None
    elif corr_pop["w_actual"].std() == 0 or corr_pop["kelly_target_pct"].std() == 0:
        category = "zero_dispersion"
        tc = None
    else:
        category = "measured"
        tc = float(np.corrcoef(corr_pop["kelly_target_pct"], corr_pop["w_actual"])[0, 1])

    denom = float(np.dot(corr_pop["kelly_target_pct"], corr_pop["kelly_target_pct"])) if len(corr_pop) else 0.0
    etr = (
        round(float(np.dot(corr_pop["w_actual"], corr_pop["kelly_target_pct"])) / denom, 6)
        if denom > 0 else None
    )

    return {
        "run_id": run_id,
        "category": category,
        "buy_side_tc": round(tc, 6) if tc is not None else None,
        "exposure_transfer_ratio": etr,
        "n_eligible": int(len(elig)),
        "n_survived_admission": n_survived,
        "n_corr_population": int(len(corr_pop)),
        "n_bought": n_bought,
    }


def _ensure_table(ledger_conn: sqlite3.Connection) -> None:
    ledger_conn.executescript(TC_DDL)


def _already_measured(ledger_conn: sqlite3.Connection) -> set[str]:
    try:
        rows = ledger_conn.execute("SELECT run_id FROM tc_metrics").fetchall()
        return {r[0] for r in rows}
    except sqlite3.OperationalError:
        return set()


def run_measurement(
    runs_db: str | Path,
    ledger_db: str | Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if ledger_db is None:
        ledger_db = LEDGER_DB

    runs_conn = sqlite3.connect(str(runs_db))
    ledger_conn = sqlite3.connect(str(ledger_db), timeout=10)
    ledger_conn.execute("PRAGMA journal_mode=WAL")
    ledger_conn.execute("PRAGMA busy_timeout=5000")
    _ensure_table(ledger_conn)

    canonical = _canonical_daily_runs(runs_conn)
    measured_ids = _already_measured(ledger_conn)
    new_runs = [r for r in canonical if r["run_id"] not in measured_ids]

    results = []
    for run in new_runs:
        tc_result = compute_buy_side_tc(runs_conn, run["run_id"])
        if tc_result is None:
            continue
        tc_result["run_date"] = run["run_date"]
        results.append(tc_result)

    written = 0
    if not dry_run and results:
        ledger_conn.executemany(
            "INSERT OR IGNORE INTO tc_metrics "
            "(run_id, run_date, category, buy_side_tc, exposure_transfer_ratio, "
            "n_eligible, n_survived_admission, n_corr_population, n_bought) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["run_id"], r["run_date"], r["category"], r["buy_side_tc"],
                 r["exposure_transfer_ratio"], r["n_eligible"],
                 r["n_survived_admission"], r["n_corr_population"], r["n_bought"])
                for r in results
            ],
        )
        ledger_conn.commit()
        written = len(results)

    all_tc = ledger_conn.execute(
        "SELECT buy_side_tc FROM tc_metrics WHERE category='measured' "
        "ORDER BY run_date"
    ).fetchall()
    tc_values = [r[0] for r in all_tc if r[0] is not None]
    n_measured = len(tc_values)

    import math
    summary = {
        "n_canonical_runs": len(canonical),
        "n_already_measured": len(measured_ids),
        "n_new_computed": len(results),
        "n_written": written,
        "tc_mean": round(float(np.mean(tc_values)), 3) if n_measured else None,
        "tc_se": (
            round(float(np.std(tc_values, ddof=1) / math.sqrt(n_measured)), 3)
            if n_measured >= 2 else None
        ),
        "tc_n_measured": n_measured,
    }

    runs_conn.close()
    ledger_conn.close()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S-TC: measure transfer coefficient per run")
    parser.add_argument("--runs-db", type=Path, help="Path to runs.alpaca.db")
    parser.add_argument("--ledger-db", type=Path, help="Path to decision_ledger.db")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't persist")
    args = parser.parse_args(argv or [])

    import os
    runs_db = args.runs_db or Path(
        os.environ.get("RQ_ROOT", str(Path.home() / "git/github/RenQuant"))
    ) / "data/runs.alpaca.db"

    summary = run_measurement(
        runs_db=runs_db,
        ledger_db=args.ledger_db,
        dry_run=args.dry_run,
    )

    log.info(
        "S-TC: %d new runs computed, %d written; rolling TC mean=%.3f (SE=%.3f, n=%d)",
        summary["n_new_computed"],
        summary["n_written"],
        summary["tc_mean"] or 0,
        summary["tc_se"] or 0,
        summary["tc_n_measured"],
    )
    print(json.dumps(summary, indent=2))
    return 0
