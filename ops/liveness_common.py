"""Shared liveness-check primitives for all ops checkers (XC-8 dedup).

Provides NYSE session-day gating and ntfy alerting — the two helpers
that were copy-pasted across pit_liveness_check.py, rq105_liveness_check.py,
and now rq104_liveness_check.py.

This module is an ops utility (deployed alongside the checkers in the -run
checkout), NOT a library import for src/ code.
"""
from __future__ import annotations

import datetime as dt
import os
import sys


RQ_DEFAULT = "/Users/renhao/git/github/RenQuant"
ORCH_DEFAULT = "/Users/renhao/git/github/renquant-orchestrator-run"


def _ensure_orch_on_path() -> None:
    root = os.environ.get("RQ_ORCH_ROOT", os.environ.get("RQ104_ORCH_ROOT", ORCH_DEFAULT))
    p = os.path.join(root, "src")
    if p not in sys.path:
        sys.path.insert(0, p)
    for name in ("renquant-common-run", "renquant-common"):
        c = os.path.join(os.path.dirname(root), name, "src")
        if os.path.isdir(c) and c not in sys.path:
            sys.path.insert(0, c)
            break


def session_calendar():
    """Real NYSE calendar (holiday/half-day aware)."""
    _ensure_orch_on_path()
    from renquant_orchestrator.intraday_quote_logger import default_session_calendar
    return default_session_calendar()


def is_session_day(day: dt.date) -> bool:
    try:
        return session_calendar().session_bounds(day) is not None
    except Exception as exc:
        print(
            f"WARNING: NYSE calendar check failed ({exc}); treating {day} as a "
            f"session day (fail-closed: do not silently skip a possible lapse)",
            file=sys.stderr,
        )
        return True


def alert(title: str, body: str, *, rq_root: str | None = None) -> None:
    """Send an ntfy alert via renquant_common.notify (campaign B6 canonical)."""
    rq = rq_root or os.environ.get("RQ_ROOT", RQ_DEFAULT)
    try:
        from renquant_common.notify import send
    except ImportError as exc:
        print(
            f"WARNING: renquant_common.notify unavailable ({exc}); "
            f"alert NOT sent: {title}: {body}",
            file=sys.stderr,
        )
        return
    send(title, body, env_file=os.path.join(rq, ".env"))
