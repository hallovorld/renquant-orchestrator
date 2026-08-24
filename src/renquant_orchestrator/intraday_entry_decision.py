"""rq105 S3-P4a: the intraday entry DECISION core — pure, guarded, inert.

This module decides; it never executes. The broker leg (S3-P4b) consumes the
:class:`EntryPlan` this returns, and the live flip (S3-c) is an explicit
operator authorization on top of THAT. Shipping the decision core first keeps
the capital-touching surface reviewable in isolation, and lets the S3-b shadow
window exercise the exact production decision path with zero order risk.

V1 ADMISSION = BATCH ∩ INTRADAY (design #1026 §4, unchanged by #1030): a name
may be entered intraday only if the day's 13:55 batch run direction-admitted
it AND the intraday re-score still admits it. Intraday data can VETO a batch
admission, never create one — this bounds the domain shift of scoring an
EOD-trained model on intraday state. A censored intraday quote is a veto
(fail closed), not a pass-through.

EVERY REJECTION IS NAMED PER NAME. The three notification incidents
(RenQuant#598/#599/#600) were all "a message naming a cause that is not the
cause"; this module makes the binding constraint explicit at the source so no
downstream renderer has to guess.

GUARDRAILS ARE DATA, NOT CODE PATHS: the limits arrive as a frozen
:class:`Guardrails` value, defaults exactly as the approved design table
(2 entries/day, $1,500/day, 15-minute session edges, shared position cap,
halt switch). A caller cannot "forget" a guardrail — the decision function
applies all of them unconditionally, in a fixed order, and reports which one
bound.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Mapping

HALT_ENV = "RENQUANT_RQ105_HALT"

#: Fixed evaluation order — the FIRST failing check names the rejection.
#: Session-level checks come before per-name checks so a halted or
#: out-of-window loop rejects everything with the session reason.
_SESSION_CHECKS = ("halted", "outside_entry_window", "daily_entry_budget_exhausted",
                   "daily_notional_budget_exhausted", "position_cap_full")


@dataclass(frozen=True)
class Guardrails:
    """The approved-design v1 limits (#1026 §5). Frozen so a plan's provenance
    can state exactly which limits produced it."""
    max_entries_per_day: int = 2
    max_notional_per_day: float = 1_500.0
    no_entry_first_minutes: int = 15
    no_entry_last_minutes: int = 15
    max_concurrent_positions: int = 8
    session_open: time = time(9, 30)
    session_close: time = time(16, 0)


@dataclass(frozen=True)
class EntryCandidate:
    ticker: str
    batch_admitted: bool
    batch_expected_return: float | None
    intraday_score: float | None
    quote_status: str            # "fresh" | "stale" | anything else = not fresh
    intraday_mid: float | None


@dataclass(frozen=True)
class EntryPlan:
    """The decision output: intents in priority order + every rejection named."""
    intents: tuple[dict, ...]
    rejections: Mapping[str, str]
    session_block: str | None
    guardrails: Guardrails


def _session_block(now_et: datetime, g: Guardrails, *, entries_today: int,
                   notional_today: float, held_plus_pending: int,
                   env: Mapping[str, str]) -> str | None:
    if env.get(HALT_ENV) == "1":
        return "halted"
    t = now_et.time()
    if t < _plus_minutes(g.session_open, g.no_entry_first_minutes) \
            or t >= _minus_minutes(g.session_close, g.no_entry_last_minutes):
        return "outside_entry_window"
    if entries_today >= g.max_entries_per_day:
        return "daily_entry_budget_exhausted"
    if notional_today >= g.max_notional_per_day:
        return "daily_notional_budget_exhausted"
    if held_plus_pending >= g.max_concurrent_positions:
        return "position_cap_full"
    return None


def _plus_minutes(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time(total // 60, total % 60)


def _minus_minutes(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute - minutes
    return time(total // 60, total % 60)


def decide_entries(
    candidates: list[EntryCandidate],
    *,
    now_et: datetime,
    entries_today: int,
    notional_today: float,
    held_plus_pending: int,
    per_entry_notional: float,
    guardrails: Guardrails | None = None,
    env: Mapping[str, str] | None = None,
) -> EntryPlan:
    """Apply admission + every guardrail; return intents and named rejections.

    ``per_entry_notional`` is the sizing the execution leg intends; the daily
    notional budget is enforced HERE against it so the plan can never exceed
    the budget by construction, rather than trusting the executor to stop.
    """
    g = guardrails or Guardrails()
    e = env if env is not None else os.environ
    block = _session_block(now_et, g, entries_today=entries_today,
                           notional_today=notional_today,
                           held_plus_pending=held_plus_pending, env=e)
    if block:
        return EntryPlan(intents=(), guardrails=g, session_block=block,
                         rejections={c.ticker: block for c in candidates})

    rejections: dict[str, str] = {}
    admitted: list[EntryCandidate] = []
    for c in candidates:
        if not c.batch_admitted:
            rejections[c.ticker] = "not_batch_admitted"       # intraday can veto, never create
        elif c.quote_status != "fresh":
            rejections[c.ticker] = "intraday_quote_censored"  # stale tape = fail closed
        elif c.intraday_score is None or c.intraday_score <= 0.0:
            rejections[c.ticker] = "intraday_veto"
        elif c.intraday_mid is None or c.intraday_mid <= 0:
            rejections[c.ticker] = "no_usable_mid"
        else:
            admitted.append(c)

    admitted.sort(key=lambda c: (-(c.intraday_score or 0.0), c.ticker))
    intents: list[dict] = []
    entries = entries_today
    notional = notional_today
    slots = held_plus_pending
    for c in admitted:
        if entries >= g.max_entries_per_day:
            rejections[c.ticker] = "daily_entry_budget_exhausted"; continue
        if notional + per_entry_notional > g.max_notional_per_day:
            rejections[c.ticker] = "daily_notional_budget_exhausted"; continue
        if slots >= g.max_concurrent_positions:
            rejections[c.ticker] = "position_cap_full"; continue
        intents.append({"ticker": c.ticker, "limit_price": c.intraday_mid,
                        "notional_budget": per_entry_notional,
                        "intraday_score": c.intraday_score,
                        "batch_expected_return": c.batch_expected_return})
        entries += 1; notional += per_entry_notional; slots += 1
    return EntryPlan(intents=tuple(intents), rejections=rejections,
                     session_block=None, guardrails=g)
