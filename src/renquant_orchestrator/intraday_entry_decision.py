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

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Mapping
from zoneinfo import ZoneInfo

HALT_ENV = "RENQUANT_RQ105_HALT"

#: The session clock. `now_et` is normalised INTO this zone rather than trusted
#: to already be in it — see `_as_et`.
ET = ZoneInfo("America/New_York")


class InvalidDecisionInput(ValueError):
    """Malformed PLUMBING: sizing, counters, guardrails, the clock.

    Raised rather than turned into a rejection, and the distinction is the whole
    input contract of this module. Two kinds of bad input arrive here and they
    deserve opposite treatment:

    * **market data** (a NaN intraday score, an unusable mid) is expected to be
      bad sometimes. It rejects the NAME, with a reason, and the loop continues —
      that is normal operation on a bad tick.
    * **plumbing** (a NaN per-entry notional, a negative counter, incoherent
      guardrails, a naive timestamp) is the caller violating the contract. There
      is no correct plan to return: a NaN notional does not "reject one name", it
      makes every budget comparison meaningless, because every comparison against
      NaN is False. Silently proceeding would produce a plan that LOOKS guarded
      and is not, which for a capital-adjacent core is the worst outcome
      available.
    """


def _finite(x: Any) -> bool:
    """True only for a real, finite number. `bool` is excluded deliberately —
    `True` is an int in Python and must never pass as a notional or a count."""
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x))


def _as_et(now: Any) -> datetime:
    """Normalise to America/New_York, or refuse.

    The parameter was named `now_et` and treated as ET BY NAME ONLY: an aware
    UTC value was compared by wall clock with no conversion, so a 14:00 UTC tick
    read as 14:00 ET — inside the entry window when the market had not opened.
    A naive value was accepted with its zone simply unknowable.
    """
    if not isinstance(now, datetime):
        raise InvalidDecisionInput(f"now_et must be a datetime, got {type(now).__name__}")
    if now.tzinfo is None or now.utcoffset() is None:
        raise InvalidDecisionInput(
            "now_et is naive — its timezone is unknowable, and this value gates "
            "entries. Pass an aware timestamp (any zone; it is converted to ET).")
    return now.astimezone(ET)


def _validate_guardrails(g: "Guardrails") -> None:
    if not (isinstance(g.max_entries_per_day, int) and not isinstance(g.max_entries_per_day, bool)
            and g.max_entries_per_day >= 0):
        raise InvalidDecisionInput(f"max_entries_per_day must be a non-negative int, got {g.max_entries_per_day!r}")
    if not (isinstance(g.max_concurrent_positions, int) and not isinstance(g.max_concurrent_positions, bool)
            and g.max_concurrent_positions >= 0):
        raise InvalidDecisionInput(f"max_concurrent_positions must be a non-negative int, got {g.max_concurrent_positions!r}")
    if not _finite(g.max_notional_per_day) or g.max_notional_per_day < 0:
        raise InvalidDecisionInput(f"max_notional_per_day must be finite and non-negative, got {g.max_notional_per_day!r}")
    for name in ("no_entry_first_minutes", "no_entry_last_minutes"):
        v = getattr(g, name)
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
            raise InvalidDecisionInput(f"{name} must be a non-negative int, got {v!r}")
    if not (isinstance(g.session_open, time) and isinstance(g.session_close, time)):
        raise InvalidDecisionInput("session_open/session_close must be datetime.time")
    if g.session_open >= g.session_close:
        raise InvalidDecisionInput(
            f"session bounds are incoherent: open {g.session_open} >= close {g.session_close}")
    # The edge exclusions must leave a window; otherwise every tick is
    # "outside_entry_window" and the loop silently never enters — a guardrail
    # that blocks everything is indistinguishable from a broken one.
    span = ((g.session_close.hour * 60 + g.session_close.minute)
            - (g.session_open.hour * 60 + g.session_open.minute))
    if g.no_entry_first_minutes + g.no_entry_last_minutes >= span:
        raise InvalidDecisionInput(
            f"no-entry edges ({g.no_entry_first_minutes}+{g.no_entry_last_minutes} min) "
            f"consume the whole {span}-minute session — no tick could ever enter")


def _validate_state(*, entries_today: Any, notional_today: Any,
                    held_plus_pending: Any, per_entry_notional: Any) -> None:
    for name, v in (("entries_today", entries_today),
                    ("held_plus_pending", held_plus_pending)):
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
            raise InvalidDecisionInput(f"{name} must be a non-negative int, got {v!r}")
    if not _finite(notional_today) or notional_today < 0:
        raise InvalidDecisionInput(
            f"notional_today must be finite and non-negative, got {notional_today!r}")
    if not _finite(per_entry_notional) or per_entry_notional <= 0:
        raise InvalidDecisionInput(
            f"per_entry_notional must be finite and strictly positive, got "
            f"{per_entry_notional!r} — a non-positive or NaN size defeats the "
            f"daily budget instead of consuming it")

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
    _validate_guardrails(g)
    _validate_state(entries_today=entries_today, notional_today=notional_today,
                    held_plus_pending=held_plus_pending,
                    per_entry_notional=per_entry_notional)
    now_et = _as_et(now_et)
    e = env if env is not None else os.environ
    block = _session_block(now_et, g, entries_today=entries_today,
                           notional_today=notional_today,
                           held_plus_pending=held_plus_pending, env=e)
    if block:
        return EntryPlan(intents=(), guardrails=g, session_block=block,
                         rejections={c.ticker: block for c in candidates})

    rejections: dict[str, str] = {}
    admitted: list[EntryCandidate] = []

    # IDENTITY BEFORE ADMISSION. `rejections` is keyed by ticker and each intent
    # names one, so the module's "exactly one outcome per name" contract is only
    # true if names are unique. Two rows for the same ticker previously produced
    # two intents — double-consuming the daily budget for one position — or
    # silently overwrote one row's rejection with the other's.
    #
    # Every occurrence of a duplicated name is rejected, not deduplicated to the
    # "best" one. Picking a winner would mean inventing a rule the design does
    # not state, and doing it inside a capital-adjacent path; a caller handing
    # this function two rows for one ticker has a bug upstream and should hear
    # about it rather than get a plausible answer.
    seen: dict[str, int] = {}
    for c in candidates:
        key = c.ticker.strip() if isinstance(c.ticker, str) else ""
        seen[key] = seen.get(key, 0) + 1

    for c in candidates:
        key = c.ticker.strip() if isinstance(c.ticker, str) else ""
        if not key:
            rejections[c.ticker if isinstance(c.ticker, str) else ""] = "blank_ticker"
        elif seen[key] > 1:
            rejections[c.ticker] = "duplicate_ticker"
        elif not c.batch_admitted:
            rejections[c.ticker] = "not_batch_admitted"       # intraday can veto, never create
        elif c.quote_status != "fresh":
            rejections[c.ticker] = "intraday_quote_censored"  # stale tape = fail closed
        elif c.intraday_score is None:
            rejections[c.ticker] = "intraday_veto"
        elif not _finite(c.intraday_score):
            # NaN/inf slipped through `<= 0.0`, which is False for NaN, so a
            # NaN-scored name was ADMITTED and then sorted on.
            rejections[c.ticker] = "intraday_score_not_finite"
        elif c.intraday_score <= 0.0:
            rejections[c.ticker] = "intraday_veto"
        elif c.intraday_mid is None:
            rejections[c.ticker] = "no_usable_mid"
        elif not _finite(c.intraday_mid):
            # Same hole, and this one becomes the order's limit_price.
            rejections[c.ticker] = "intraday_mid_not_finite"
        elif c.intraday_mid <= 0:
            rejections[c.ticker] = "no_usable_mid"
        elif c.batch_expected_return is not None and not _finite(c.batch_expected_return):
            # Carried verbatim into the intent; a NaN would travel downstream as
            # if it were a measurement.
            rejections[c.ticker] = "batch_expected_return_not_finite"
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
