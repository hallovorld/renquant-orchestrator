"""Backfill decision_outcomes from candidate_scores + ticker_forward_returns.

PROVENANCE WARNING — RECONSTRUCTED SUBSTRATE, NOT AUTHORITATIVE LIVE TRUTH.
This backfiller infers gate verdicts from the ``blocked_by`` column in
``candidate_scores``, which is a pipeline annotation, NOT a real-time ledger
event. The mapping (blocked_by prefix → gate name) is heuristic. Downstream
consumers (e.g. ``decision_outcome_validator``) should treat results as
reconstructed/approximate and should NOT cite them as definitive live-ledger
measurements without explicit qualification. The authoritative source for
gate verdicts will be the live decision_ledger once #133 is wired.

Bridges the per-ticker gate verdicts recorded in candidate_scores.blocked_by
(from pipeline runs in runs.alpaca.db) to the decision_outcomes table (in
decision_ledger.db). This is the collector that populates the S5 readiness
substrate and enables the decision_outcome_validator to run on real data.

READ-ONLY on the runs DB. WRITE to the ledger/attribution DB only (via the
existing write_outcomes helper).

Data flow:
  runs.alpaca.db:candidate_scores  →  per-ticker gate verdicts (allow/block)
  runs.alpaca.db:ticker_forward_returns  →  fwd_5d, fwd_20d, fwd_60d returns
  decision_ledger.db:decision_outcomes  ←  joined outcome rows (INSERT OR IGNORE)

The gate mapping:
  - blocked_by IS NULL AND selected = 1  →  verdict "allow", gate "admission"
  - blocked_by starts with a known prefix  →  verdict "block", gate from prefix
  - blocked_by IS NULL AND selected = 0  →  verdict "block", gate "qp_not_selected"
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RUNS_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"

GATE_PREFIXES = {
    "veto:": "VetoWeakBuys",
    "regime_admission:": "RegimeAdmission",
    "conviction:": "ConvictionGate",
    "panel_fundamentals": "FundamentalsFail",
    "qp_admission": "QPAdmission",
    "qp_no_trade": "QPNoTrade",
    "qp_delta": "QPDelta",
    "qp_global": "QPGlobal",
    "qp_soft_sell": "QPSoftSell",
    "kelly_zero": "KellySizing",
    "size_": "SizeGate",
    "correlation": "CorrelationGate",
}


def _map_gate(blocked_by: str | None, selected: int) -> tuple[str, str]:
    """Map candidate_scores.blocked_by to (gate, verdict)."""
    if blocked_by is None or blocked_by == "":
        if selected:
            return "admission", "allow"
        return "qp_not_selected", "block"
    blocked = blocked_by.lower()
    for prefix, gate in GATE_PREFIXES.items():
        if blocked.startswith(prefix):
            return gate, "block"
    return f"other:{blocked_by[:50]}", "block"


def backfill(
    runs_db_path: Path,
    ledger_db_path: Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill decision_outcomes from runs DB data.

    Returns a summary dict with counts and any errors.
    """
    from .ledger_attribution import connect_attribution, write_outcomes

    runs_con = sqlite3.connect(
        f"file:{runs_db_path}?mode=ro", uri=True, timeout=10
    )
    runs_con.row_factory = sqlite3.Row

    where_parts = ["pr.run_type = 'live'", "pr.strategy = 'renquant-104'"]
    params: list[str] = []
    if start_date:
        where_parts.append("pr.run_date >= ?")
        params.append(start_date)
    if end_date:
        where_parts.append("pr.run_date <= ?")
        params.append(end_date)
    where_clause = " AND ".join(where_parts)

    runs = runs_con.execute(
        f"SELECT DISTINCT pr.run_id, pr.run_date "
        f"FROM pipeline_runs pr WHERE {where_clause} "
        f"ORDER BY pr.run_date",
        params,
    ).fetchall()

    fwd_returns: dict[tuple[str, str], dict] = {}
    for row in runs_con.execute(
        "SELECT as_of_date, ticker, fwd_5d, fwd_20d, fwd_60d, close_price "
        "FROM ticker_forward_returns"
    ):
        fwd_returns[(row[0], row[1])] = {
            "fwd_5d_ret": row[2],
            "fwd_20d_ret": row[3],
            "fwd_60d_ret": row[4],
            "entry_price": row[5],
        }

    outcomes: list[dict[str, Any]] = []
    skipped_no_fwd = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for run in runs:
        run_id = run[0]
        run_date = run[1]

        candidates = runs_con.execute(
            "SELECT ticker, role, selected, blocked_by, mu, sigma "
            "FROM candidate_scores WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        for c in candidates:
            ticker = c[0]
            selected = c[2]
            blocked_by = c[3]
            gate, verdict = _map_gate(blocked_by, selected)

            fwd_key = (run_date, ticker)
            fwd = fwd_returns.get(fwd_key)
            if fwd is None:
                skipped_no_fwd += 1
                continue

            outcomes.append({
                "as_of": run_date,
                "scope": "book",
                "ticker": ticker,
                "gate": gate,
                "verdict": verdict,
                "fwd_5d_ret": fwd["fwd_5d_ret"],
                "fwd_20d_ret": fwd["fwd_20d_ret"],
                "fwd_60d_ret": fwd["fwd_60d_ret"],
                "entry_price": fwd["entry_price"],
                "recorded_at": now_iso,
                "metadata": {
                    "source": "outcome_backfiller",
                    "run_id": run_id,
                    "blocked_by": blocked_by,
                },
            })

    runs_con.close()

    written = 0
    if not dry_run and outcomes:
        ledger_con = connect_attribution(ledger_db_path)
        written = write_outcomes(ledger_con, outcomes)
        ledger_con.close()

    return {
        "runs_scanned": len(runs),
        "outcomes_prepared": len(outcomes),
        "outcomes_written": written,
        "skipped_no_forward_returns": skipped_no_fwd,
        "dry_run": dry_run,
        "start_date": start_date,
        "end_date": end_date,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill decision_outcomes from candidate_scores + ticker_forward_returns"
    )
    parser.add_argument(
        "--runs-db", type=Path, default=DEFAULT_RUNS_DB,
        help="Path to runs.alpaca.db (read-only)",
    )
    parser.add_argument(
        "--ledger-db", type=Path, default=None,
        help="Path to decision_ledger.db (default: decision_ledger.DEFAULT_DB)",
    )
    parser.add_argument("--start-date", help="Filter runs from this date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Filter runs until this date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just report")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)

    if not args.runs_db.exists():
        print(f"ERROR: runs DB not found: {args.runs_db}", file=sys.stderr)
        return 1

    ledger_db = args.ledger_db
    if ledger_db is None:
        from .decision_ledger import DEFAULT_DB
        ledger_db = DEFAULT_DB

    result = backfill(
        args.runs_db, ledger_db,
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Runs scanned:        {result['runs_scanned']}")
        print(f"Outcomes prepared:    {result['outcomes_prepared']}")
        print(f"Outcomes written:     {result['outcomes_written']}")
        print(f"Skipped (no fwd ret): {result['skipped_no_forward_returns']}")
        if result["dry_run"]:
            print("(dry run — nothing written)")
    return 0
