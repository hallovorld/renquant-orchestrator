#!/usr/bin/env python3
"""Check score_db health: warn on stale/empty files, verify actual DB has data.

The live pipeline writes score_distribution rows to data/runs.<broker>.db
(via persistence.ensure_schema + RecordScoreDistributionTask). A legacy
score_db.sqlite3 file may exist as an empty placeholder in
backtesting/renquant_104/ — it is NOT the actual score store.

This script:
  1. Warns if score_db.sqlite3 exists and is empty (misleading artifact).
  2. Verifies data/runs.<broker>.db has score_distribution rows.
  3. Reports the latest date and row count, plus percentile-table coverage
     and the last 10 scored dates.

Exit 0 = healthy, exit 1 = problems found.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from renquant_orchestrator.runtime_paths import default_data_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=None,
        help="operator data/state root (default: runtime_paths.default_data_root(), "
        "honoring RENQUANT_DATA_ROOT)",
    )
    parser.add_argument("--broker", default="alpaca")
    args = parser.parse_args(argv)

    repo = args.repo_dir if args.repo_dir is not None else default_data_root()
    problems = 0

    # 1. Check for misleading empty score_db.sqlite3
    stale = repo / "backtesting" / "renquant_104" / "score_db.sqlite3"
    if stale.exists() and stale.stat().st_size == 0:
        print(
            f"WARN: {stale} is a 0-byte empty file. "
            f"Score data is actually in data/runs.{args.broker}.db. "
            f"This file can be safely deleted.",
        )
        problems += 1

    # 2. Check actual runs DB
    runs_db = repo / "data" / f"runs.{args.broker}.db"
    if not runs_db.exists():
        print(f"ERROR: {runs_db} does not exist — no score persistence.")
        return 1

    db = sqlite3.connect(str(runs_db))

    # Check score_distribution table exists
    tables = {
        t[0]
        for t in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "score_distribution" not in tables:
        print(f"ERROR: {runs_db} has no score_distribution table.")
        return 1

    total = db.execute("SELECT COUNT(*) FROM score_distribution").fetchone()[0]
    if total == 0:
        print(f"ERROR: score_distribution has 0 rows in {runs_db}.")
        return 1

    latest = db.execute(
        "SELECT date, COUNT(*) FROM score_distribution "
        "GROUP BY date ORDER BY date DESC LIMIT 1"
    ).fetchone()
    print(f"OK: score_distribution has {total} total rows, "
          f"latest date={latest[0]} ({latest[1]} tickers).")

    # 3. Check percentiles table
    if "score_percentiles_daily" in tables:
        pct_cnt = db.execute(
            "SELECT COUNT(*) FROM score_percentiles_daily"
        ).fetchone()[0]
        print(f"OK: score_percentiles_daily has {pct_cnt} rows.")
    else:
        print("WARN: score_percentiles_daily table missing.")
        problems += 1

    # 4. Date coverage: any gaps in last 10 trading days?
    dates = db.execute(
        "SELECT DISTINCT date FROM score_distribution "
        "ORDER BY date DESC LIMIT 10"
    ).fetchall()
    print(f"Last 10 scored dates: {[d[0] for d in dates]}")

    db.close()
    return 1 if problems > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
