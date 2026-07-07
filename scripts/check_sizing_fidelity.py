#!/usr/bin/env python3
"""Sizing-fidelity diagnostic: measure whole-share quantization error.

Reads runs.alpaca.db to quantify:
  1. size_insufficient_cash blocks (names dropped to 0 shares by int truncation)
  2. Cash-drag root-cause breakdown (which gates block the most candidates)
  3. Estimated notional lost to whole-share rounding on filled trades

This is the Phase 1 (S-FRAC) baseline measurement tool. After fractional
shares activate, the size_insufficient_cash count should drop to 0 and the
notional error should shrink to < 1% (the S-FRAC v2 acceptance criterion).

Exit 0 = report only, exit 1 = problems found.
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
        help="data root (default: runtime_paths.default_data_root())",
    )
    parser.add_argument("--broker", default="alpaca")
    parser.add_argument("--days", type=int, default=30, help="lookback window")
    args = parser.parse_args(argv)

    repo = args.repo_dir if args.repo_dir is not None else default_data_root()
    runs_db = repo / "data" / f"runs.{args.broker}.db"
    if not runs_db.exists():
        print(f"ERROR: {runs_db} does not exist")
        return 1

    db = sqlite3.connect(str(runs_db))
    problems = 0

    # 1. size_insufficient_cash blocks
    size_blocks = db.execute(
        """
        SELECT date, ticker, kelly_target_pct, mu
        FROM ticker_daily_state
        WHERE blocked_by = 'size_insufficient_cash'
          AND date >= date('now', ?)
        ORDER BY date DESC
        """,
        (f"-{args.days} days",),
    ).fetchall()

    if size_blocks:
        problems += 1
        print(f"SIZING FIDELITY: {len(size_blocks)} size_insufficient_cash "
              f"blocks in last {args.days} days")
        tickers = {}
        for date, ticker, kelly, mu in size_blocks:
            tickers.setdefault(ticker, []).append(date)
        for ticker, dates in sorted(tickers.items(), key=lambda x: -len(x[1])):
            print(f"  {ticker:6s}: {len(dates)} blocks "
                  f"(latest {dates[0]})")
    else:
        print(f"OK: 0 size_insufficient_cash blocks in last {args.days} days")

    # 2. Cash-drag root-cause breakdown
    blocked_reasons = db.execute(
        """
        SELECT
            CASE
                WHEN blocked_by LIKE 'size_insufficient%' THEN 'size_insufficient'
                WHEN blocked_by LIKE 'veto:%' THEN 'veto_weak_buys'
                WHEN blocked_by LIKE 'regime_admission%' THEN 'regime_admission'
                WHEN blocked_by LIKE 'kelly_zero%' THEN 'kelly_zero'
                WHEN blocked_by LIKE 'conviction%' THEN 'conviction_floor'
                WHEN blocked_by LIKE 'correlation%' THEN 'correlation_cap'
                WHEN blocked_by LIKE 'defensive%' THEN 'defensive_non_bear'
                WHEN blocked_by = 'tier' THEN 'tier_filter'
                ELSE blocked_by
            END as reason_group,
            COUNT(*) as cnt
        FROM candidate_scores
        WHERE blocked_by IS NOT NULL AND blocked_by != ''
          AND run_id IN (
              SELECT run_id FROM pipeline_runs
              WHERE run_date >= date('now', ?)
          )
        GROUP BY reason_group
        ORDER BY cnt DESC
        """,
        (f"-{args.days} days",),
    ).fetchall()

    if blocked_reasons:
        total = sum(cnt for _, cnt in blocked_reasons)
        print(f"\nCANDIDATE BLOCK BREAKDOWN (last {args.days} days, "
              f"{total} total blocks):")
        for reason, cnt in blocked_reasons:
            pct = cnt / total * 100 if total > 0 else 0
            print(f"  {reason:30s}: {cnt:5d} ({pct:5.1f}%)")

    # 3. Recent cash % from portfolio_daily_metrics
    cash_rows = db.execute(
        """
        SELECT run_date, cash / portfolio_value as cash_pct
        FROM pipeline_runs
        WHERE run_date >= date('now', ?)
          AND portfolio_value > 0
        ORDER BY run_date DESC
        LIMIT 10
        """,
        (f"-{args.days} days",),
    ).fetchall()

    if cash_rows:
        avg_cash = sum(r[1] for r in cash_rows if r[1] is not None) / max(
            1, sum(1 for r in cash_rows if r[1] is not None)
        )
        latest = cash_rows[0]
        print(f"\nCASH DRAG: latest={latest[1]:.1%} ({latest[0]}), "
              f"avg={avg_cash:.1%} over {len(cash_rows)} sessions")
        if avg_cash > 0.50:
            problems += 1
            print("  WARN: avg cash > 50% — significant cash drag")

    # 4. Fractional readiness summary
    print(f"\nFRACTIONAL READINESS:")
    print(f"  size_insufficient blocks: {len(size_blocks)} "
          f"({'BLOCKING' if size_blocks else 'CLEAR'})")
    print(f"  Affected tickers: "
          f"{', '.join(sorted(set(t for _, t, _, _ in size_blocks))) or 'none'}")

    db.close()
    return 1 if problems > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
