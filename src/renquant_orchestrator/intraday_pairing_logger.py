"""renquant105 Stage-1 OPERATIONS-ONLY paired execution-shortfall logging harness.

OBSERVE-ONLY / post-hoc data collector for the intraday-decisioning RFC
(``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`` §9,
converged r11/r12). For each daily-admitted name on a session it records a
**paired** implementation-shortfall (IS) row comparing:

  * (a) the ACTUAL next-day-open **batch** entry the 104 后 batch placed, and
  * (b) the HYPOTHETICAL **intraday** entry at the daily decision's intraday
    tick (nothing is placed intraday — the intraday arm is a counterfactual
    reference here),

both measured against a common **decision-time reference (arrival) mid** (§9.1).
The paired rows accumulate as JSONL so a future, SEPARATE experiment-prereg PR
(§9.4) can consume real pilot variance. This harness is the pairing structure and
the accumulation buffer — nothing more.

Stage-1 is operations-only. This module DELIBERATELY does **not**:

  * emit orders, place trades, promote, pin, or gate anything (OBSERVE-ONLY);
  * render any PASS/FAIL, non-inferiority verdict, or ±10-bps claim — those are
    explicitly deferred to the future separate prereg PR (design §9.4);
  * impute censored cells — a no-fill / no-intraday-tick pair is RECORDED by
    cause and left censored, never filled in (design §9.2d).

Design conventions (matching ``decision_pnl_attribution`` / ``decision_ledger``):
pure functions over plain data structures for the pairing logic (testable with
zero I/O), plus thin **read-only** loaders whose paths are parameterized so
nothing is hard-coded to the live umbrella tree and tests never touch live state.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .runtime_paths import default_data_root

# Schema version for the pilot JSONL rows — bump if the record shape changes so
# the future experiment (§9.4) can migrate cleanly.
SCHEMA_VERSION = "1"
STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "observe_only_paired_is"

# Read-only defaults. Every public function takes the path/connection explicitly;
# these are only the ad-hoc/CLI fallbacks. Inputs default to the umbrella tree
# (read-only). The pilot OUTPUT defaults under the operator data root (decoupled
# from the umbrella checkout, honoring RENQUANT_DATA_ROOT) — this collector never
# writes into the umbrella git tree by default.
DEFAULT_RUNS_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"
DEFAULT_TICK_SOURCE = Path.home() / "git/github/RenQuant/logs/renquant105_pilot/intraday_ticks.jsonl"


def default_pilot_path(data_root: Path | None = None) -> Path:
    """Default accumulating pilot-data file, under the operator data root."""
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "paired_is.jsonl"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PriceRef:
    """A price observation with its wall-clock reference (an entry or a fill)."""

    price: float
    time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"price": self.price, "time": self.time}


@dataclass(frozen=True)
class AdmittedName:
    """One daily-admitted candidate (the pre-treatment admit, §9.2). ``side`` is
    ``buy`` for a long entry (the default; shorts are rare per the mandate)."""

    date: str
    ticker: str
    side: str = "buy"
    signal_version: str | None = None  # frozen-signal id (§6 class A); run_id here


# ---------------------------------------------------------------------------
# Pure pairing logic (no I/O — fully testable)
# ---------------------------------------------------------------------------
def implementation_shortfall(
    entry_price: float | None,
    reference_mid: float | None,
    side: str,
) -> float | None:
    """Signed implementation shortfall of an entry vs the decision-time reference
    mid, in the instrument's price units (Perold arrival-price convention).

    For a **buy**, positive = entered ABOVE the reference (paid up / worse); for a
    **sell**, positive = entered BELOW the reference (worse). This is a raw signed
    deviation ONLY — it is not a verdict, a between-arm comparison, or a bps claim
    (all deferred, §9.4). Returns ``None`` when any input is missing (censored —
    recorded, never imputed, §9.2d); ``reference_mid`` is carried on the record so
    any downstream normalization (e.g. to bps) stays a choice of the future
    analysis, not something asserted here.
    """
    if entry_price is None or reference_mid is None:
        return None
    sign = 1.0 if side == "buy" else -1.0
    return sign * (float(entry_price) - float(reference_mid))


def build_paired_record(
    *,
    date: str,
    ticker: str,
    side: str = "buy",
    reference_mid: float | None,
    batch_entry_ref: PriceRef | None,
    intraday_entry_ref: PriceRef | None,
    signal_version: str | None = None,
    admitted: bool = True,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one PAIRED IS record for an admitted name.

    ``batch_entry_ref`` = the ACTUAL next-open batch fill (a real historical
    fill); ``intraday_entry_ref`` = the HYPOTHETICAL intraday entry at the
    decision tick (no order is placed intraday in Stage-1). ``reference_mid`` is
    the common decision-time arrival mid. Any missing input is recorded, never
    imputed, and named in ``censored_reason``.
    """
    is_batch = implementation_shortfall(
        batch_entry_ref.price if batch_entry_ref else None, reference_mid, side
    )
    is_intraday = implementation_shortfall(
        intraday_entry_ref.price if intraday_entry_ref else None, reference_mid, side
    )

    missing: list[str] = []
    if intraday_entry_ref is None:
        missing.append("no_intraday_tick")
    if batch_entry_ref is None:
        missing.append("no_batch_fill")
    # A reference decoupled from the tick could be missing on its own; only tag it
    # when the tick itself was present (otherwise no_intraday_tick already covers
    # the absent decision-time mid).
    if reference_mid is None and intraday_entry_ref is not None:
        missing.append("no_reference")

    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        # The intraday arm is a counterfactual reference; no real intraday order
        # exists in Stage-1 observe-only. The batch arm is a real historical fill.
        "intraday_entry_hypothetical": True,
        "date": date,
        "ticker": ticker,
        "side": side,
        "signal_version": signal_version,
        "reference_mid": reference_mid,
        "batch_entry_ref": batch_entry_ref.to_dict() if batch_entry_ref else None,
        "intraday_entry_ref": intraday_entry_ref.to_dict() if intraday_entry_ref else None,
        "implementation_shortfall_batch": is_batch,
        "implementation_shortfall_intraday": is_intraday,
        "admitted": bool(admitted),
        "filled": batch_entry_ref is not None,
        "censored_reason": "+".join(missing) if missing else None,
    }
    if extra:
        record["extra"] = dict(extra)
    return record


def pair_records(
    admitted: Iterable[AdmittedName],
    batch_fills: Mapping[tuple[str, str], PriceRef],
    intraday_ticks: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join admitted names to their batch fill and intraday tick, producing one
    paired record per admitted name (censored rows included — recorded, not
    dropped, §9.2d).

    ``batch_fills`` is keyed by ``(signal_version, ticker)`` when the admit
    carries a ``signal_version`` (the run_id that placed the order), else by
    ``(date, ticker)``. ``intraday_ticks`` is keyed by ``(date, ticker)`` and each
    value is ``{"mid": float, "entry_price": float?, "tick_time": str?}``; the
    tick's ``mid`` is the decision-time reference and ``entry_price`` (defaulting
    to ``mid``) is where the intraday path would have entered.
    """
    records: list[dict[str, Any]] = []
    for name in admitted:
        fill_key = (name.signal_version or name.date, name.ticker)
        batch_entry_ref = batch_fills.get(fill_key) or batch_fills.get(
            (name.date, name.ticker)
        )

        tick = intraday_ticks.get((name.date, name.ticker))
        if tick is not None:
            reference_mid = tick.get("mid")
            entry_price = tick.get("entry_price", reference_mid)
            intraday_entry_ref = (
                PriceRef(price=entry_price, time=tick.get("tick_time"))
                if entry_price is not None
                else None
            )
        else:
            reference_mid = None
            intraday_entry_ref = None

        records.append(
            build_paired_record(
                date=name.date,
                ticker=name.ticker,
                side=name.side,
                reference_mid=reference_mid,
                batch_entry_ref=batch_entry_ref,
                intraday_entry_ref=intraday_entry_ref,
                signal_version=name.signal_version,
            )
        )
    return records


def pair_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Idempotency key = the design pair key (signal_session, symbol,
    signal_version) (§9.2)."""
    return (
        str(record.get("date")),
        str(record.get("ticker")),
        str(record.get("signal_version") or ""),
    )


# ---------------------------------------------------------------------------
# Diagnostics summary (counts only — NO verdict, comparison, or bps claim)
# ---------------------------------------------------------------------------
def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Operational counts over the paired rows. Deliberately reports NO between-
    arm comparison, mean IS, non-inferiority verdict, or ±10-bps figure — Stage 1
    renders no execution-quality verdict (§9.3); those are deferred to §9.4."""
    censored: dict[str, int] = {}
    n_batch_fill = 0
    n_intraday_tick = 0
    n_complete = 0
    for r in records:
        reason = r.get("censored_reason")
        if reason:
            censored[reason] = censored.get(reason, 0) + 1
        else:
            n_complete += 1
        if r.get("batch_entry_ref") is not None:
            n_batch_fill += 1
        if r.get("intraday_entry_ref") is not None:
            n_intraday_tick += 1
    return {
        "n_admitted_pairs": len(records),
        "n_complete_pairs": n_complete,
        "n_censored_pairs": len(records) - n_complete,
        "n_with_batch_fill": n_batch_fill,
        "n_with_intraday_tick": n_intraday_tick,
        "censored_by_reason": censored,
    }


# ---------------------------------------------------------------------------
# JSONL accumulation (idempotent append)
# ---------------------------------------------------------------------------
def existing_pair_keys(path: str | Path) -> set[tuple[str, str, str]]:
    """Pair keys already present in the pilot file (empty if the file is absent).
    Malformed lines are skipped so a partially-written file never blocks append."""
    p = Path(path)
    if not p.exists():
        return set()
    keys: set[tuple[str, str, str]] = set()
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(pair_key(json.loads(line)))
            except (json.JSONDecodeError, AttributeError):
                continue
    return keys


def append_records(
    path: str | Path,
    records: Iterable[Mapping[str, Any]],
) -> int:
    """Append paired rows to the accumulating pilot JSONL, skipping any whose pair
    key is already present (idempotent — re-running a session is a no-op, never a
    duplicate). Creates parent dirs. Returns the number of NEW rows written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_pair_keys(p)
    written = 0
    with p.open("a", encoding="utf-8") as fh:
        for r in records:
            key = pair_key(r)
            if key in seen:
                continue
            fh.write(json.dumps(r, sort_keys=True) + "\n")
            seen.add(key)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Thin read-only loaders (parameterized paths — never hard-code live state)
# ---------------------------------------------------------------------------
def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a run DB **read-only** (``mode=ro`` URI) so this collector can never
    write to it. Defaults to :data:`DEFAULT_RUNS_DB`; pass an explicit path (or an
    in-memory DB) in tests."""
    if db_path is None:
        db_path = DEFAULT_RUNS_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def load_admitted(
    conn: sqlite3.Connection,
    date: str,
    *,
    run_type: str = "live",
) -> list[AdmittedName]:
    """Load the daily-admitted names (``candidate_scores.selected = 1``) for a
    session, joined to ``pipeline_runs`` on ``run_id`` to filter by ``run_date``
    and ``run_type``. ``signal_version`` carries the run_id (the frozen-signal id
    that placed the batch order)."""
    rows = conn.execute(
        """
        SELECT cs.run_id AS run_id, cs.ticker AS ticker
        FROM candidate_scores cs
        JOIN pipeline_runs pr ON pr.run_id = cs.run_id
        WHERE pr.run_date = ? AND pr.run_type = ? AND cs.selected = 1
        ORDER BY cs.run_id, cs.ticker
        """,
        (date, run_type),
    ).fetchall()
    return [
        AdmittedName(
            date=date,
            ticker=row["ticker"],
            side="buy",
            signal_version=row["run_id"],
        )
        for row in rows
    ]


def load_batch_fills(
    conn: sqlite3.Connection,
    admitted: Sequence[AdmittedName],
    *,
    buy_actions: Sequence[str] = ("buy",),
) -> dict[tuple[str, str], PriceRef]:
    """Load the ACTUAL next-open batch buy fills for the admitted names, joined by
    ``run_id`` (the batch run that admitted a name also placed its order), keyed by
    ``(signal_version, ticker)``. Robust to the presence/absence of a
    ``trade_date`` column (used only for the fill timestamp)."""
    run_ids = sorted({n.signal_version for n in admitted if n.signal_version})
    if not run_ids:
        return {}
    cols = _table_columns(conn, "trades")
    time_col = "trade_date" if "trade_date" in cols else None
    placeholders = ",".join("?" for _ in run_ids)
    action_ph = ",".join("?" for _ in buy_actions)
    select_time = f", {time_col} AS fill_time" if time_col else ""
    rows = conn.execute(
        f"""
        SELECT run_id, ticker, price{select_time}
        FROM trades
        WHERE run_id IN ({placeholders}) AND action IN ({action_ph})
        """,
        (*run_ids, *buy_actions),
    ).fetchall()
    fills: dict[tuple[str, str], PriceRef] = {}
    for row in rows:
        price = row["price"]
        if price is None:
            continue
        fill_time = row["fill_time"] if time_col else None
        fills[(row["run_id"], row["ticker"])] = PriceRef(
            price=float(price), time=fill_time
        )
    return fills


def load_intraday_ticks(
    path: str | Path,
    date: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Load the structured intraday decision-tick quote source (JSONL) for a
    session, keyed by ``(date, ticker)``.

    Each line is ``{"date", "ticker", "mid", "entry_price"?, "tick_time"?}``. This
    is the pluggable feed the future intraday full-decisioning loop emits; until
    that loop lands the source is typically absent, so every pair is censored
    ``no_intraday_tick`` — the correct, honest Stage-1 state (scaffold ready,
    waiting for the tick feed). A missing file yields an empty mapping."""
    p = Path(path)
    if not p.exists():
        return {}
    ticks: dict[tuple[str, str], dict[str, Any]] = {}
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") != date or "ticker" not in obj:
                continue
            ticks[(date, obj["ticker"])] = obj
    return ticks


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY; --dry-run / --json summary
# ---------------------------------------------------------------------------
def collect(
    *,
    date: str,
    runs_db: str | Path,
    tick_source: str | Path,
    run_type: str = "live",
) -> list[dict[str, Any]]:
    """Read-only end-to-end pairing for a session: load admitted + batch fills +
    intraday ticks and return the paired records. Places nothing, writes nothing."""
    conn = connect(runs_db)
    try:
        admitted = load_admitted(conn, date, run_type=run_type)
        batch_fills = load_batch_fills(conn, admitted)
    finally:
        conn.close()
    ticks = load_intraday_ticks(tick_source, date)
    return pair_records(admitted, batch_fills, ticks)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-pairing-logger",
        description=(
            "renquant105 Stage-1 OPERATIONS-ONLY paired intraday-vs-batch "
            "implementation-shortfall logger. OBSERVE-ONLY: collects pilot data; "
            "places no orders and renders no execution-quality verdict."
        ),
    )
    parser.add_argument("--date", required=True, help="session date YYYY-MM-DD")
    parser.add_argument(
        "--runs-db",
        default=str(DEFAULT_RUNS_DB),
        help="read-only run DB (candidate_scores + trades)",
    )
    parser.add_argument(
        "--tick-source",
        default=str(DEFAULT_TICK_SOURCE),
        help="structured intraday decision-tick quote JSONL (may be absent)",
    )
    parser.add_argument(
        "--out",
        default=str(default_pilot_path()),
        help="accumulating pilot JSONL (append, idempotent)",
    )
    parser.add_argument("--run-type", default="live")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute + summarize only; write nothing",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the summary as JSON"
    )
    args = parser.parse_args(argv)

    records = collect(
        date=args.date,
        runs_db=args.runs_db,
        tick_source=args.tick_source,
        run_type=args.run_type,
    )
    summary = summarize(records)
    written = 0
    if not args.dry_run:
        written = append_records(args.out, records)

    summary = {
        "date": args.date,
        "mode": "dry-run" if args.dry_run else "append",
        "out": None if args.dry_run else str(args.out),
        "rows_written": written,
        "observe_only": True,
        **summary,
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(f"[OBSERVE-ONLY] renquant105 Stage-1 paired IS logger — {args.date}")
        print(f"  mode                : {summary['mode']}")
        print(f"  admitted pairs      : {summary['n_admitted_pairs']}")
        print(f"  complete pairs      : {summary['n_complete_pairs']}")
        print(f"  censored pairs      : {summary['n_censored_pairs']}")
        print(f"  with batch fill     : {summary['n_with_batch_fill']}")
        print(f"  with intraday tick  : {summary['n_with_intraday_tick']}")
        if summary["censored_by_reason"]:
            print("  censored by reason  :")
            for reason, n in sorted(summary["censored_by_reason"].items()):
                print(f"      {reason}: {n}")
        if not args.dry_run:
            print(f"  rows written        : {written} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
