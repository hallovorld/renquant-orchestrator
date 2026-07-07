#!/usr/bin/env python3
"""Sizing-fidelity diagnostic: measure whole-share quantization error.

Reads runs.alpaca.db, restricted to CANONICAL daily runs (one genuine
completed run per run_date, deduped via ``tc_measurement._canonical_daily_runs``
— the same selection discipline this repo already uses for TC measurement),
to quantify:

  1. size_insufficient_cash blocks (the explicit block label; a LOWER BOUND
     on quantization loss, not the full picture — see #2).
  2. Whole-share quantization loss: for every candidate that SURVIVED TO
     THE SIZING STAGE (``kelly_target_pct > 0``, and ``blocked_by`` is
     either absent or classifies as ``sizing_failed``/``selected_submitted``
     under ``tc_measurement._classify_reason`` — i.e. NOT rejected earlier
     at admission/correlation/tier), compare the model's intended weight
     against the actual executed weight (0.0 if no trade was placed). Any
     gap is downstream of admission, which is exactly where whole-share
     rounding happens. This catches quantization loss regardless of which
     (if any) sizing-stage blocked_by label got attached — the gap the
     label-count metric alone is blind to.

     Two design notes from investigating the real DB directly (not assumed):
     (a) ``selected=1`` was considered as the survival criterion but
     rejected — it is essentially unpopulated on live runs after
     2026-05-22 (a pipeline change stopped setting it), so it cannot
     support this comparison on current data. ``kelly_target_pct``-based
     admission classification, reusing the SAME taxonomy
     ``tc_measurement.py`` already established, is what remains reliable.
     (b) ``qp_target_w`` was also considered and rejected: on live runs it
     and any historical ``selected=1`` rows essentially never co-occur (0
     of ~232k selected=1 rows in the live DB have qp_target_w populated —
     a disjoint code path), so it cannot support this comparison either.
  3. Cash-drag root-cause breakdown (which gates block the most candidates),
     restricted to the same canonical run set as #2.
  4. Recent cash-drag percentage from pipeline_runs.

This is the Phase 1 (S-FRAC) baseline measurement tool. After fractional
shares activate, the size_insufficient_cash count should drop to 0 and the
quantization-loss metric should shrink to < 1% (the S-FRAC v2 acceptance
criterion).

Exit 0 = report only, exit 1 = problems found.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from renquant_orchestrator.runtime_paths import default_data_root
from renquant_orchestrator.tc_measurement import (
    _canonical_daily_runs,
    _PRE_SELECTION_BLOCKERS,
    _SIZING_FAILURES,
    _SELECTED_SUBMITTED,
)

MIN_FULL_RUN_CANDIDATES = 80

# A candidate "survived to the sizing stage" if it was never rejected at
# admission (correlation/tier/sector/wash-sale/candidate_not_selected) —
# i.e. blocked_by is absent, or falls in tc_measurement's own
# sizing-stage/submitted categories. Anything in _PRE_SELECTION_BLOCKERS,
# or an unclassified reason (e.g. a QP-admission-stage rejection not yet
# in this taxonomy), is excluded: those are admission losses, not sizing
# quantization losses.
_SIZING_STAGE_REASONS = _SIZING_FAILURES | _SELECTED_SUBMITTED


def _canonical_run_ids(db: sqlite3.Connection, days: int) -> list[str]:
    """Canonical (one-per-date, genuinely-completed) run_ids in the window."""
    canonical = _canonical_daily_runs(db)
    if not canonical:
        return []
    cutoff = db.execute(
        "SELECT date('now', ?)", (f"-{days} days",)
    ).fetchone()[0]
    return [r["run_id"] for r in canonical if r["run_date"] >= cutoff]


def _survived_to_sizing(blocked_by: str | None) -> bool:
    if not blocked_by:
        return True
    if blocked_by in _PRE_SELECTION_BLOCKERS:
        return False
    return blocked_by in _SIZING_STAGE_REASONS


def _quantization_loss(db: sqlite3.Connection, run_ids: list[str]) -> dict:
    """Gap between the model's intended weight and the actually-executed
    weight, for every candidate that survived to the sizing stage —
    regardless of which (if any) sizing-stage blocked_by label got attached.

    Uses ``kelly_target_pct`` as the intended weight and reuses
    ``tc_measurement``'s own admission taxonomy to define "survived to
    sizing," rather than the ``selected`` column or ``qp_target_w`` — see
    the module docstring for why both of those were investigated and
    rejected against the real DB.
    """
    if not run_ids:
        return {"n_selected": 0, "n_gapped": 0, "total_gap_pct": 0.0, "rows": []}

    placeholders = ",".join("?" * len(run_ids))
    candidates = db.execute(
        f"""
        SELECT run_id, ticker, kelly_target_pct, blocked_by
        FROM candidate_scores
        WHERE run_id IN ({placeholders})
          AND kelly_target_pct IS NOT NULL
          AND kelly_target_pct > 0
        """,
        run_ids,
    ).fetchall()
    survived = [c for c in candidates if _survived_to_sizing(c[3])]

    trades = db.execute(
        f"""
        SELECT run_id, ticker, target_pct
        FROM trades
        WHERE run_id IN ({placeholders}) AND action LIKE 'buy%'
        """,
        run_ids,
    ).fetchall()
    actual_by_key = {(r, t): pct for r, t, pct in trades}

    rows = []
    total_gap = 0.0
    n_gapped = 0
    for run_id, ticker, kelly_w, blocked_by in survived:
        actual = actual_by_key.get((run_id, ticker), 0.0)
        gap = kelly_w - actual
        if gap > 1e-9:
            n_gapped += 1
            total_gap += gap
            rows.append({
                "run_id": run_id,
                "ticker": ticker,
                "kelly_target_pct": kelly_w,
                "actual_pct": actual,
                "gap_pct": round(gap, 6),
                "blocked_by": blocked_by,
            })

    return {
        "n_selected": len(survived),
        "n_gapped": n_gapped,
        "total_gap_pct": round(total_gap, 6),
        "mean_gap_pct_per_selected": (
            round(total_gap / len(survived), 6) if survived else 0.0
        ),
        "rows": sorted(rows, key=lambda r: -r["gap_pct"])[:20],
    }


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
    parser.add_argument(
        "--evidence-out", type=Path, default=None,
        help="write a JSON evidence artifact to this path",
    )
    args = parser.parse_args(argv)

    repo = args.repo_dir if args.repo_dir is not None else default_data_root()
    runs_db = repo / "data" / f"runs.{args.broker}.db"
    if not runs_db.exists():
        print(f"ERROR: {runs_db} does not exist")
        return 1

    db = sqlite3.connect(str(runs_db))
    problems = 0

    canonical_ids = _canonical_run_ids(db, args.days)
    print(f"CANONICAL RUNS: {len(canonical_ids)} in last {args.days} days "
          f"(deduped one-per-date via tc_measurement._canonical_daily_runs, "
          f"requiring >={MIN_FULL_RUN_CANDIDATES} candidate_scores rows)")

    # 1. size_insufficient_cash blocks — an explicit-label LOWER BOUND, not
    #    the full quantization-loss picture (see #2 below).
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
        print(f"\nLABELED size_insufficient_cash BLOCKS (lower bound only): "
              f"{len(size_blocks)} in last {args.days} days")
        tickers: dict[str, list[str]] = {}
        for date, ticker, kelly, mu in size_blocks:
            tickers.setdefault(ticker, []).append(date)
        for ticker, dates in sorted(tickers.items(), key=lambda x: -len(x[1])):
            print(f"  {ticker:6s}: {len(dates)} blocks (latest {dates[0]})")
    else:
        print(f"\nOK: 0 labeled size_insufficient_cash blocks in last "
              f"{args.days} days")

    # 2. Whole-share quantization loss — the real metric: gap between
    #    QP-intended weight and actually-executed weight, regardless of
    #    blocked_by label.
    quant = _quantization_loss(db, canonical_ids)
    print(f"\nWHOLE-SHARE QUANTIZATION LOSS (canonical runs, sizing-stage "
          f"candidates only):")
    print(f"  candidates surviving to sizing: {quant['n_selected']}")
    print(f"  Candidates with executed < intended: {quant['n_gapped']}")
    if quant["n_selected"] > 0:
        gap_rate = quant["n_gapped"] / quant["n_selected"] * 100
        print(f"  Gap rate: {gap_rate:.1f}% of candidates surviving to sizing")
        per_run_mean = quant["total_gap_pct"] / len(canonical_ids) if canonical_ids else 0.0
        print(f"  Total gap (sum across all {len(canonical_ids)} canonical "
              f"runs, each run's own portfolio as the 100% baseline — NOT a "
              f"single-day percentage): {quant['total_gap_pct']:.4f}")
        print(f"  Mean gap per canonical run: {per_run_mean:.4f} "
              f"({per_run_mean:.1%} of one day's portfolio, averaged)")
        print(f"  Mean gap per candidate surviving to sizing: "
              f"{quant['mean_gap_pct_per_selected']:.4f}")
        if quant["n_gapped"] > 0:
            problems += 1
            no_label = sum(1 for r in quant["rows"] if not r["blocked_by"])
            other_label = sum(
                1 for r in quant["rows"]
                if r["blocked_by"] and r["blocked_by"] != "size_insufficient_cash"
            )
            print(f"  Of top {len(quant['rows'])} gaps: {no_label} have NO "
                  f"blocked_by label, {other_label} have a DIFFERENT label "
                  f"than size_insufficient_cash — this is the loss the "
                  f"label-count metric alone would miss.")
    else:
        print("  No candidates surviving to sizing found in canonical runs — cannot "
              "compute quantization loss for this window.")

    # 3. Cash-drag root-cause breakdown, restricted to canonical runs.
    blocked_reasons: list[tuple[str, int]] = []
    if canonical_ids:
        placeholders = ",".join("?" * len(canonical_ids))
        blocked_reasons = db.execute(
            f"""
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
              AND run_id IN ({placeholders})
            GROUP BY reason_group
            ORDER BY cnt DESC
            """,
            canonical_ids,
        ).fetchall()

    if blocked_reasons:
        total = sum(cnt for _, cnt in blocked_reasons)
        print(f"\nCANDIDATE BLOCK BREAKDOWN (canonical runs only, "
              f"{total} total blocks):")
        for reason, cnt in blocked_reasons:
            pct = cnt / total * 100 if total > 0 else 0
            print(f"  {reason:30s}: {cnt:5d} ({pct:5.1f}%)")
    elif canonical_ids:
        print("\nCANDIDATE BLOCK BREAKDOWN: no blocked candidates in "
              "canonical runs.")

    # 4. Recent cash % from pipeline_runs.
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

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "days": args.days,
            "canonical_run_ids": canonical_ids,
            "labeled_size_insufficient_cash_blocks": len(size_blocks),
            "quantization_loss": quant,
            "block_breakdown": [
                {"reason": r, "count": c} for r, c in blocked_reasons
            ],
        }, indent=2))
        print(f"\nEvidence artifact written: {args.evidence_out}")

    db.close()
    return 1 if problems > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
