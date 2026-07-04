"""renquant105 Stage-1 OBSERVE-ONLY entry-timing shadow evaluator.

Pilot-data collector for the intraday-decisioning RFC
(``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`` §5.3,
§6, §9, §11b — converged r11/r12). For each **daily-admitted** name on a session
it replays a set of **PRE-REGISTERED candidate entry-timing policies** against the
real-time tick feed and logs, per name per policy, what that policy **WOULD** have
chosen — the entry instant + the reference quote at that instant + eligibility.

It places **NO** orders and makes **NO** live decision. It is a downstream, purely
observational reader of the class-D "timing-only quote" feed (design §6): it never
touches positions, cash, pins, gates, or run state, and it renders **NO**
fill-quality / implementation-shortfall / PASS-FAIL claim (all deferred to the
future, separate experiment-prereg PR, design §9.4). This complements the paired-IS
harness (orchestrator #215): #215 accumulates the intraday-vs-batch shortfall pair;
this collects the *entry-timing-policy* pilot corpus feeding the same experiment.

Stage-1 posture (design §9.3, converged r11): **operations-only, observe-only.**
This module DELIBERATELY does **not**:

  * place orders, promote, pin, size, or gate anything (no trading surface exists);
  * compute any shortfall / fill / execution-quality metric or bps figure;
  * render any PASS/FAIL or non-inferiority verdict;
  * impute a censored cell — a policy that never triggers is RECORDED by cause and
    left censored (``eligible = false`` + ``censored_reason``), never filled in
    (design §9.2d).

Tick-feed contract (reuse — do NOT re-collect, do NOT re-derive session rules):
this consumes the SAME ``intraday_ticks.jsonl`` **eligible** feed produced by the
decoupled intraday quote logger (orchestrator #216) and read by the paired-IS
harness (#215). #216 already applied the FROZEN eligibility policy at collection
time; this evaluator therefore **reuses #216's certification** rather than
reimplementing weaker rules:

  * **Eligible status (reuse #216, do NOT re-decide).** Only rows the #216 producer
    stamped ``status = "ok"`` (:data:`ELIGIBLE_STATUS`) are admitted as evidence.
    A row without that status — a censored observation that leaked, or a legacy /
    unverified quote from before the eligibility policy existed — is DROPPED, never
    treated as a decision tick. The producer's frozen
    :data:`FEED_ELIGIBILITY_POLICY_VERSION` is carried onto every shadow row so the
    corpus self-identifies which eligibility policy admitted the underlying tick.
  * **Session boundaries = the shared exchange calendar (reuse #216, do NOT
    hard-code clock times).** #216 resolves each session's ``[open, close)`` from the
    SAME NYSE ``pandas_market_calendars`` primitive execution uses — honoring
    holidays (no session), half-days / early closes (earlier ``close``) and DST —
    and stamps those calendar-resolved bounds (``session_open`` / ``session_close``)
    on every eligible tick. This evaluator reads those stamped bounds; the §11b
    entry window scales to the actual session (open+offset … close−cutoff) with **no
    hard-coded 09:30–16:00 weekday rule**, so early-close and holiday sessions are
    handled correctly. A tick lacking calendar-resolved bounds is DROPPED (it cannot
    be certified against a real session).
  * **Freshness must be PROVEN, not assumed.** A tick must carry a resolvable quote
    age (#216's stamped ``quote_age``, else recomputed from ``ts`` − ``quote_ts``);
    a row whose age is unknown is DROPPED (never "kept because age is unknown"), and
    a tick older than ``quote_staleness_hard_sec`` (design §6 class-D hard-skip) is
    dropped. An unpriceable row (no ``mid``) is skipped, never imputed.
  * **Causality.** Each policy is a pure function that walks the tick series in
    ascending ``tick_time`` order and returns the FIRST tick satisfying its trigger.
    It NEVER looks forward for a more favorable price. Running state (VWAP, opening
    range) is accumulated only from ticks at or before the tick being evaluated, and
    any reference level a policy triggers against must be **known as-of the decision
    instant** (see :func:`policy_pullback_to_ref`).

The policy set + its parameters + the confirmatory-analysis design are
**PRE-REGISTERED** here as a frozen config (:data:`DEFAULT_CONFIG`, fingerprinted
onto every row) and in the progress doc, so the future experiment (§9.4) knows
exactly which frozen policy produced the corpus, which policy is primary, how
multiplicity is controlled, and that the confirmatory period is held out untouched.
Freezing four policy names is NOT a pre-registration by itself; the frozen design
below closes that gap. The OUTPUT defaults under the operator data root
(:func:`~renquant_orchestrator.runtime_paths.default_data_root`, honoring
``RENQUANT_DATA_ROOT``) — it NEVER writes into the umbrella git tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .runtime_paths import default_data_root

# Reuse the #216 producer's FROZEN eligible-status + policy-version constants when
# the module is importable (binds the shadow to #216's contract, not a re-hardcoded
# literal); fall back to the known literals on a checkout where #216 has not landed
# yet, so this module still imports and its tests still run.
try:  # pragma: no cover - trivial import shim
    from .intraday_quote_logger import (  # type: ignore
        ELIGIBILITY_POLICY_VERSION as _FEED_POLICY_VERSION,
        STATUS_OK as _FEED_STATUS_OK,
    )
except Exception:  # pragma: no cover - #216 not merged on this checkout
    _FEED_STATUS_OK = "ok"
    _FEED_POLICY_VERSION = "renquant105-eligibility-v1"

# Only rows the #216 producer certified eligible (this status) are admitted as
# evidence; every other status is a censored observation and is dropped.
ELIGIBLE_STATUS = _FEED_STATUS_OK
# The producer's frozen eligibility-policy version, carried onto shadow rows for
# provenance (a bare quote stream does not identify which policy admitted it).
FEED_ELIGIBILITY_POLICY_VERSION = _FEED_POLICY_VERSION

# Schema version for the pilot JSONL rows — bump if the record shape changes so the
# future experiment (§9.4) can migrate cleanly. v2: consume #216 status/bounds; the
# pullback reference is now causal (batch_ref is provenance-only, never a trigger).
SCHEMA_VERSION = "2"
STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "observe_only_entry_timing_shadow"

ET = ZoneInfo("America/New_York")

# The pre-registered candidate policy names (frozen; the config pins their params).
POLICY_IMMEDIATE = "immediate_first_eligible_tick"
POLICY_VWAP_CROSS = "vwap_cross"
POLICY_OPENING_RANGE_BREAKOUT = "opening_range_breakout"
POLICY_PULLBACK_TO_REF = "pullback_to_ref"

REGISTERED_POLICIES = (
    POLICY_IMMEDIATE,
    POLICY_VWAP_CROSS,
    POLICY_OPENING_RANGE_BREAKOUT,
    POLICY_PULLBACK_TO_REF,
)

# Causal pullback reference kinds — both are known AS-OF the decision instant.
REF_KIND_PRIOR_CLOSE = "prior_close"   # a frozen daily level, known pre-market
REF_KIND_OPENING_PRINT = "opening_print"  # the first observed in-session tick mid


def default_pilot_path(data_root: Path | None = None) -> Path:
    """Default accumulating entry-timing pilot file, under the operator data root.

    Sits beside the #215/#216 pilot artifacts in ``logs/renquant105_pilot/``. Rooted
    at :func:`default_data_root` (honoring ``RENQUANT_DATA_ROOT``), NEVER the umbrella
    git tree."""
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "entry_timing_shadow.jsonl"


def default_tick_source(data_root: Path | None = None) -> Path:
    """Default tick feed the evaluator reads (single rolling JSONL filtered by date).

    Rooted at :func:`default_data_root` (honoring ``RENQUANT_DATA_ROOT``),
    consistent with :func:`default_pilot_path`."""
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


DEFAULT_TICK_SOURCE = default_tick_source()


# ---------------------------------------------------------------------------
# Pre-registered frozen policy + confirmatory-analysis config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntryTimingConfig:
    """PRE-REGISTERED, frozen entry-timing spec (design §5.3, §6, §9.4, §11b).

    Every field is fixed BEFORE data collection so the corpus is reproducible and
    the future experiment (§9.4) can attribute rows to an exact parameterization via
    :meth:`fingerprint`. Two groups:

    * **policy knobs** — the candidate policies and their windows/thresholds;
    * **confirmatory-analysis design** — the frozen primary policy/endpoint,
      analysis unit, censoring rule, cost/fill model, minimum pilot size,
      multiplicity control, and period policy. Stage-1 COMPUTES NONE of these (it
      renders no verdict); it freezes them so the deferred §9.4 experiment inherits
      an immutable spec and cannot post-hoc pick a winning policy against the same
      data it will be judged on. Freezing four policy names alone is not a
      pre-registration — this closes that gap.

    Long/buy side only (the shorting mandate bar is very high; entry-timing pilots
    the long entry).
    """

    # --- policy knobs -----------------------------------------------------
    # §11b session-boundary entry window (minutes relative to the calendar-resolved
    # open/close; the absolute clock scales to the actual session, incl. early close).
    entry_open_offset_min: int = 5      # no entry in the first 5 min after the open
    entry_close_cutoff_min: int = 30    # no entry in the last 30 min before the close
    # §6 class-D timing-quote freshness hard-skip (seconds); a staler tick is dropped.
    quote_staleness_hard_sec: float = 15.0
    # opening_range_breakout: the opening-range window length (minutes from the open).
    opening_range_minutes: int = 30
    # pullback_to_ref: enter on a dip of at least this fraction below the reference.
    pullback_pct: float = 0.003
    # The frozen, ordered policy set this config pre-registers.
    policies: tuple[str, ...] = REGISTERED_POLICIES

    # --- confirmatory-analysis design (frozen; NOT computed in Stage-1) ----
    # The primary (reference) policy the confirmatory endpoint is defined against —
    # the plumbing baseline. The other candidates are secondary hypotheses.
    primary_policy: str = POLICY_IMMEDIATE
    # The frozen primary endpoint. DEFERRED: Stage-1 stores raw refs only and
    # computes no shortfall; §9.4 computes this against real pilot variance.
    primary_endpoint: str = "implementation_shortfall_vs_arrival_reference__deferred_to_9_4"
    # The unit of analysis for the confirmatory test.
    analysis_unit: str = "session"
    # Censoring rule (§9.2d): a non-triggering policy is recorded by cause, never
    # imputed, and no adversarial bound is applied in Stage-1.
    censoring_rule: str = "recorded_by_cause__never_imputed"
    # Cost/fill model (§9.2c): the reference is the arrival mid (midpoint-as-fill →
    # zero modeled shortfall by construction); a richer fill/cost model is the
    # confirmatory stage's frozen choice, computed against real data in §9.4.
    fill_model: str = "arrival_mid_reference__zero_modeled_shortfall"
    # Minimum disjoint pilot sessions before ANY confirmatory inference may be
    # designed. A pre-registered floor (not the final power-based N, which §9.4 sets
    # against real pilot variance) so the corpus cannot be over-read at tiny N.
    min_pilot_sessions: int = 20
    # Multiplicity control for the family of secondary policies vs the primary.
    multiplicity_control: str = "holm_bonferroni_secondary_vs_primary"
    # Period policy: the pilot period is for policy SELECTION only; the confirmatory
    # evaluation period is HELD OUT and stays untouched during pilot collection.
    period_policy: str = "pilot_selection_only__confirmatory_period_held_out_untouched"

    def policy_params(self, policy: str) -> dict[str, Any]:
        """The frozen parameters that govern a single policy (recorded per row)."""
        window = {
            "entry_open_offset_min": self.entry_open_offset_min,
            "entry_close_cutoff_min": self.entry_close_cutoff_min,
            "quote_staleness_hard_sec": self.quote_staleness_hard_sec,
        }
        if policy == POLICY_OPENING_RANGE_BREAKOUT:
            return {**window, "opening_range_minutes": self.opening_range_minutes}
        if policy == POLICY_PULLBACK_TO_REF:
            return {**window, "pullback_pct": self.pullback_pct}
        return dict(window)

    def frozen_design(self) -> dict[str, Any]:
        """The frozen confirmatory-analysis design (§9.4) — declared, not computed.

        Surfaced in the pre-registration manifest so a reviewer can see the primary
        policy/endpoint, analysis unit, censoring, cost/fill model, minimum pilot
        size, multiplicity control, and held-out confirmatory period are all fixed
        before data exists. Stage-1 renders none of these."""
        return {
            "primary_policy": self.primary_policy,
            "primary_endpoint": self.primary_endpoint,
            "analysis_unit": self.analysis_unit,
            "censoring_rule": self.censoring_rule,
            "fill_model": self.fill_model,
            "min_pilot_sessions": self.min_pilot_sessions,
            "multiplicity_control": self.multiplicity_control,
            "period_policy": self.period_policy,
            # Stage-1 is observe-only: no confirmatory statistic is computed here.
            "confirmatory_inference": "deferred_to_experiment_prereg_9_4",
        }

    def fingerprint(self) -> str:
        """Stable short hash of the frozen spec — pins the corpus to this config.

        Includes BOTH the policy knobs and the confirmatory-analysis design, so
        changing any pre-registered choice (a threshold, the primary policy, the
        multiplicity control …) changes the fingerprint and is auditable."""
        payload = {
            "entry_open_offset_min": self.entry_open_offset_min,
            "entry_close_cutoff_min": self.entry_close_cutoff_min,
            "quote_staleness_hard_sec": self.quote_staleness_hard_sec,
            "opening_range_minutes": self.opening_range_minutes,
            "pullback_pct": self.pullback_pct,
            "policies": list(self.policies),
            "frozen_design": self.frozen_design(),
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


DEFAULT_CONFIG = EntryTimingConfig()


def preregistration_manifest(config: EntryTimingConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """The frozen PRE-REGISTRATION of the candidate policy set + params + design.

    A single canonical dict — the ordered policy set, each policy's frozen params,
    the frozen confirmatory-analysis design (§9.4), the config fingerprint, and the
    schema/stage — surfaced so the progress doc, the ``--print-preregistration``
    CLI, and the future experiment (§9.4) all reference the exact same frozen
    definition. Emitting or asserting this NEVER collects data or places anything
    (observe-only)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        "observe_only": True,
        "config_fingerprint": config.fingerprint(),
        "feed_eligibility_policy_version": FEED_ELIGIBILITY_POLICY_VERSION,
        "policies": list(config.policies),
        "policy_params": {p: config.policy_params(p) for p in config.policies},
        "frozen_design": config.frozen_design(),
    }


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdmittedName:
    """One daily-admitted candidate (the pre-treatment admit, design §9.2).

    ``conviction_time`` (optional ISO ts) constrains the "first eligible tick AFTER
    conviction" rule: entries are only considered at or after it. When absent the
    admit is treated as effective from the session open (the frozen daily signal is
    available pre-market). ``signal_version`` carries the frozen-signal id (class A).
    """

    date: str
    ticker: str
    side: str = "buy"
    signal_version: str | None = None
    conviction_time: str | None = None


@dataclass(frozen=True)
class Tick:
    """A normalized in-session **eligible** timing quote (class-D, #216 status=ok).

    ``mid`` is the decision-time reference; ``tick_time`` is the exchange as-of
    (idempotency/causality axis). ``session_open`` / ``session_close`` are the
    calendar-resolved session bounds #216 stamped (the §11b window scales to them).
    ``quote_age`` is the proven freshness; ``feed_policy_version`` is #216's frozen
    eligibility-policy version (provenance)."""

    date: str
    ticker: str
    tick_time: str
    when: datetime          # parsed, tz-aware (ET) — the causality sort key
    mid: float
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    quote_ts: str | None = None
    volume: float | None = None
    session_open: datetime | None = None
    session_close: datetime | None = None
    quote_age: float | None = None
    feed_policy_version: str | None = None

    def quote(self) -> dict[str, Any]:
        """The raw reference quote carried onto a chosen-entry row (provenance only —
        no fill-quality is derived)."""
        return {
            "mid": self.mid,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "tick_time": self.tick_time,
            "quote_ts": self.quote_ts,
        }


@dataclass(frozen=True)
class PolicyOutcome:
    """What a policy WOULD have chosen — an entry instant + reference quote, or a
    censored (never-triggered) outcome. Carries NO fill-quality metric. ``reference``
    / ``reference_kind`` record the causal, known-as-of level a reference-relative
    policy triggered against (pullback), for provenance."""

    policy: str
    eligible: bool
    entry_tick: Tick | None = None
    censored_reason: str | None = None
    reference: float | None = None
    reference_kind: str | None = None


# ---------------------------------------------------------------------------
# Time / quote helpers (reuse #216's stamped eligibility — do NOT re-decide)
# ---------------------------------------------------------------------------
def _parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp to a tz-aware datetime; a naive value is treated
    as ET. Accepts a trailing ``Z``."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ET)
    return dt


def _parse_dt_opt(value: Any) -> datetime | None:
    """Best-effort parse of an optional ISO ts; ``None`` when absent/unparseable."""
    if not value:
        return None
    try:
        return _parse_dt(str(value))
    except (ValueError, TypeError):
        return None


def _mid_of(record: Mapping[str, Any]) -> float | None:
    """Decision-time mid: prefer the feed's ``mid``; else NBBO midpoint; else last
    trade; else ``None`` (unpriceable — skipped, never imputed)."""
    mid = record.get("mid")
    if mid is not None:
        return float(mid)
    bid, ask = record.get("bid"), record.get("ask")
    if bid is not None and ask is not None:
        return (float(bid) + float(ask)) / 2.0
    last = record.get("last")
    if last is not None:
        return float(last)
    return None


def _quote_age_sec(record: Mapping[str, Any]) -> float | None:
    """Proven quote age (seconds). Prefer #216's authoritative stamped ``quote_age``;
    else recompute from the sample time (``ts``) minus the exchange quote time
    (``quote_ts``). Returns ``None`` when freshness cannot be proven — the caller
    DROPS such a row (never "kept because age is unknown")."""
    stamped = record.get("quote_age")
    if stamped is not None:
        try:
            return float(stamped)
        except (TypeError, ValueError):
            pass
    sample, quote_ts = record.get("ts"), record.get("quote_ts")
    if not sample or not quote_ts:
        return None
    try:
        return (_parse_dt(str(sample)) - _parse_dt(str(quote_ts))).total_seconds()
    except (ValueError, TypeError):
        return None


def normalize_ticks(
    records: Iterable[Mapping[str, Any]],
    *,
    ticker: str,
    date: str,
    config: EntryTimingConfig = DEFAULT_CONFIG,
) -> list[Tick]:
    """Filter a ticker's raw feed rows to the causal, eligible, fresh, priceable,
    calendar-in-session series and sort it ascending by ``tick_time``.

    Reuses #216's certification rather than re-deriving weaker rules: it admits ONLY
    rows the producer stamped ``status = "ok"`` (:data:`ELIGIBLE_STATUS`), requires a
    PROVEN quote age (drops rows whose freshness is unknown, and drops rows staler
    than ``quote_staleness_hard_sec``), requires the calendar-resolved session bounds
    #216 stamped (``session_open`` / ``session_close``) and that the tick falls inside
    them, and skips unpriceable rows (no mid). It does NOT re-collect or re-decide
    session membership with a hard-coded 09:30–16:00 weekday rule.
    """
    ticks: list[Tick] = []
    for r in records:
        if r.get("date") != date or r.get("ticker") != ticker:
            continue
        # (1) reuse #216's eligibility — only certified ``ok`` rows are evidence.
        if str(r.get("status")) != ELIGIBLE_STATUS:
            continue  # censored / legacy / unverified — never a decision tick
        # (2) freshness must be PROVEN, not assumed.
        age = _quote_age_sec(r)
        if age is None:
            continue  # unknown freshness -> dropped
        if age > config.quote_staleness_hard_sec:
            continue  # stale timing quote — class-D hard-skip
        # (3) priceable.
        mid = _mid_of(r)
        if mid is None:
            continue  # unpriceable — skipped, never imputed
        tick_time = r.get("tick_time") or r.get("quote_ts") or r.get("ts")
        if not tick_time:
            continue
        when = _parse_dt_opt(tick_time)
        if when is None:
            continue
        # (4) calendar-resolved session bounds (reuse #216's shared NYSE calendar).
        s_open = _parse_dt_opt(r.get("session_open"))
        s_close = _parse_dt_opt(r.get("session_close"))
        if s_open is None or s_close is None:
            continue  # no calendar-resolved bounds -> cannot certify -> dropped
        if not (s_open <= when < s_close):
            continue  # outside the calendar session -> dropped
        vol = r.get("volume", r.get("size"))
        ticks.append(
            Tick(
                date=date,
                ticker=ticker,
                tick_time=str(tick_time),
                when=when,
                mid=mid,
                bid=r.get("bid"),
                ask=r.get("ask"),
                last=r.get("last"),
                quote_ts=r.get("quote_ts"),
                volume=float(vol) if vol is not None else None,
                session_open=s_open,
                session_close=s_close,
                quote_age=age,
                feed_policy_version=(
                    str(r.get("eligibility_policy_version"))
                    if r.get("eligibility_policy_version")
                    else None
                ),
            )
        )
    ticks.sort(key=lambda t: (t.when, t.tick_time))
    return ticks


# ---------------------------------------------------------------------------
# Entry window (§11b) + eligibility — bounds come from the feed's calendar stamp
# ---------------------------------------------------------------------------
def _entry_window(
    ticks: Sequence[Tick], config: EntryTimingConfig
) -> tuple[datetime | None, datetime | None, datetime | None]:
    """The §11b entry window [open+offset, close−cutoff) + the session open, all in
    the calendar-resolved bounds #216 stamped (early-close/holiday/DST aware — NO
    hard-coded clock). ``(None, None, None)`` when no eligible tick carries bounds
    (then every policy censors)."""
    stamped = next(
        (t for t in ticks if t.session_open is not None and t.session_close is not None),
        None,
    )
    if stamped is None:
        return None, None, None
    open_dt = stamped.session_open
    close_dt = stamped.session_close
    first_eligible = open_dt + timedelta(minutes=config.entry_open_offset_min)
    last_eligible = close_dt - timedelta(minutes=config.entry_close_cutoff_min)
    return first_eligible, last_eligible, open_dt


def _is_eligible(
    tick: Tick,
    *,
    first_eligible: datetime | None,
    last_eligible: datetime | None,
    conviction: datetime | None,
) -> bool:
    """A tick may host an ENTRY iff the §11b window is defined, the tick is inside it,
    and it is at/after the name's conviction time. (State-accumulating ticks before
    the window are still used for VWAP / opening range, but no entry is placed on
    them.)"""
    if first_eligible is None or last_eligible is None:
        return False
    if tick.when < first_eligible or tick.when >= last_eligible:
        return False
    if conviction is not None and tick.when < conviction:
        return False
    return True


# ---------------------------------------------------------------------------
# Pre-registered candidate policies — each a pure function over the tick series
# ---------------------------------------------------------------------------
def policy_immediate(
    ticks: Sequence[Tick],
    *,
    first_eligible: datetime | None,
    last_eligible: datetime | None,
    session_open: datetime | None,
    conviction: datetime | None,
    config: EntryTimingConfig,
    causal_ref: float | None,
) -> PolicyOutcome:
    """Enter at the FIRST eligible tick after conviction (the plumbing baseline,
    design §5.3). As-of correct: the first eligible tick is taken, never a later,
    more favorable one."""
    for t in ticks:
        if _is_eligible(t, first_eligible=first_eligible, last_eligible=last_eligible, conviction=conviction):
            return PolicyOutcome(POLICY_IMMEDIATE, eligible=True, entry_tick=t)
    return PolicyOutcome(POLICY_IMMEDIATE, eligible=False, censored_reason="no_eligible_tick")


def policy_vwap_cross(
    ticks: Sequence[Tick],
    *,
    first_eligible: datetime | None,
    last_eligible: datetime | None,
    session_open: datetime | None,
    conviction: datetime | None,
    config: EntryTimingConfig,
    causal_ref: float | None,
) -> PolicyOutcome:
    """Enter on the first eligible **bullish** VWAP cross-up: the tick where the mid
    transitions from at/below the running VWAP to above it.

    The VWAP is a **causal running** average over the session's ticks so far,
    weighted by ``volume`` when the feed carries it and equal-weighted otherwise
    (the #216 quote feed carries no per-tick volume, so this degenerates to a running
    mean of quote mids — documented, deterministic). Only ticks at or before the
    evaluated tick enter the VWAP (no look-ahead)."""
    cum_pv = 0.0
    cum_w = 0.0
    prev_mid: float | None = None
    prev_vwap: float | None = None
    for t in ticks:
        w = t.volume if (t.volume is not None and t.volume > 0) else 1.0
        cum_pv += t.mid * w
        cum_w += w
        vwap = cum_pv / cum_w
        crossed_up = (
            prev_mid is not None
            and prev_vwap is not None
            and prev_mid <= prev_vwap
            and t.mid > vwap
        )
        if crossed_up and _is_eligible(
            t, first_eligible=first_eligible, last_eligible=last_eligible, conviction=conviction
        ):
            return PolicyOutcome(POLICY_VWAP_CROSS, eligible=True, entry_tick=t)
        prev_mid, prev_vwap = t.mid, vwap
    return PolicyOutcome(POLICY_VWAP_CROSS, eligible=False, censored_reason="no_vwap_cross")


def policy_opening_range_breakout(
    ticks: Sequence[Tick],
    *,
    first_eligible: datetime | None,
    last_eligible: datetime | None,
    session_open: datetime | None,
    conviction: datetime | None,
    config: EntryTimingConfig,
    causal_ref: float | None,
) -> PolicyOutcome:
    """Enter on the first eligible tick whose mid breaks ABOVE the opening-range high.

    The opening range is the max mid over ticks in
    [session_open, session_open + opening_range_minutes) — built only from ticks
    inside that early window (causal), where ``session_open`` is the calendar-resolved
    open #216 stamped (NOT a hard-coded 09:30). The breakout is then the first
    eligible tick after the window whose mid exceeds that high."""
    if not ticks:
        return PolicyOutcome(POLICY_OPENING_RANGE_BREAKOUT, eligible=False, censored_reason="no_ticks")
    if session_open is None:
        return PolicyOutcome(
            POLICY_OPENING_RANGE_BREAKOUT, eligible=False, censored_reason="no_opening_range"
        )
    or_end = session_open + timedelta(minutes=config.opening_range_minutes)
    or_high = max((t.mid for t in ticks if session_open <= t.when < or_end), default=None)
    if or_high is None:
        return PolicyOutcome(
            POLICY_OPENING_RANGE_BREAKOUT, eligible=False, censored_reason="no_opening_range"
        )
    for t in ticks:
        if t.when < or_end:
            continue  # inside the opening range — cannot be a breakout entry yet
        if t.mid > or_high and _is_eligible(
            t, first_eligible=first_eligible, last_eligible=last_eligible, conviction=conviction
        ):
            return PolicyOutcome(POLICY_OPENING_RANGE_BREAKOUT, eligible=True, entry_tick=t)
    return PolicyOutcome(POLICY_OPENING_RANGE_BREAKOUT, eligible=False, censored_reason="no_breakout")


def policy_pullback_to_ref(
    ticks: Sequence[Tick],
    *,
    first_eligible: datetime | None,
    last_eligible: datetime | None,
    session_open: datetime | None,
    conviction: datetime | None,
    config: EntryTimingConfig,
    causal_ref: float | None,
) -> PolicyOutcome:
    """Enter on the first eligible tick that dips to/below a CAUSAL reference level.

    The reference must be **known as-of the decision instant** (Codex blocking
    look-ahead fix). It is:

      * a **prior close / frozen daily level** (``causal_ref``) when supplied — known
        pre-market; else
      * the **observed opening print** = the first in-session eligible tick's mid
        (design §9.2c arrival reference: the opening-auction print / first NBBO mid
        at/after 09:30 ET). This is causal because a trigger only fires on ticks
        at/after the window, by which time the first tick has already been observed.

    The next-open **batch reference** is deliberately NOT used to trigger here: it is
    not known at the decision instant, so using it would be look-ahead. It is carried
    onto the row for provenance only (:func:`build_record`, ``batch_ref``) and is
    excluded from any online triggering. The trigger is a dip of at least
    ``pullback_pct`` below the causal reference."""
    if not ticks:
        return PolicyOutcome(POLICY_PULLBACK_TO_REF, eligible=False, censored_reason="no_ticks")
    if causal_ref is not None:
        ref: float | None = float(causal_ref)
        ref_kind = REF_KIND_PRIOR_CLOSE
    else:
        ref = ticks[0].mid  # observed opening print (already known when we trigger)
        ref_kind = REF_KIND_OPENING_PRINT
    if ref is None:
        return PolicyOutcome(POLICY_PULLBACK_TO_REF, eligible=False, censored_reason="no_reference")
    threshold = ref * (1.0 - config.pullback_pct)
    for t in ticks:
        if t.mid <= threshold and _is_eligible(
            t, first_eligible=first_eligible, last_eligible=last_eligible, conviction=conviction
        ):
            return PolicyOutcome(
                POLICY_PULLBACK_TO_REF,
                eligible=True,
                entry_tick=t,
                reference=ref,
                reference_kind=ref_kind,
            )
    return PolicyOutcome(
        POLICY_PULLBACK_TO_REF,
        eligible=False,
        censored_reason="no_pullback",
        reference=ref,
        reference_kind=ref_kind,
    )


POLICY_FUNCS: dict[str, Callable[..., PolicyOutcome]] = {
    POLICY_IMMEDIATE: policy_immediate,
    POLICY_VWAP_CROSS: policy_vwap_cross,
    POLICY_OPENING_RANGE_BREAKOUT: policy_opening_range_breakout,
    POLICY_PULLBACK_TO_REF: policy_pullback_to_ref,
}


# ---------------------------------------------------------------------------
# Record building (raw refs only — NO shortfall / fill-quality)
# ---------------------------------------------------------------------------
def build_record(
    *,
    name: AdmittedName,
    outcome: PolicyOutcome,
    config: EntryTimingConfig,
    prior_close_ref: float | None = None,
    batch_ref: float | None = None,
    feed_policy_version: str | None = None,
) -> dict[str, Any]:
    """Build one OBSERVE-ONLY entry-timing row for (name, policy).

    Records the chosen entry instant + reference quote + eligibility ONLY. Carries no
    implementation-shortfall, fill, PnL, or PASS/FAIL — those are the future
    experiment's call (design §9.4). ``batch_ref`` (the next-open batch reference) is
    recorded for provenance ONLY and is explicitly flagged as NOT a trigger input
    (``batch_ref_used_for_trigger = false``); the causal reference actually used by a
    reference-relative policy is ``causal_reference`` / ``causal_reference_kind``."""
    entry = outcome.entry_tick
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        "observe_only": True,
        "places_orders": False,
        "config_fingerprint": config.fingerprint(),
        "feed_eligibility_policy_version": (
            feed_policy_version or FEED_ELIGIBILITY_POLICY_VERSION
        ),
        "date": name.date,
        "ticker": name.ticker,
        "side": name.side,
        "signal_version": name.signal_version,
        "policy": outcome.policy,
        "policy_params": config.policy_params(outcome.policy),
        "eligible": bool(outcome.eligible),
        "entry_tick_time": entry.tick_time if entry else None,
        "entry_ref_quote": entry.mid if entry else None,
        "entry_quote": entry.quote() if entry else None,
        # Causal, known-as-of reference a reference-relative policy triggered on.
        "causal_reference": outcome.reference,
        "causal_reference_kind": outcome.reference_kind,
        "prior_close_ref": prior_close_ref,
        # Provenance ONLY — the next-open batch reference is not known at the decision
        # instant and is NEVER used to trigger an online entry (look-ahead guard).
        "batch_ref": batch_ref,
        "batch_ref_used_for_trigger": False,
        "censored_reason": outcome.censored_reason,
    }


def evaluate_name(
    name: AdmittedName,
    ticks: Sequence[Tick],
    *,
    config: EntryTimingConfig = DEFAULT_CONFIG,
    prior_close_ref: float | None = None,
    batch_ref: float | None = None,
) -> list[dict[str, Any]]:
    """Evaluate ALL pre-registered policies for one admitted name over its already
    normalized (eligible, causal, in-session, fresh) tick series. One row per policy.

    The §11b entry window scales to the calendar-resolved session bounds stamped on
    the ticks (no hard-coded clock). ``prior_close_ref`` (a frozen daily level, known
    pre-market) is the causal reference for ``pullback_to_ref``; ``batch_ref`` (the
    next-open batch reference) is recorded for provenance only and never triggers."""
    first_eligible, last_eligible, session_open = _entry_window(ticks, config)
    conviction = _parse_dt(name.conviction_time) if name.conviction_time else None
    feed_policy_version = next(
        (t.feed_policy_version for t in ticks if t.feed_policy_version), None
    )
    rows: list[dict[str, Any]] = []
    for policy in config.policies:
        func = POLICY_FUNCS[policy]
        outcome = func(
            ticks,
            first_eligible=first_eligible,
            last_eligible=last_eligible,
            session_open=session_open,
            conviction=conviction,
            config=config,
            causal_ref=prior_close_ref,
        )
        rows.append(
            build_record(
                name=name,
                outcome=outcome,
                config=config,
                prior_close_ref=prior_close_ref,
                batch_ref=batch_ref,
                feed_policy_version=feed_policy_version,
            )
        )
    return rows


def evaluate_session(
    admitted: Iterable[AdmittedName],
    tick_records: Iterable[Mapping[str, Any]],
    *,
    config: EntryTimingConfig = DEFAULT_CONFIG,
    prior_close_refs: Mapping[str, float] | None = None,
    batch_refs: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate every admitted name × every pre-registered policy for one session.

    ``tick_records`` is the raw #216 eligible feed (already limited to the session,
    or a superset — it is filtered + re-certified per name). ``prior_close_refs``
    optionally maps ticker → the frozen daily level (prior close) used as the CAUSAL
    ``pullback_to_ref`` reference. ``batch_refs`` (next-open batch reference) is
    recorded as provenance only and never triggers. Returns all rows; writes nothing
    (caller appends)."""
    prior_close_refs = prior_close_refs or {}
    batch_refs = batch_refs or {}
    records = list(tick_records)
    rows: list[dict[str, Any]] = []
    for name in admitted:
        ticks = normalize_ticks(records, ticker=name.ticker, date=name.date, config=config)
        rows.extend(
            evaluate_name(
                name,
                ticks,
                config=config,
                prior_close_ref=prior_close_refs.get(name.ticker),
                batch_ref=batch_refs.get(name.ticker),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Diagnostics summary (counts only — NO verdict, comparison, or bps claim)
# ---------------------------------------------------------------------------
def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Operational counts over the rows. Reports NO between-arm comparison, entry
    price, shortfall, or verdict — Stage 1 renders no execution-quality claim (§9.3)."""
    per_policy: dict[str, dict[str, Any]] = {}
    for r in records:
        policy = str(r.get("policy"))
        bucket = per_policy.setdefault(
            policy, {"n": 0, "n_eligible": 0, "n_censored": 0, "censored_by_reason": {}}
        )
        bucket["n"] += 1
        if r.get("eligible"):
            bucket["n_eligible"] += 1
        else:
            bucket["n_censored"] += 1
            reason = str(r.get("censored_reason"))
            reasons = bucket["censored_by_reason"]
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "n_rows": len(records),
        "n_names": len({(r.get("date"), r.get("ticker")) for r in records}),
        "per_policy": per_policy,
    }


# ---------------------------------------------------------------------------
# Idempotent JSONL accumulation
# ---------------------------------------------------------------------------
def record_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Idempotency key = one row per (session, ticker, policy). Re-running a session
    is a no-op, never a duplicate."""
    return (
        str(record.get("date")),
        str(record.get("ticker")),
        str(record.get("policy")),
    )


def existing_keys(path: str | Path) -> set[tuple[str, str, str]]:
    """Keys already present in the pilot file (empty if absent). Malformed lines are
    skipped so a partially-written file never blocks append."""
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
                keys.add(record_key(json.loads(line)))
            except (json.JSONDecodeError, AttributeError):
                continue
    return keys


def append_records(path: str | Path, records: Iterable[Mapping[str, Any]]) -> int:
    """Append rows to the accumulating pilot JSONL, skipping any whose key is already
    present (idempotent). Creates parent dirs. Returns the count of NEW rows."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_keys(p)
    written = 0
    with p.open("a", encoding="utf-8") as fh:
        for r in records:
            key = record_key(r)
            if key in seen:
                continue
            fh.write(json.dumps(r, sort_keys=True) + "\n")
            seen.add(key)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Thin read-only loaders (parameterized paths — never hard-code live state)
# ---------------------------------------------------------------------------
def load_tick_records(path: str | Path, date: str) -> list[dict[str, Any]]:
    """Load the #216 ``intraday_ticks.jsonl`` rows for one session (filtered by
    ``date``). A missing file yields ``[]`` (every policy then censors — the honest
    Stage-1 state until the feed lands). Never re-collects; only reads."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("date") == date and "ticker" in obj:
                out.append(obj)
    return out


def load_admitted_from_json(path: str | Path) -> list[AdmittedName]:
    """Load admitted names from a small JSON file — a list of objects with ``date``
    /``ticker`` (+ optional ``side``/``signal_version``/``conviction_time``). Keeps
    the CLI decoupled from the run DB (the paired-IS harness #215 owns the DB read)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        AdmittedName(
            date=str(obj["date"]),
            ticker=str(obj["ticker"]),
            side=str(obj.get("side", "buy")),
            signal_version=(str(obj["signal_version"]) if obj.get("signal_version") else None),
            conviction_time=(str(obj["conviction_time"]) if obj.get("conviction_time") else None),
        )
        for obj in data
    ]


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY; --dry-run / --json summary
# ---------------------------------------------------------------------------
def collect(
    *,
    date: str,
    tick_source: str | Path,
    admitted: Sequence[AdmittedName] | None = None,
    tickers: Sequence[str] | None = None,
    prior_close_refs: Mapping[str, float] | None = None,
    batch_refs: Mapping[str, float] | None = None,
    config: EntryTimingConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """Read-only end-to-end evaluation for a session: load the #216 tick feed and
    evaluate every admitted name × pre-registered policy. Places nothing, writes
    nothing. ``admitted`` wins; else ``tickers`` are treated as admitted buys; else
    every ticker present in the feed for the date is evaluated (observe-only over
    whatever was collected)."""
    records = load_tick_records(tick_source, date)
    if admitted is None:
        if tickers is None:
            tickers = sorted({str(r["ticker"]) for r in records if r.get("ticker")})
        admitted = [AdmittedName(date=date, ticker=t) for t in tickers]
    return evaluate_session(
        admitted,
        records,
        config=config,
        prior_close_refs=prior_close_refs,
        batch_refs=batch_refs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="entry-timing-shadow",
        description=(
            "renquant105 Stage-1 OBSERVE-ONLY entry-timing shadow evaluator. Replays "
            "PRE-REGISTERED candidate entry-timing policies against the intraday tick "
            "feed and logs what each WOULD have chosen. Places no orders; renders no "
            "fill-quality verdict."
        ),
    )
    parser.add_argument(
        "--print-preregistration",
        action="store_true",
        help="print the frozen pre-registered policy set + params + design (JSON) and exit; observe-only",
    )
    parser.add_argument("--date", help="session date YYYY-MM-DD")
    parser.add_argument(
        "--tick-source",
        default=str(DEFAULT_TICK_SOURCE),
        help="the #216 intraday_ticks.jsonl feed (read-only; may be absent)",
    )
    parser.add_argument(
        "--admitted-json",
        default=None,
        help="JSON list of admitted names (date/ticker[/side/signal_version/conviction_time])",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="comma-separated admitted tickers (used when --admitted-json is absent)",
    )
    parser.add_argument(
        "--prior-close-refs-json",
        default=None,
        help="JSON object {ticker: prior_close_price} — the CAUSAL pullback_to_ref reference",
    )
    parser.add_argument(
        "--batch-refs-json",
        default=None,
        help="JSON object {ticker: next_open_batch_reference} — provenance ONLY, never a trigger",
    )
    parser.add_argument(
        "--out",
        default=str(default_pilot_path()),
        help="accumulating pilot JSONL (append, idempotent)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="compute + summarize only; write nothing"
    )
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = parser.parse_args(argv)

    if args.print_preregistration:
        print(json.dumps(preregistration_manifest(), sort_keys=True, indent=2))
        return 0
    if not args.date:
        parser.error("--date is required (unless --print-preregistration)")

    admitted: list[AdmittedName] | None = None
    if args.admitted_json:
        admitted = load_admitted_from_json(args.admitted_json)
    tickers = (
        [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None
    )
    prior_close_refs = (
        {str(k): float(v) for k, v in json.loads(Path(args.prior_close_refs_json).read_text()).items()}
        if args.prior_close_refs_json
        else None
    )
    batch_refs = (
        {str(k): float(v) for k, v in json.loads(Path(args.batch_refs_json).read_text()).items()}
        if args.batch_refs_json
        else None
    )

    records = collect(
        date=args.date,
        tick_source=args.tick_source,
        admitted=admitted,
        tickers=tickers,
        prior_close_refs=prior_close_refs,
        batch_refs=batch_refs,
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
        "config_fingerprint": DEFAULT_CONFIG.fingerprint(),
        **summary,
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(f"[OBSERVE-ONLY] renquant105 Stage-1 entry-timing shadow — {args.date}")
        print(f"  mode                : {summary['mode']}")
        print(f"  names               : {summary['n_names']}")
        print(f"  rows                : {summary['n_rows']}")
        for policy, b in sorted(summary["per_policy"].items()):
            print(f"  {policy:<30}: eligible={b['n_eligible']} censored={b['n_censored']}")
        if not args.dry_run:
            print(f"  rows written        : {written} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
