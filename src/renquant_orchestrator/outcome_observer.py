"""S5 Path B: forward-outcome observer for the decision ledger.

Scheduled job that populates ``decision_outcomes`` from price data after
the longest forward-return horizon (60 trading days) has elapsed.

One row per ``(as_of, scope, ticker, gate)`` with all three horizons
(5d, 20d, 60d) populated atomically. Append-only via INSERT OR IGNORE —
re-running is idempotent.

The observer reads decisions from the ledger, resolves entry prices from
``candidate_scores``, and reads +5/+20/+60 forward returns from the
precomputed ``ticker_forward_returns`` derived table (NOT a first-hand
realized-close-price fetch — this is a useful substrate but inherits
whatever assumptions the process that populated ``ticker_forward_returns``
made; see ``_load_forward_prices`` for the exact query).

Usage (CLI):
    rq observe-outcomes --runs-db ~/renquant-data/runs.alpaca.db
    rq observe-outcomes --dry-run   # show what WOULD be written
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .ledger_attribution import connect_attribution, write_outcomes

log = logging.getLogger(__name__)

HORIZONS = (5, 20, 60)
MAX_HORIZON = max(HORIZONS)
CALENDAR_BUFFER = int(MAX_HORIZON * 1.6)


def _trading_days_after(
    as_of: str, n: int, calendar_fn: Any = None
) -> str | None:
    """Return the date n trading days after as_of, or None if unavailable."""
    if calendar_fn is not None:
        return calendar_fn(as_of, n)
    dt = datetime.date.fromisoformat(as_of)
    skipped = 0
    current = dt
    while skipped < n:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:
            skipped += 1
    return current.isoformat()


def pending_decisions(
    ledger_conn: sqlite3.Connection,
    *,
    max_as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Find ledger decisions that have no corresponding outcome row yet.

    Only returns decisions whose as_of is old enough that the 60d horizon
    has plausibly elapsed (as_of + ~90 calendar days ≤ today).
    """
    if max_as_of is None:
        cutoff = datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER)
        max_as_of = cutoff.isoformat()

    sql = """
    SELECT DISTINCT l.as_of, l.scope, l.gate,
           l.verdict, l.reason, l.inputs_json
    FROM decision_ledger l
    LEFT JOIN decision_outcomes o
      ON l.as_of = o.as_of AND l.scope = o.scope AND l.gate = o.gate
    WHERE o.as_of IS NULL
      AND l.as_of <= ?
    ORDER BY l.as_of, l.scope, l.gate
    """
    ledger_conn.row_factory = sqlite3.Row
    rows = ledger_conn.execute(sql, (max_as_of,)).fetchall()
    return [dict(r) for r in rows]


def _load_entry_prices(
    runs_conn: sqlite3.Connection,
    decisions: list[dict[str, Any]],
) -> dict[tuple[str, str], float]:
    """Load entry prices from candidate_scores for each (as_of, ticker).

    Uses the scored close price from the pipeline run on the decision date.
    """
    if not decisions:
        return {}

    dates = sorted({d["as_of"] for d in decisions})
    tickers = sorted({d["scope"] for d in decisions if d["scope"] != "book"})

    if not tickers:
        return {}

    placeholders_d = ",".join("?" for _ in dates)
    placeholders_t = ",".join("?" for _ in tickers)

    sql = f"""
    SELECT DISTINCT run_date, ticker, close_price
    FROM candidate_scores
    WHERE run_date IN ({placeholders_d})
      AND ticker IN ({placeholders_t})
      AND close_price IS NOT NULL
    """
    try:
        rows = runs_conn.execute(sql, dates + tickers).fetchall()
    except sqlite3.OperationalError:
        log.warning("candidate_scores table not found or missing columns")
        return {}

    return {(r[0], r[1]): float(r[2]) for r in rows}


def _load_forward_prices(
    runs_conn: sqlite3.Connection,
    decisions: list[dict[str, Any]],
    calendar_fn: Any = None,
) -> dict[tuple[str, str, int], float]:
    """Read precomputed +5/+20/+60 forward returns for each (as_of, ticker).

    Returns {(as_of, ticker, horizon): fwd_return}. This reads the
    precomputed ``ticker_forward_returns`` derived table keyed by
    (run_date=as_of, ticker) — it is NOT a first-hand fetch of realized
    close prices at ``target_date``. ``target_date`` is computed only as an
    availability guard (skip a horizon the calendar function can't resolve
    at all); it is never used to filter the query itself, since
    ``ticker_forward_returns`` already stores the forward return under the
    originating ``as_of``, not under the target date. Do not present this
    as an authoritative realized-price path without also fixing this to
    genuinely resolve/query by target_date against a raw price table.
    """
    if not decisions:
        return {}

    result: dict[tuple[str, str, int], float] = {}
    dates = sorted({d["as_of"] for d in decisions})
    tickers = sorted({d["scope"] for d in decisions if d["scope"] != "book"})

    if not tickers:
        return result

    try:
        for as_of in dates:
            for horizon in HORIZONS:
                target_date = _trading_days_after(as_of, horizon, calendar_fn)
                if target_date is None:
                    continue

                placeholders_t = ",".join("?" for _ in tickers)
                sql = f"""
                SELECT ticker, fwd_{horizon}d_ret
                FROM ticker_forward_returns
                WHERE run_date = ? AND ticker IN ({placeholders_t})
                  AND fwd_{horizon}d_ret IS NOT NULL
                """
                try:
                    rows = runs_conn.execute(sql, [as_of] + tickers).fetchall()
                    for r in rows:
                        result[(as_of, r[0], horizon)] = float(r[1])
                except sqlite3.OperationalError:
                    pass
    except Exception:
        log.warning("failed to load forward prices", exc_info=True)

    return result


def observe_outcomes(
    ledger_conn: sqlite3.Connection,
    runs_conn: sqlite3.Connection,
    *,
    calendar_fn: Any = None,
    dry_run: bool = False,
    max_as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Main entry: find pending decisions, resolve prices, write outcomes.

    Returns the list of outcome dicts that were (or would be) written.
    """
    decisions = pending_decisions(ledger_conn, max_as_of=max_as_of)
    if not decisions:
        log.info("no pending decisions found")
        return []

    log.info("found %d pending decision-gate rows", len(decisions))

    entry_prices = _load_entry_prices(runs_conn, decisions)
    fwd_data = _load_forward_prices(runs_conn, decisions, calendar_fn)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    outcomes: list[dict[str, Any]] = []

    for d in decisions:
        as_of = d["as_of"]
        scope = d["scope"]
        gate = d["gate"]
        verdict = d["verdict"]
        ticker = scope if scope != "book" else ""

        entry_price = entry_prices.get((as_of, ticker))

        fwd_5d = fwd_data.get((as_of, ticker, 5))
        fwd_20d = fwd_data.get((as_of, ticker, 20))
        fwd_60d = fwd_data.get((as_of, ticker, 60))

        # Atomic write contract (module docstring, S5 spec #339): a
        # decision_outcomes row is written ONLY once ALL THREE horizons are
        # available. write_outcomes() is INSERT OR IGNORE on a fixed
        # (as_of, scope, ticker, gate) primary key with no update path, and
        # pending_decisions() treats "row exists" as "done" — a partial
        # write here would permanently suppress backfill of the still-
        # missing horizons (Codex #351 round 1).
        if fwd_5d is None or fwd_20d is None or fwd_60d is None:
            continue

        exit_5d = entry_price * (1 + fwd_5d) if entry_price and fwd_5d is not None else None
        exit_20d = entry_price * (1 + fwd_20d) if entry_price and fwd_20d is not None else None
        exit_60d = entry_price * (1 + fwd_60d) if entry_price and fwd_60d is not None else None

        outcomes.append({
            "as_of": as_of,
            "scope": scope,
            "ticker": ticker,
            "gate": gate,
            "verdict": verdict,
            "fwd_5d_ret": fwd_5d,
            "fwd_20d_ret": fwd_20d,
            "fwd_60d_ret": fwd_60d,
            "entry_price": entry_price,
            "exit_price_5d": exit_5d,
            "exit_price_20d": exit_20d,
            "exit_price_60d": exit_60d,
            "recorded_at": now,
            "metadata": {"source": "outcome_observer", "version": "1"},
        })

    if outcomes and not dry_run:
        written = write_outcomes(ledger_conn, outcomes)
        log.info("wrote %d outcome rows (%d skipped as duplicates)",
                 written, len(outcomes) - written)
    elif dry_run:
        log.info("dry run: would write %d outcome rows", len(outcomes))

    return outcomes


def main(argv: list[str] | None = None) -> None:
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--ledger-db",
        help="path to decision_ledger.db (default: ~/renquant-data/decision_ledger.db)",
    )
    ap.add_argument(
        "--runs-db",
        help="path to runs.alpaca.db for entry prices and forward returns",
    )
    ap.add_argument(
        "--max-as-of",
        help="only process decisions on or before this date (YYYY-MM-DD)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="show what would be written without writing",
    )
    args = ap.parse_args(argv)

    ledger_conn = connect_attribution(args.ledger_db)
    if args.runs_db:
        runs_conn = sqlite3.connect(args.runs_db, timeout=10)
    else:
        db_path = Path.home() / "renquant-data" / "runs.alpaca.db"
        if not db_path.exists():
            print(f"runs DB not found at {db_path}", file=sys.stderr)
            print("use --runs-db to specify", file=sys.stderr)
            sys.exit(1)
        runs_conn = sqlite3.connect(str(db_path), timeout=10)

    try:
        outcomes = observe_outcomes(
            ledger_conn, runs_conn,
            dry_run=args.dry_run,
            max_as_of=args.max_as_of,
        )
        if not outcomes:
            print("no outcomes to record", file=sys.stderr)
        else:
            action = "would write" if args.dry_run else "wrote"
            print(f"{action} {len(outcomes)} outcome rows", file=sys.stderr)
    finally:
        runs_conn.close()
        ledger_conn.close()
