# PINNED VERBATIM COPY of the #215 consumer for a hermetic interop/contract test.
# Source: hallovorld/renquant-orchestrator @ origin/feat/renquant105-paired-is-harness
#   src/renquant_orchestrator/intraday_pairing_logger.py
#   commit 6fe46f29aeb2d8adf837d4dc96ad4f5d38204571
# Do NOT edit by hand. Re-vendor (copy verbatim) whenever #215 pushes new commits so
# this fixture never drifts from the real CURRENT consumer contract — a stale pin
# gives false interop confidence (Codex #216 r2: "producer and consumer schema/
# version contract must be tested together on their current heads, not via a
# skipped optional import"). When #215 merges to main, delete this fixture and the
# local round-trip test — `test_round_trip_into_intraday_pairing_logger`
# (importorskip) then exercises the real installed module. This "drops the actual
# consumer in" so the tick feed's interop is PROVEN now, not left
# branch-dependent/skipped.
"""renquant105 Stage-1 OPERATIONS-ONLY paired execution-observation logging harness.

OBSERVE-ONLY / post-hoc data collector for the intraday-decisioning RFC
(``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`` §9,
converged r11/r12). For each daily-admitted name on a session it records **raw,
per-arm arrival observations** for the two entry paths:

  * (a) the ACTUAL next-day-open **batch** entry the 104 后 batch placed — a real
    historical fill — with the batch arm's own **arrival/reference quote** at the
    instant the batch became executable (session-T open reference, §9.2c), and
  * (b) the HYPOTHETICAL **intraday** entry — the intraday arm's own arrival
    quote at the **first eligible tick after conviction** (§11b). Nothing is
    placed intraday in Stage-1; the intraday arm has no real fill.

Why raw per-arm observations instead of a single paired shortfall (Codex review,
2026-07-01): measuring BOTH arms against ONE common intraday midpoint made the
batch "shortfall" silently include the overnight/timing move while the intraday
"shortfall" collapsed to ~zero (its entry was defaulted to that same midpoint).
That is a biased estimand, not execution quality. The fix, per §9.1's two-readout
split: give **each arm its own arrival quote at its own executable instant**,
record bid/ask/source-ts/eligibility-ts/fill-model raw, and — only when a total
between-arm difference is even computable — DECOMPOSE it into

  * a **timing / opportunity-cost** component (the market move between the two
    arrival instants — overnight/latency return; NOT execution quality), and
  * a **within-path execution shortfall** per arm (fill vs that arm's OWN arrival
    quote), explicitly flagged NOT an execution-quality verdict because no
    spread / market-impact fill model is applied (``fill_model = "none/raw"``).

No arm's entry is ever defaulted to a midpoint. In Stage-1 the intraday arm has no
real fill, so ``execution_shortfall_intraday`` and ``total_difference`` stay
``null`` (censored, never imputed, §9.2d); the batch arm yields a within-path
``execution_shortfall_batch`` only when its arrival reference is also present, and
the ``timing_component`` only when both arrival mids are present.

Stage-1 is operations-only. This module DELIBERATELY does **not**:

  * emit orders, place trades, promote, pin, or gate anything (OBSERVE-ONLY);
  * render any PASS/FAIL, non-inferiority verdict, ±10-bps claim, or between-arm
    execution-quality comparison — all deferred to the future separate prereg PR
    (design §9.4). ``decomposition.is_execution_quality`` is always ``False``.
  * impute censored cells — a no-fill / no-tick / no-arrival-quote observation is
    RECORDED by cause and left ``null``, never filled in (design §9.2d).

Design conventions (matching ``decision_pnl_attribution`` / ``decision_ledger``):
pure functions over plain data structures for the pairing logic (testable with
zero I/O), plus thin **read-only** loaders whose paths are parameterized so
nothing is hard-coded to the live umbrella tree and tests never touch live state.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .runtime_paths import default_data_root

# Schema version for the pilot JSONL rows — bump if the record shape changes so
# the future experiment (§9.4) can migrate cleanly. v2: raw per-arm arrival
# observations + timing/execution decomposition (replaces the v1 single-mid
# paired shortfall the Codex review flagged as biased).
SCHEMA_VERSION = "2"
STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "observe_only_paired_arrival_obs"

# ---------------------------------------------------------------------------
# FROZEN Stage-1 pre-registration (mirrors the progress doc). These are the
# researcher-degree-of-freedom knobs Codex asked to be frozen BEFORE evidence is
# collected: the tick-selection rule, censoring policy, session/calendar window,
# and the analysis unit. Changing any of them is a recorded decision, not an
# ad-hoc edit — and no downstream analysis may pick a favorable tick post hoc.
# ---------------------------------------------------------------------------
# Intraday arm arrival tick: the FIRST tick whose quote source-ts is at/after the
# name's conviction/eligibility instant (as-of enforced) — never a later, more
# favorable tick. Without a declared eligibility instant no tick is selected.
TICK_SELECTION = "first_eligible_tick_after_conviction"
AS_OF_ENFORCED = True
# No spread / market-impact / fill model is applied to any arm. Raw quotes only.
FILL_MODEL = "none/raw"
# Missing observations are recorded by cause and left null — never imputed (§9.2d).
CENSORING = "recorded_not_imputed"
# Independent analysis unit is the session DATE, not the row. The future
# experiment (§9.4) blocks on dates, not on per-name rows.
ANALYSIS_UNIT = "session_date"
# Eligibility window (§11b): first eligible tick at open+5min, no new entries in
# the last 30 min. The as-of / cutoff bounds are enforced against these instants;
# times are never hard-coded (NYSE calendar guard scales half-days upstream).
SESSION_ELIGIBILITY = "open+5min .. close-30min"

FROZEN_PREREG: dict[str, Any] = {
    "tick_selection": TICK_SELECTION,
    "as_of_enforced": AS_OF_ENFORCED,
    "fill_model": FILL_MODEL,
    "censoring": CENSORING,
    "analysis_unit": ANALYSIS_UNIT,
    "session_eligibility": SESSION_ELIGIBILITY,
}

# Read-only defaults. Every public function takes the path/connection explicitly;
# these are only the ad-hoc/CLI fallbacks. Inputs default to the umbrella tree
# (read-only). The pilot OUTPUT defaults under the operator data root (decoupled
# from the umbrella checkout, honoring RENQUANT_DATA_ROOT) — this collector never
# writes into the umbrella git tree by default.
DEFAULT_RUNS_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"
DEFAULT_TICK_SOURCE = Path.home() / "git/github/RenQuant/logs/renquant105_pilot/intraday_ticks.jsonl"
DEFAULT_BATCH_ARRIVAL_SOURCE = (
    Path.home() / "git/github/RenQuant/logs/renquant105_pilot/batch_arrival_quotes.jsonl"
)


def default_pilot_path(data_root: Path | None = None) -> Path:
    """Default accumulating pilot-data file, under the operator data root."""
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "paired_is.jsonl"


# ---------------------------------------------------------------------------
# Input validation — this collector ingests ARBITRARY JSONL, so it enforces the
# consumer contract independently of any producer (the #216 producer censors bad
# quotes, but we must not rely on that here).
# ---------------------------------------------------------------------------
def _valid_price(value: Any) -> bool:
    """A price is valid only if it is finite and strictly positive. NaN / ±inf /
    non-numeric / non-positive values are rejected (a crossed or garbage quote must
    never yield a plausible-looking midpoint)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0.0


def _parse_instant(ts: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp to an aware **UTC** :class:`datetime`, or return
    ``None`` when it is missing, timezone-naive, or malformed.

    String lexical order is NOT chronological across mixed UTC offsets, a trailing
    ``Z`` designator, or DST-shifted offsets (e.g. ``09:36-04:00`` is the SAME
    instant as ``13:36+00:00`` and LATER than ``13:35Z``). Every ordering / cutoff
    comparison therefore parses to a real instant instead of comparing strings. A
    naive timestamp (no offset) is refused — we make no local-time assumption — and
    a malformed one is refused rather than silently mis-ordered."""
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # Accept a trailing 'Z' (UTC designator) that Python 3.10 fromisoformat rejects.
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return None  # naive — refuse (offset required; no local-time guess)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PriceRef:
    """A realized fill: a transacted price with its wall-clock reference."""

    price: float
    time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"price": self.price, "time": self.time}


@dataclass(frozen=True)
class QuoteRef:
    """An arm's ARRIVAL / reference quote at the instant that arm becomes
    executable (§9.1 arrival-price convention). Records bid/ask/source-ts raw; the
    reference mid is DERIVED from bid/ask (or an explicitly supplied ``mid`` when a
    single print — e.g. the opening auction cross — is all that exists, §9.2c) and
    is VALIDATED first: a crossed (``bid > ask``), non-positive, or non-finite quote
    is censored to ``None`` rather than fabricating a plausible midpoint. No
    spread/impact model is applied here; ``mid`` is a raw reference, not a fill."""

    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    source_ts: str | None = None
    source: str | None = None  # e.g. "opening_auction_print", "first_eligible_tick"

    def resolved_mid(self) -> float | None:
        """Reference mid: an explicit ``mid`` if given, else the bid/ask midpoint,
        else ``None`` (recorded, never imputed).

        The quote is VALIDATED before a mid is derived — this collector ingests
        arbitrary JSONL and enforces the consumer contract itself. A crossed market
        (``bid > ask``), a non-positive price, or a non-finite (NaN / ±inf) price is
        invalid market data and yields ``None`` (censored), never a plausible-looking
        midpoint. The raw ``bid`` / ``ask`` are still recorded by :meth:`to_dict`;
        only the DERIVED mid is censored."""
        # Explicit single-print reference (e.g. the opening-auction cross): accept
        # only when finite and positive.
        if self.mid is not None:
            return float(self.mid) if _valid_price(self.mid) else None
        # Derive from bid/ask only when BOTH are finite, positive, and not crossed.
        if self.bid is not None and self.ask is not None:
            if not (_valid_price(self.bid) and _valid_price(self.ask)):
                return None
            bid = float(self.bid)
            ask = float(self.ask)
            if bid > ask:
                return None  # crossed market — invalid, do not fabricate a mid
            return (bid + ask) / 2.0
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.resolved_mid(),
            "source_ts": self.source_ts,
            "source": self.source,
        }


@dataclass(frozen=True)
class ArmObservation:
    """Raw observation for one entry arm (``"batch"`` or ``"intraday"``).

    ``eligible_ts`` = when this arm became executable (batch = session-T open;
    intraday = first eligible tick after conviction, §11b). ``arrival_quote`` = the
    arm's own arrival/reference quote at that instant. ``fill`` = a REAL fill if
    one exists (the batch arm has a real historical fill; the intraday arm has none
    in Stage-1 observe-only). ``fill_model`` is always ``"none/raw"`` — no
    spread/market-impact model is applied, so a fill-vs-arrival delta is NOT an
    execution-quality verdict."""

    arm: str
    eligible_ts: str | None = None
    arrival_quote: QuoteRef | None = None
    fill: PriceRef | None = None
    fill_model: str = FILL_MODEL

    def arrival_mid(self) -> float | None:
        return self.arrival_quote.resolved_mid() if self.arrival_quote else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "eligible_ts": self.eligible_ts,
            "arrival_quote": self.arrival_quote.to_dict() if self.arrival_quote else None,
            "fill": self.fill.to_dict() if self.fill else None,
            "fill_model": self.fill_model,
        }


@dataclass(frozen=True)
class AdmittedName:
    """One daily-admitted candidate (the pre-treatment admit, §9.2). ``side`` is
    ``buy`` for a long entry (the default; shorts are rare per the mandate)."""

    date: str
    ticker: str
    side: str = "buy"
    signal_version: str | None = None  # frozen-signal id (§6 class A); run_id here


# ---------------------------------------------------------------------------
# Pure decomposition logic (no I/O — fully testable)
# ---------------------------------------------------------------------------
def _signed(delta: float, side: str) -> float:
    """Apply the side sign so a POSITIVE result always means "worse for us": for a
    buy, paying above reference is positive; for a sell, selling below is positive."""
    return delta if side == "buy" else -delta


def execution_shortfall(
    fill_price: float | None,
    arrival_mid: float | None,
    side: str,
) -> float | None:
    """WITHIN-PATH execution shortfall of an arm: its fill vs its OWN arrival mid
    (Perold arrival-price convention), signed so positive = worse. This is a raw
    signed deviation ONLY — with ``fill_model = "none/raw"`` it is NOT an
    execution-quality verdict, NOT a spread/impact estimate, and NOT a between-arm
    claim. Returns ``None`` when either input is missing (censored, never imputed).
    """
    if fill_price is None or arrival_mid is None:
        return None
    return _signed(float(fill_price) - float(arrival_mid), side)


def timing_component(
    batch_arrival_mid: float | None,
    intraday_arrival_mid: float | None,
    side: str,
) -> float | None:
    """TIMING / opportunity-cost component: the market move between the two arms'
    arrival instants, measured as (batch arrival mid − intraday arrival mid),
    signed by side. This is the overnight/latency return separating the two
    executable instants — it is NOT execution cost and never was (r2's estimand
    error; r3/§9.1 separate the two). Returns ``None`` if either arrival mid is
    missing."""
    if batch_arrival_mid is None or intraday_arrival_mid is None:
        return None
    return _signed(float(batch_arrival_mid) - float(intraday_arrival_mid), side)


def decompose(
    batch_arm: ArmObservation,
    intraday_arm: ArmObservation,
    side: str,
) -> dict[str, Any]:
    """Decompose the between-arm entry difference into a TIMING component and a
    per-arm WITHIN-PATH execution shortfall, keeping them strictly separated.

    Identity (all signed by side):
        total_difference = timing_component + exec_batch − exec_intraday
    where
        total_difference = signed(batch_fill − intraday_fill)   [both real fills]
        timing_component = signed(batch_arrival_mid − intraday_arrival_mid)
        exec_batch       = signed(batch_fill − batch_arrival_mid)
        exec_intraday    = signed(intraday_fill − intraday_arrival_mid)

    Any term whose inputs are missing is ``None`` (censored, never imputed). In
    Stage-1 the intraday arm has no real fill, so ``execution_shortfall_intraday``
    and ``total_difference`` are ``None`` by construction — the honest state, not a
    zero. ``is_execution_quality`` is always ``False``: no spread/impact fill model
    exists (``fill_model = "none/raw"``), so none of these terms is an
    execution-quality verdict."""
    b_mid = batch_arm.arrival_mid()
    i_mid = intraday_arm.arrival_mid()
    b_fill = batch_arm.fill.price if batch_arm.fill else None
    i_fill = intraday_arm.fill.price if intraday_arm.fill else None

    exec_batch = execution_shortfall(b_fill, b_mid, side)
    exec_intraday = execution_shortfall(i_fill, i_mid, side)
    timing = timing_component(b_mid, i_mid, side)
    total = (
        _signed(float(b_fill) - float(i_fill), side)
        if b_fill is not None and i_fill is not None
        else None
    )

    return {
        "timing_component": timing,
        "execution_shortfall_batch": exec_batch,
        "execution_shortfall_intraday": exec_intraday,
        "total_difference": total,
        # Explicit guard rails so no downstream reader mistakes these raw deltas
        # for an execution-quality verdict.
        "is_execution_quality": False,
        "fill_model": FILL_MODEL,
        "note": (
            "timing_component = opportunity cost between arrival instants (NOT "
            "execution quality); execution_shortfall_* = fill vs that arm's own "
            "arrival mid with fill_model=none/raw — NOT an execution-quality "
            "verdict until a pre-registered spread/impact fill model exists. "
            "total_difference is null unless BOTH arms have a real fill."
        ),
    }


def build_paired_record(
    *,
    date: str,
    ticker: str,
    side: str = "buy",
    batch_arm: ArmObservation,
    intraday_arm: ArmObservation,
    signal_version: str | None = None,
    admitted: bool = True,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one paired RAW-OBSERVATION record for an admitted name.

    Records each arm's raw arrival observation (quote bid/ask/source-ts,
    eligibility ts, fill, fill model) plus the timing-vs-execution decomposition.
    No arm's entry is imputed to a midpoint; any missing input is recorded and
    named in ``censored_reason``. The intraday arm having no real fill is the
    normal Stage-1 state (``intraday_entry_hypothetical = True``), NOT a censoring
    anomaly — only missing OBSERVED inputs are flagged."""
    decomposition = decompose(batch_arm, intraday_arm, side)

    missing: list[str] = []
    if intraday_arm.arrival_quote is None:
        missing.append("no_intraday_tick")
    elif intraday_arm.arrival_mid() is None:
        missing.append("no_intraday_arrival_mid")
    if batch_arm.fill is None:
        missing.append("no_batch_fill")
    if batch_arm.arrival_quote is None:
        missing.append("no_batch_arrival_quote")
    elif batch_arm.arrival_mid() is None:
        missing.append("no_batch_arrival_mid")

    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        # The intraday arm is a counterfactual reference; no real intraday order
        # exists in Stage-1 observe-only. The batch arm is a real historical fill.
        "intraday_entry_hypothetical": True,
        "prereg": dict(FROZEN_PREREG),
        "date": date,
        "ticker": ticker,
        "side": side,
        "signal_version": signal_version,
        "batch_arm": batch_arm.to_dict(),
        "intraday_arm": intraday_arm.to_dict(),
        "decomposition": decomposition,
        "admitted": bool(admitted),
        "filled": batch_arm.fill is not None,
        "censored_reason": "+".join(missing) if missing else None,
    }
    if extra:
        record["extra"] = dict(extra)
    return record


# ---------------------------------------------------------------------------
# Tick-selection rule — FROZEN, explicit, as-of enforced (§9.2 / §11b)
# ---------------------------------------------------------------------------
def select_first_eligible_tick(
    ticks: Sequence[Mapping[str, Any]],
    eligible_after: str | None,
    *,
    not_after: str | None = None,
) -> Mapping[str, Any] | None:
    """Select the intraday arm's arrival tick per the FROZEN rule: the FIRST tick
    whose quote ``source_ts`` is at/after the name's conviction/eligibility instant
    ``eligible_after`` (as-of enforced) — never a later, possibly more favorable,
    tick. Optionally bounded above by ``not_after`` (the close−30min no-entry
    cutoff, §11b): ticks after it are ineligible.

    All comparisons are on true INSTANTS, not raw strings. Timestamps are parsed to
    aware UTC datetimes (:func:`_parse_instant`) so mixed UTC offsets, a trailing
    ``Z``, DST-shifted offsets, and sub-second precision order chronologically —
    lexical string order does NOT (it can pick a later tick as "first", admit a
    pre-eligibility tick, or mishandle ``not_after``).

    Returns ``None`` (censored) when ``eligible_after`` is not supplied (we refuse to
    pick a tick without a declared as-of, closing the post-hoc-selection loophole),
    when no tick carries a parseable timestamp, or when no tick falls in the window.
    A tick whose ``source_ts`` is missing, timezone-naive, or malformed is INELIGIBLE
    (it cannot be ordered as-of, so it is never admitted as "first"). A supplied
    ``eligible_after`` / ``not_after`` that is itself naive or malformed is a control
    error and raises :class:`ValueError` — a bad as-of must fail loud, never silently
    censor everything. Ties on the instant resolve to the first in feed order
    (stable) — deterministic, never "the best price at that instant"."""
    if eligible_after is None:
        return None
    elig = _parse_instant(eligible_after)
    if elig is None:
        raise ValueError(
            "eligible_after must be a timezone-aware ISO-8601 instant, got "
            f"{eligible_after!r}"
        )
    cutoff: datetime | None = None
    if not_after is not None:
        cutoff = _parse_instant(not_after)
        if cutoff is None:
            raise ValueError(
                "not_after must be a timezone-aware ISO-8601 instant, got "
                f"{not_after!r}"
            )
    # Parse each tick to a real instant; ticks with a missing / naive / malformed
    # timestamp are ineligible (cannot be chronologically ordered as-of). Keep the
    # original feed index so ties break to feed order (stable) and selection can
    # never prefer a better price.
    parsed: list[tuple[datetime, int, Mapping[str, Any]]] = []
    for idx, tick in enumerate(ticks):
        inst = _parse_instant(tick.get("source_ts"))
        if inst is None:
            continue
        parsed.append((inst, idx, tick))
    parsed.sort(key=lambda item: (item[0], item[1]))
    for inst, _idx, tick in parsed:
        if inst < elig:
            continue  # before eligibility — cannot be used
        if cutoff is not None and inst > cutoff:
            break  # past the no-entry cutoff; all later ticks are too
        return tick
    return None


def _quote_from_tick(tick: Mapping[str, Any]) -> QuoteRef:
    """Build the intraday arrival :class:`QuoteRef` from a selected tick line."""
    return QuoteRef(
        bid=tick.get("bid"),
        ask=tick.get("ask"),
        mid=tick.get("mid"),
        source_ts=tick.get("source_ts"),
        source=tick.get("source", "first_eligible_tick"),
    )


# ---------------------------------------------------------------------------
# The join
# ---------------------------------------------------------------------------
def pair_records(
    admitted: Iterable[AdmittedName],
    batch_fills: Mapping[tuple[str, str], PriceRef],
    intraday_ticks: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    *,
    batch_arrivals: Mapping[tuple[str, str], QuoteRef] | None = None,
    eligibility: Mapping[tuple[str, str], str] | None = None,
    not_after: Mapping[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Join admitted names to (i) their real batch fill, (ii) the batch arrival
    reference quote, and (iii) their intraday arrival tick selected by the FROZEN
    first-eligible-tick rule, producing one raw-observation record per admitted
    name (censored rows included — recorded, not dropped, §9.2d).

    ``batch_fills`` is keyed by ``(signal_version, ticker)`` (the run_id that placed
    the order) with a ``(date, ticker)`` fallback. ``intraday_ticks`` maps
    ``(date, ticker)`` to the RAW LIST of that name's ticks (all of them — selection
    happens here, not in the loader, so no favorable tick can be pre-picked). Each
    tick is ``{"source_ts", "bid"?, "ask"?, "mid"?, "eligible_after"?}``.
    ``batch_arrivals`` maps ``(date, ticker)`` to the batch arm's arrival quote
    (session-T open reference, §9.2c); absent → the batch within-path execution and
    the timing component are censored. ``eligibility`` supplies the intraday
    conviction/as-of instant per name (falls back to a tick's ``eligible_after``);
    ``not_after`` supplies the close−30min cutoff per name."""
    batch_arrivals = batch_arrivals or {}
    eligibility = eligibility or {}
    not_after = not_after or {}
    records: list[dict[str, Any]] = []
    for name in admitted:
        key = (name.date, name.ticker)
        fill_key = (name.signal_version or name.date, name.ticker)
        batch_fill = batch_fills.get(fill_key) or batch_fills.get(key)

        batch_arm = ArmObservation(
            arm="batch",
            eligible_ts=(
                batch_arrivals[key].source_ts if key in batch_arrivals else None
            ),
            arrival_quote=batch_arrivals.get(key),
            fill=batch_fill,
        )

        name_ticks = intraday_ticks.get(key, [])
        eligible_after = eligibility.get(key)
        if eligible_after is None:
            # Fall back to an eligibility instant stamped on the ticks themselves.
            for t in name_ticks:
                if t.get("eligible_after") is not None:
                    eligible_after = str(t["eligible_after"])
                    break
        selected = select_first_eligible_tick(
            name_ticks, eligible_after, not_after=not_after.get(key)
        )
        intraday_arm = ArmObservation(
            arm="intraday",
            eligible_ts=eligible_after,
            arrival_quote=_quote_from_tick(selected) if selected is not None else None,
            fill=None,  # no real intraday order in Stage-1 (observe-only)
        )

        records.append(
            build_paired_record(
                date=name.date,
                ticker=name.ticker,
                side=name.side,
                batch_arm=batch_arm,
                intraday_arm=intraday_arm,
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
    renders no execution-quality verdict (§9.3); those are deferred to §9.4.

    ``analysis_unit`` is echoed as ``session_date`` and the number of distinct
    session dates is reported alongside the row count, because the independent
    unit for the future experiment is the DATE, not the row (§9.4)."""
    censored: dict[str, int] = {}
    n_batch_fill = 0
    n_intraday_tick = 0
    n_batch_arrival = 0
    n_timing = 0
    n_exec_batch = 0
    n_complete_obs = 0
    dates: set[str] = set()
    for r in records:
        dates.add(str(r.get("date")))
        reason = r.get("censored_reason")
        if reason:
            censored[reason] = censored.get(reason, 0) + 1
        else:
            n_complete_obs += 1
        batch_arm = r.get("batch_arm") or {}
        intraday_arm = r.get("intraday_arm") or {}
        if batch_arm.get("fill") is not None:
            n_batch_fill += 1
        if batch_arm.get("arrival_quote") is not None:
            n_batch_arrival += 1
        if intraday_arm.get("arrival_quote") is not None:
            n_intraday_tick += 1
        decomp = r.get("decomposition") or {}
        if decomp.get("timing_component") is not None:
            n_timing += 1
        if decomp.get("execution_shortfall_batch") is not None:
            n_exec_batch += 1
    return {
        "analysis_unit": ANALYSIS_UNIT,
        "n_sessions": len(dates),
        "n_admitted_pairs": len(records),
        "n_complete_observations": n_complete_obs,
        "n_censored_pairs": len(records) - n_complete_obs,
        "n_with_batch_fill": n_batch_fill,
        "n_with_batch_arrival_quote": n_batch_arrival,
        "n_with_intraday_tick": n_intraday_tick,
        "n_timing_computable": n_timing,
        "n_exec_batch_computable": n_exec_batch,
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
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Load the structured intraday decision-tick quote source (JSONL) for a
    session, keyed by ``(date, ticker)`` to the RAW LIST of that name's ticks.

    The loader deliberately does NOT collapse a name to a single tick — it returns
    every tick so :func:`select_first_eligible_tick` (the FROZEN, as-of-enforced
    rule) makes the choice, closing the loophole where a favorable tick could be
    pre-selected. Each line is
    ``{"date", "ticker", "source_ts", "bid"?, "ask"?, "mid"?, "eligible_after"?}``.
    This is the pluggable feed the future intraday full-decisioning loop emits;
    until it lands the source is typically absent, so every pair is censored
    ``no_intraday_tick`` — the correct, honest Stage-1 state. A missing file yields
    an empty mapping."""
    p = Path(path)
    if not p.exists():
        return {}
    ticks: dict[tuple[str, str], list[dict[str, Any]]] = {}
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
            ticks.setdefault((date, obj["ticker"]), []).append(obj)
    return ticks


def load_batch_arrivals(
    path: str | Path,
    date: str,
) -> dict[tuple[str, str], QuoteRef]:
    """Load the batch arm's arrival reference quotes (session-T open reference,
    §9.2c) for a session from a JSONL source, keyed by ``(date, ticker)``.

    Each line is ``{"date", "ticker", "bid"?, "ask"?, "mid"?, "source_ts"?,
    "source"?}`` — the primary-listing opening-auction print, or the first
    consolidated NBBO midpoint at/after 09:30 ET as the named fallback. If several
    lines share a name the first is kept (opening reference is a single instant). A
    missing file yields an empty mapping (batch within-path execution + timing then
    censored — recorded, never imputed)."""
    p = Path(path)
    if not p.exists():
        return {}
    arrivals: dict[tuple[str, str], QuoteRef] = {}
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
            key = (date, obj["ticker"])
            if key in arrivals:
                continue
            arrivals[key] = QuoteRef(
                bid=obj.get("bid"),
                ask=obj.get("ask"),
                mid=obj.get("mid"),
                source_ts=obj.get("source_ts"),
                source=obj.get("source", "opening_auction_print"),
            )
    return arrivals


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY; --dry-run / --json summary
# ---------------------------------------------------------------------------
def collect(
    *,
    date: str,
    runs_db: str | Path,
    tick_source: str | Path,
    batch_arrival_source: str | Path | None = None,
    run_type: str = "live",
) -> list[dict[str, Any]]:
    """Read-only end-to-end pairing for a session: load admitted + batch fills +
    batch arrival quotes + intraday ticks and return the raw-observation records.
    Places nothing, writes nothing."""
    conn = connect(runs_db)
    try:
        admitted = load_admitted(conn, date, run_type=run_type)
        batch_fills = load_batch_fills(conn, admitted)
    finally:
        conn.close()
    ticks = load_intraday_ticks(tick_source, date)
    batch_arrivals = (
        load_batch_arrivals(batch_arrival_source, date) if batch_arrival_source else {}
    )
    return pair_records(
        admitted, batch_fills, ticks, batch_arrivals=batch_arrivals
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-pairing-logger",
        description=(
            "renquant105 Stage-1 OPERATIONS-ONLY paired intraday-vs-batch "
            "arrival-observation logger. OBSERVE-ONLY: collects raw per-arm "
            "arrival data; places no orders and renders no execution-quality "
            "verdict (timing vs within-path execution are recorded separately)."
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
        "--batch-arrival-source",
        default=str(DEFAULT_BATCH_ARRIVAL_SOURCE),
        help="batch arm arrival-quote JSONL (session-T open reference; may be absent)",
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
        batch_arrival_source=args.batch_arrival_source,
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
        print(f"[OBSERVE-ONLY] renquant105 Stage-1 paired arrival logger — {args.date}")
        print(f"  mode                : {summary['mode']}")
        print(f"  analysis unit       : {summary['analysis_unit']}")
        print(f"  sessions            : {summary['n_sessions']}")
        print(f"  admitted pairs      : {summary['n_admitted_pairs']}")
        print(f"  complete obs        : {summary['n_complete_observations']}")
        print(f"  censored pairs      : {summary['n_censored_pairs']}")
        print(f"  with batch fill     : {summary['n_with_batch_fill']}")
        print(f"  with batch arrival  : {summary['n_with_batch_arrival_quote']}")
        print(f"  with intraday tick  : {summary['n_with_intraday_tick']}")
        print(f"  timing computable   : {summary['n_timing_computable']}")
        print(f"  exec-batch computable: {summary['n_exec_batch_computable']}")
        if summary["censored_by_reason"]:
            print("  censored by reason  :")
            for reason, n in sorted(summary["censored_by_reason"].items()):
                print(f"      {reason}: {n}")
        if not args.dry_run:
            print(f"  rows written        : {written} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
