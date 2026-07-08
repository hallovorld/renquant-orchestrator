"""renquant105 observe-only cash-drag scorecard from shadow decision logs.

Reads the existing Stage-1 ``intraday_decisions_shadow.jsonl`` corpus and
produces a per-session summary of the cash-drag signals that the CURRENT
orchestrator/pipeline contract can measure honestly:

- close idle-cash fraction (cash / equity on the last tick),
- final envelope counters (entries/deployed/turnover),
- counts of whole-share-floor and insufficient-cash skips recorded by the
  tick runner.

This module is deliberately read-only and deliberately narrow. It does NOT
infer any pre-quantization sizing target for 105, because the current
intraday contract does not expose that field. The scorecard therefore reports
the missing contract explicitly instead of fabricating a stronger claim.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .intraday_session_scheduler import (
    RECORD_KIND_TICK,
    SCHEDULER_SCHEMA_VERSION,
    default_shadow_log_path,
)
from .runtime_paths import default_data_root

SKIP_REASON_WHOLE_SHARE_FLOOR = "zero_quantity_after_whole_share_floor"
SKIP_REASON_INSUFFICIENT_CASH = "insufficient_available_cash"
_MEASURED_SKIP_REASONS = (
    SKIP_REASON_WHOLE_SHARE_FLOOR,
    SKIP_REASON_INSUFFICIENT_CASH,
)
_PENDING_FIELDS = {
    "target_notional": (
        "current 105 intraday contract exposes realized entry intents and "
        "skip reasons, but not the pre-quantization sizing target"
    ),
    "true_zero_drop_pre_quantization": (
        "without target_notional we can count realized whole-share-floor skips, "
        "not every pre-quantization zero-drop candidate"
    ),
}


def _iter_tick_records(path: str | Path) -> Iterable[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"shadow log not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{p}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(f"{p}:{line_no}: record must be a JSON object")
            if rec.get("kind") != RECORD_KIND_TICK:
                continue
            if rec.get("schema_version") != SCHEDULER_SCHEMA_VERSION:
                raise ValueError(
                    f"{p}:{line_no}: unsupported schema_version "
                    f"{rec.get('schema_version')!r}"
                )
            yield rec


def _session_date_filter(rec: Mapping[str, Any], session_dates: set[str] | None) -> bool:
    if session_dates is None:
        return True
    return str(rec.get("session_date") or "") in session_dates


def _reason_counts(skipped_rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in skipped_rows:
        for reason in row.get("reasons") or ():
            counts[str(reason)] += 1
    return counts


def _summarize_session(session_date: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = max(rows, key=lambda r: int(r.get("tick_index", -1)))
    inputs = dict(latest.get("inputs") or {})
    live_state = dict(inputs.get("live_state") or {})
    decisions = dict(latest.get("decisions") or {})
    counters = dict(decisions.get("counters") or {})

    cash = live_state.get("cash")
    equity = live_state.get("equity")
    idle_cash_frac = None
    if isinstance(cash, (int, float)) and isinstance(equity, (int, float)) and equity > 0:
        idle_cash_frac = float(cash) / float(equity)

    skip_counts = Counter()
    for row in rows:
        row_decisions = dict(row.get("decisions") or {})
        skip_counts.update(_reason_counts(row_decisions.get("skipped") or ()))

    return {
        "session_date": session_date,
        "tick_count": len(rows),
        "last_tick_at": latest.get("tick_at"),
        "close_cash": float(cash) if isinstance(cash, (int, float)) else None,
        "close_equity": float(equity) if isinstance(equity, (int, float)) else None,
        "close_idle_cash_fraction": idle_cash_frac,
        "entries_count": int(counters.get("entries_count", 0) or 0),
        "deployed_notional": float(counters.get("deployed_notional", 0.0) or 0.0),
        "turnover_notional": float(counters.get("turnover_notional", 0.0) or 0.0),
        "whole_share_floor_skip_count": int(
            skip_counts.get(SKIP_REASON_WHOLE_SHARE_FLOOR, 0)
        ),
        "insufficient_available_cash_skip_count": int(
            skip_counts.get(SKIP_REASON_INSUFFICIENT_CASH, 0)
        ),
        "skip_reason_counts": dict(sorted(skip_counts.items())),
    }


def build_scorecard(
    path: str | Path,
    *,
    session_dates: Sequence[str] | None = None,
) -> dict[str, Any]:
    wanted = set(session_dates) if session_dates else None
    by_session: dict[str, list[dict[str, Any]]] = {}
    for rec in _iter_tick_records(path):
        if not _session_date_filter(rec, wanted):
            continue
        session_date = str(rec.get("session_date") or "")
        if not session_date:
            raise ValueError("tick record missing session_date")
        by_session.setdefault(session_date, []).append(rec)

    sessions = [
        _summarize_session(session_date, rows)
        for session_date, rows in sorted(by_session.items())
    ]
    idle_fracs = [
        float(s["close_idle_cash_fraction"])
        for s in sessions
        if s["close_idle_cash_fraction"] is not None
    ]
    whole_share_skips = [int(s["whole_share_floor_skip_count"]) for s in sessions]
    insufficient_cash_skips = [
        int(s["insufficient_available_cash_skip_count"]) for s in sessions
    ]

    return {
        "schema_version": "rq105-cash-drag-scorecard-v1",
        "source": str(Path(path)),
        "n_sessions": len(sessions),
        "sessions": sessions,
        "summary": {
            "median_close_idle_cash_fraction": median(idle_fracs) if idle_fracs else None,
            "median_whole_share_floor_skip_count": (
                median(whole_share_skips) if whole_share_skips else None
            ),
            "median_insufficient_available_cash_skip_count": (
                median(insufficient_cash_skips) if insufficient_cash_skips else None
            ),
            "total_whole_share_floor_skip_count": sum(whole_share_skips),
            "total_insufficient_available_cash_skip_count": sum(insufficient_cash_skips),
        },
        "pending_contract_fields_unavailable": dict(_PENDING_FIELDS),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-cash-drag-scorecard",
        description=(
            "Read the renquant105 shadow decision log and summarize the "
            "cash-drag signals the current contract exposes."
        ),
    )
    parser.add_argument(
        "--shadow-log",
        default=str(default_shadow_log_path(default_data_root())),
        help="scheduler intraday_decisions_shadow.jsonl (read-only)",
    )
    parser.add_argument(
        "--session-date",
        action="append",
        default=[],
        help="limit to one or more YYYY-MM-DD session dates",
    )
    args = parser.parse_args(argv)
    payload = build_scorecard(args.shadow_log, session_dates=args.session_date or None)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "SKIP_REASON_INSUFFICIENT_CASH",
    "SKIP_REASON_WHOLE_SHARE_FLOOR",
    "build_scorecard",
    "main",
]

