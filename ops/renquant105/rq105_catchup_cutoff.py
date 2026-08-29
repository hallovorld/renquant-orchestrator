#!/usr/bin/env python3
"""rq105_catchup_cutoff.py — the catch-up guard's session-calendar cutoff
(orch#1085 r2; codex on the first draft).

The first draft of ``rq105_catchup_guard.sh`` took a FIXED ``1300`` local
cutoff and a weekday number. NYSE early-close sessions (day after
Thanksgiving, Christmas Eve, ...) close at 13:00 ET = 10:00 PT, and weekday
market holidays have no session at all — so a boot between 10:00 and 13:00 PT
on an early-close day would have exported a "pre-session frozen" vector after
the session had ended, and a boot on Labor Day would have started the
scheduler for a session that does not exist.

This helper is the ONE calendar answer the guard consumes. For a local date
it prints the local ``HHMM`` of that date's ACTUAL session close (early-close
aware) and exits 0; for a non-session date (weekend / holiday) it prints the
reason and exits 1; for anything else (bad date, calendar backend missing,
import failure, a close that does not fall on the requested local date) it
prints the reason and exits 2. The guard treats every non-zero as "refuse
catch-up", never as "run" — fail closed.

The calendar is the SAME primitive the rest of rq105 uses —
``renquant_orchestrator.intraday_quote_logger.default_session_calendar``
(a re-export of ``renquant_common.market_calendar``, ``pandas_market_calendars``
NYSE), exactly what ``rq105_liveness_check._session_calendar`` and the session
scheduler's own gate resolve. There is deliberately NO ``sys.path`` bootstrap
and NO fallback here: the guard runs this script under the wrapper's own
``PYTHONPATH`` (``$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC``, the pinned
orchestrator checkout and the pin-verified renquant-common — orch#1016), so
the calendar the cutoff comes from is the calendar the job itself imports. If
that import fails, the job could not have run either; the guard refuses and
the 14:00 liveness check reports ``export_missing`` / ``scheduler_dark``.

"Local" is the process's local clock — the same clock the wrapper's
``$(date +%H%M)`` reads — so the printed cutoff and the guard's ``now`` are
comparable by construction (DST already resolved by the calendar's aware
datetimes).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

EXIT_SESSION = 0
EXIT_NON_SESSION = 1
EXIT_ERROR = 2


def local_close_hhmm(day: dt.date, calendar=None) -> str | None:
    """``HHMM`` of ``day``'s session close in the process-local timezone, or
    ``None`` when ``day`` is not a session. Raises on calendar failure and when
    the local close does not fall on ``day`` (a host clock the guard's ``now``
    could not be compared against)."""
    if calendar is None:
        from renquant_orchestrator.intraday_quote_logger import (  # noqa: PLC0415
            default_session_calendar,
        )

        calendar = default_session_calendar()
    bounds = calendar.session_bounds(day)
    if bounds is None:
        return None
    close_local = bounds.close.astimezone()  # process-local tz == `date +%H%M`
    if close_local.date() != day:
        raise RuntimeError(
            f"session close {bounds.close.isoformat()} falls on local date "
            f"{close_local.date().isoformat()}, not {day.isoformat()} — the host "
            f"clock cannot be compared against this session"
        )
    return close_local.strftime("%H%M")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True, help="local date, YYYY-MM-DD")
    ns = ap.parse_args(argv)
    try:
        day = dt.date.fromisoformat(ns.date)
    except ValueError as exc:
        print(f"bad date {ns.date!r}: {exc}")
        return EXIT_ERROR
    try:
        hhmm = local_close_hhmm(day)
    except Exception as exc:  # noqa: BLE001 — every failure is a refusal, named
        print(f"calendar error for {day.isoformat()}: {type(exc).__name__}: {exc}")
        return EXIT_ERROR
    if hhmm is None:
        print(f"non-session: {day.isoformat()} is not an NYSE session (weekend/holiday)")
        return EXIT_NON_SESSION
    print(hhmm)
    return EXIT_SESSION


if __name__ == "__main__":
    sys.exit(main())
