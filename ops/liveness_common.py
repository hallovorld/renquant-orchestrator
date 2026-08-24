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
RQ_ROOT_DEFAULT = "/Users/renhao/git/github/RenQuant"


def resolve_common_src(orch_root: str) -> str:
    """The PINNED renquant-common src, verified against subrepos.lock.json.

    This used to walk ("renquant-common-run", "renquant-common") and take the
    first that existed, so which copy of the code executed was decided by
    filesystem state rather than by review (orch#1016). The first fix replaced
    that with one NAMED sibling checkout, which was still wrong: a directory
    name is not a revision, and the named sibling is a mutable working tree.

    It now delegates to ops/renquant105/rq105_pinned_common.py — the same
    implementation the shell wrappers call — which resolves
    <RQ_ROOT>/.subrepo_runtime/repos/renquant-common/src and refuses unless its
    HEAD matches the umbrella's recorded pin.

    `orch_root` is accepted for call-site compatibility and to derive RQ_ROOT
    when it is not in the environment; the CHECKOUT is never chosen from it.
    """
    ops_rq105 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renquant105")
    if ops_rq105 not in sys.path:
        sys.path.insert(0, ops_rq105)
    from rq105_pinned_common import resolve_pinned_common_src  # noqa: PLC0415

    rq_root = os.environ.get("RQ_ROOT") or RQ_ROOT_DEFAULT
    return resolve_pinned_common_src(rq_root)


def _ensure_orch_on_path() -> None:
    root = os.environ.get("RQ_ORCH_ROOT", os.environ.get("RQ104_ORCH_ROOT", ORCH_DEFAULT))
    p = os.path.join(root, "src")
    if p not in sys.path:
        sys.path.insert(0, p)
    c = resolve_common_src(root)
    if c not in sys.path:
        sys.path.insert(0, c)


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


def alert(title: str, body: str, *, rq_root: str | None = None) -> bool:
    """Send an ntfy alert via renquant_common.notify (campaign B6 canonical).

    RETURNS THE SEND-ATTEMPT OUTCOME — NOT DELIVERY. Codex on #672: a ``True``
    here proves only that ``notify.send`` built the request and the server accepted
    it. It does not prove an operator received, saw, or acted on anything. Treating
    it as delivery evidence would be the same over-reach this function exists to
    correct, one step further along the chain: "the POST succeeded" and "somebody
    was told" are different facts, and only the first is observable from here.

    It used to return ``None``, and
    ``renquant_common.notify.send`` is deliberately built never to raise into a
    monitor -- it swallows the failure, increments a counter and returns
    ``False``. So the bool was the only in-process evidence that an alarm
    reached anybody, and this function threw it away: measured 2026-07-31,
    **0 of 12 call sites** could observe delivery, because there was nothing to
    observe.

    That made "raised an alarm" and "the send was never even attempted"
    indistinguishable at every caller -- the same shape as a crashed sentinel
    exiting with the alarm code, one layer up. Callers can now record the attempt
    outcome; nothing here observes receipt.
    """
    rq = rq_root or os.environ.get("RQ_ROOT", RQ_DEFAULT)
    try:
        from renquant_common.notify import send
    except ImportError as exc:
        print(
            f"WARNING: renquant_common.notify unavailable ({exc}); "
            f"alert NOT sent: {title}: {body}",
            file=sys.stderr,
        )
        return False
    return bool(send(title, body, env_file=os.path.join(rq, ".env")))
