"""renquant105 ENTRY-TIMING POLICY module — SHADOW-EVALUATED ONLY (sprint D2).

The code half of harvesting the measured open-gap entry leak (S10 memo
``doc/research/2026-07-02-s10-open-auction-is.md``: fills ARE the open auction;
the true-VWAP cohort's +80bps point estimate is suggestive but INCONCLUSIVE at
10 days — hence shadow evidence first, live wiring later). Design note:
``doc/design/2026-07-03-entry-timing-policy.md``. Architecture: RFC #208
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``
§5.3 (entry-timing policy), §11b (entry windows), §12 Stage 2.

Three surfaces, all shadow:

1. **A pure policy-decision function** (:func:`decide`): given a frozen daily
   entry intent for one name, the session clock, the live quote context, and
   the config, return SUBMIT-NOW vs WAIT for each policy in a small,
   pre-declared family:

   * ``baseline_open_delay`` — submit at the first eligible tick after the
     intent arrives (open + entry_open_delay). This IS the current shadow
     pipeline behavior — the control.
   * ``delay_fixed`` — submit at ``open + delay_minutes`` (configurable T).
   * ``gap_reversion_trigger`` — for a gap-UP open, submit when the mid
     retraces ``retrace_frac`` of the opening gap (trigger =
     ``open_print − retrace_frac × (open_print − prior_close)``); gap-down or
     no-gap opens submit immediately (pre-declared: the leak being harvested
     is the inflated gap-up open, per the S10 pivot).
   * ``vwap_chase`` — **explicitly OUT OF SCOPE** (needs order slicing;
     Stage 2+). Declared so nobody re-invents it ad hoc; selecting it in
     config is a config error that falls back to baseline.

   **Every policy has a HARD deadline** (default = the §11b entry cutoff,
   ``close − entry_close_cutoff``) after which it degrades to SUBMIT-NOW —
   participation is never sacrificed silently; the degradation is recorded on
   the row (``degraded: true`` + reason). The degradation fires on the last
   tick that can still act: ``now + tick_seconds > deadline``.

2. **Shadow evaluation** (:class:`ShadowEntryTimingEvaluator`) — the DEFAULT
   and ONLY wired mode. It runs inside the shadow session scheduler's tick
   loop (the :mod:`.intraday_session_scheduler` ``tick_observer`` seam),
   consumes each persisted shadow tick record (intents + class-D per-tick
   mids), and logs WHAT EACH POLICY WOULD HAVE DONE plus the realized
   counterfactual cost vs the baseline (same tick feed, mid-as-fill) to the
   schema-versioned JSONL ``logs/renquant105_pilot/entry_timing_policy_shadow
   .jsonl``. It places NO orders, delays NO exit (non-buy intents are never
   waited), and mutates NO decision state — an evaluator exception never
   halts the decision loop (the scheduler counts it and continues). **NO live
   wiring exists in this module; the live consumer is a separate Stage-2
   decision per RFC #208 §9.3a.**

3. **The comparison-report CLI** (``report``) — aggregates the shadow log
   into per-policy cost distributions (mean/median bps saved vs baseline,
   participation rate, degradation count): the parameter-tuning surface.
   Picking the policy + params later = reading this report against the
   pre-registered selection protocol in the design note. A ``replay``
   subcommand re-runs the evaluator over a persisted shadow decision log
   (same code path as in-loop) so already-collected sessions backfill the
   corpus.

Counterfactual method (pre-declared): all policies are priced on the SAME
class-D mid series the shadow loop observed (``inputs.live_state.prices``),
mid-as-fill with zero modeled slippage — consistent with the
``entry_timing_shadow`` collector's frozen
``arrival_mid_reference__zero_modeled_shortfall`` fill model. ``saved bps`` =
``(baseline_mid − policy_mid) / baseline_mid × 1e4`` for buys (positive =
policy entered cheaper than the control). No shortfall vs broker fills is
claimed — there are no fills; this is a between-policy timing differential on
one feed, exactly the evidence the §9.4 experiment needs.

Config: ``intraday_decisioning.entry_timing.{policy, delay_minutes,
retrace_frac, min_gap_bps, deadline_minutes_before_cutoff,
prior_close_refs_path, shadow_log}`` in the pinned strategy config. Safe
defaults; an absent section ⇒ baseline selected (and shadow evaluation still
runs — it is free and is the point). Malformed values are collected into
``config_errors`` and defaulted, and force the selected policy back to
baseline — a typo can never select a non-control policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .runtime_paths import default_data_root

log = logging.getLogger("renquant.entry_timing_policy")

ET = ZoneInfo("America/New_York")

#: Schema version of the policy-shadow JSONL rows — bump on shape changes so
#: the §9.4 experiment can migrate cleanly.
SCHEMA_VERSION = "rq105-entry-timing-policy-v1"
RECORD_KIND = "entry_timing_policy_shadow"
STAGE = "renquant105-stage1-operations-only"

#: The pre-declared policy family (frozen names).
POLICY_BASELINE = "baseline_open_delay"
POLICY_DELAY_FIXED = "delay_fixed"
POLICY_REVERSION = "gap_reversion_trigger"
POLICY_VWAP_CHASE = "vwap_chase"

#: Policies the shadow evaluator actually runs (baseline FIRST — it is the
#: control every other policy's counterfactual cost is anchored on).
EVALUATED_POLICIES = (POLICY_BASELINE, POLICY_DELAY_FIXED, POLICY_REVERSION)

#: Declared but explicitly NOT implemented (needs order slicing — Stage 2+).
OUT_OF_SCOPE_POLICIES = (POLICY_VWAP_CHASE,)

ACTION_SUBMIT_NOW = "submit_now"
ACTION_WAIT = "wait"

# Decision reasons (frozen strings — they appear in the schema-versioned log).
REASON_WINDOW_NOT_OPEN = "entry_window_not_open"
REASON_WINDOW_CLOSED = "entry_window_closed"
REASON_BASELINE = "baseline_submit_at_open_delay"
REASON_DELAY_ELAPSED = "fixed_delay_elapsed"
REASON_WAITING_DELAY = "waiting_fixed_delay"
REASON_RETRACE_HIT = "gap_retrace_trigger_hit"
REASON_WAITING_RETRACE = "awaiting_gap_retrace"
REASON_GAP_DOWN = "gap_down_submit_now"
REASON_NO_GAP = "no_gap_submit_now"
REASON_MISSING_REF = "missing_gap_reference_submit_now"
REASON_DEADLINE = "hard_deadline_degraded_submit_now"
REASON_NON_BUY = "non_buy_never_delayed"

#: Censoring reasons (a row is written for every (session, name, policy) —
#: an unresolved cell is recorded by cause, never imputed or dropped).
CENSOR_UNRESOLVED_AT_FLUSH = "unresolved_at_flush"


def default_policy_shadow_log_path(data_root: Path | None = None) -> Path:
    """The accumulating policy-shadow JSONL, beside the other 105 pilot logs.

    Rooted at :func:`default_data_root` (honors ``RENQUANT_DATA_ROOT``) —
    NEVER the umbrella git tree."""
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "entry_timing_policy_shadow.jsonl"


# ---------------------------------------------------------------------------
# Config — intraday_decisioning.entry_timing.{...}; absent => baseline.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntryTimingPolicyConfig:
    """The ``intraday_decisioning.entry_timing`` section (safe defaults).

    ``policy`` is the SELECTED policy — informational in shadow mode (the
    evaluator always runs the whole family) and the value a future Stage-2
    live consumer would read. Absent section or any malformed value ⇒
    baseline (fail-safe to the control, never to an experiment)."""

    policy: str = POLICY_BASELINE
    delay_minutes: float = 30.0
    retrace_frac: float = 0.5
    min_gap_bps: float = 10.0
    deadline_minutes_before_cutoff: float = 0.0
    prior_close_refs_path: str | None = None
    shadow_log: str | None = None
    config_errors: tuple[str, ...] = ()

    def policy_params(self, policy: str) -> dict[str, Any]:
        """The frozen parameters governing one policy (recorded per row)."""
        common = {
            "deadline_minutes_before_cutoff": self.deadline_minutes_before_cutoff,
        }
        if policy == POLICY_DELAY_FIXED:
            return {**common, "delay_minutes": self.delay_minutes}
        if policy == POLICY_REVERSION:
            return {
                **common,
                "retrace_frac": self.retrace_frac,
                "min_gap_bps": self.min_gap_bps,
            }
        return common

    def fingerprint(self) -> str:
        """Stable short hash pinning every row to this exact parameterization."""
        payload = {
            "policy": self.policy,
            "delay_minutes": self.delay_minutes,
            "retrace_frac": self.retrace_frac,
            "min_gap_bps": self.min_gap_bps,
            "deadline_minutes_before_cutoff": self.deadline_minutes_before_cutoff,
            "evaluated_policies": list(EVALUATED_POLICIES),
            "schema_version": SCHEMA_VERSION,
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


def load_entry_timing_config(
    strategy_config: Mapping[str, Any],
) -> EntryTimingPolicyConfig:
    """Read ``intraday_decisioning.entry_timing`` from the pinned config.

    Absent section ⇒ all defaults (selected policy = baseline). Malformed
    values are collected into ``config_errors``, defaulted, AND force
    ``policy`` back to baseline — a typo can never select a non-control
    policy. Selecting an out-of-scope policy (``vwap_chase``) is a config
    error, not a silent acceptance."""
    section = ((strategy_config or {}).get("intraday_decisioning") or {})
    if not isinstance(section, Mapping):
        return EntryTimingPolicyConfig(
            config_errors=("intraday_decisioning is not a mapping",)
        )
    raw = section.get("entry_timing")
    if raw is None:
        return EntryTimingPolicyConfig()
    if not isinstance(raw, Mapping):
        return EntryTimingPolicyConfig(
            config_errors=("intraday_decisioning.entry_timing is not a mapping",)
        )
    errors: list[str] = []

    def _number(key: str, default: float, *, minimum: float | None = None,
                maximum: float | None = None) -> float:
        value_raw = raw.get(key, default)
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            errors.append(f"{key} is not a number: {value_raw!r}")
            return default
        if minimum is not None and value < minimum:
            errors.append(f"{key} must be >= {minimum}: {value_raw!r}")
            return default
        if maximum is not None and value > maximum:
            errors.append(f"{key} must be <= {maximum}: {value_raw!r}")
            return default
        return value

    policy = str(raw.get("policy", POLICY_BASELINE) or POLICY_BASELINE)
    if policy in OUT_OF_SCOPE_POLICIES:
        errors.append(
            f"policy {policy!r} is explicitly OUT OF SCOPE (needs order "
            "slicing, Stage 2+) — falling back to baseline"
        )
        policy = POLICY_BASELINE
    elif policy not in EVALUATED_POLICIES:
        errors.append(f"unknown policy {policy!r} — falling back to baseline")
        policy = POLICY_BASELINE

    delay_minutes = _number("delay_minutes", 30.0, minimum=0.0)
    retrace_frac = _number("retrace_frac", 0.5, minimum=0.0, maximum=1.0)
    min_gap_bps = _number("min_gap_bps", 10.0, minimum=0.0)
    deadline_min = _number("deadline_minutes_before_cutoff", 0.0, minimum=0.0)

    prior_raw = raw.get("prior_close_refs_path")
    prior_path = str(prior_raw) if prior_raw else None
    log_raw = raw.get("shadow_log")
    log_path = str(log_raw) if log_raw else None

    if errors:
        policy = POLICY_BASELINE  # any config error => fail-safe to the control
    return EntryTimingPolicyConfig(
        policy=policy,
        delay_minutes=delay_minutes,
        retrace_frac=retrace_frac,
        min_gap_bps=min_gap_bps,
        deadline_minutes_before_cutoff=deadline_min,
        prior_close_refs_path=prior_path,
        shadow_log=log_path,
        config_errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Pure decision inputs / output.
# ---------------------------------------------------------------------------
def _parse_dt(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ET)
    return dt


@dataclass(frozen=True)
class EntryIntent:
    """One frozen daily entry intent for one name (the class-A decision).

    ``arrival_time`` = the first shadow tick on which the pipeline emitted the
    intent (nothing can submit earlier). ``prior_close`` is the frozen daily
    reference (known pre-market) the gap is measured against; ``None`` when no
    provider is wired — the reversion policy then degrades to submit-now with
    an explicit reason, never guesses."""

    ticker: str
    trading_day: str
    arrival_time: datetime
    side: str = "buy"
    parent_intent_id: str = ""
    signal_version: str | None = None
    prior_close: float | None = None


@dataclass(frozen=True)
class SessionClock:
    """The session clock a decision is made against (§11b, calendar-resolved).

    ``tick_seconds`` is the loop cadence — the deadline degradation fires on
    the last tick that can still act (``now + tick_seconds > deadline``)."""

    open: datetime
    first_eligible: datetime
    entry_cutoff: datetime
    close: datetime
    tick_seconds: float = 720.0

    @classmethod
    def from_windows_record(
        cls, windows: Mapping[str, Any], *, tick_seconds: float = 720.0
    ) -> "SessionClock":
        """Build from a scheduler tick record's ``windows`` stamp (ISO strings)."""
        return cls(
            open=_parse_dt(windows["open"]),
            first_eligible=_parse_dt(windows["first_eligible_tick"]),
            entry_cutoff=_parse_dt(windows["entry_cutoff"]),
            close=_parse_dt(windows["close"]),
            tick_seconds=float(tick_seconds),
        )

    def hard_deadline(self, config: EntryTimingPolicyConfig) -> datetime:
        """The HARD deadline (default = the §11b entry cutoff): at/after it a
        still-waiting policy degrades to submit-now."""
        return self.entry_cutoff - timedelta(
            minutes=config.deadline_minutes_before_cutoff
        )


@dataclass(frozen=True)
class QuoteContext:
    """The live class-D quote context at one tick for one name.

    ``mid`` — this tick's mid (``None`` = unpriced tick, cannot trigger);
    ``open_print`` — the first observed in-session mid for the name (the same
    causal opening-print convention as ``entry_timing_shadow``)."""

    now: datetime
    mid: float | None = None
    open_print: float | None = None


@dataclass(frozen=True)
class PolicyDecision:
    """SUBMIT-NOW vs WAIT, with full provenance for the shadow row."""

    policy: str
    action: str
    reason: str
    degraded: bool = False
    trigger_price: float | None = None
    gap_bps: float | None = None
    deadline: datetime | None = None


def _natural_decision(
    policy: str,
    *,
    intent: EntryIntent,
    clock: SessionClock,
    quote: QuoteContext,
    config: EntryTimingPolicyConfig,
) -> PolicyDecision:
    """The policy's own trigger logic, BEFORE the deadline override."""
    if policy == POLICY_BASELINE:
        # The control: submit at the first eligible tick after arrival.
        return PolicyDecision(policy, ACTION_SUBMIT_NOW, REASON_BASELINE)

    if policy == POLICY_DELAY_FIXED:
        target = clock.open + timedelta(minutes=config.delay_minutes)
        if quote.now >= target:
            return PolicyDecision(policy, ACTION_SUBMIT_NOW, REASON_DELAY_ELAPSED)
        return PolicyDecision(policy, ACTION_WAIT, REASON_WAITING_DELAY)

    if policy == POLICY_REVERSION:
        prior = intent.prior_close
        open_print = quote.open_print
        if prior is None or open_print is None or prior <= 0:
            # Missing reference: fail toward participation (= baseline), and
            # say so — never guess a gap.
            return PolicyDecision(
                policy, ACTION_SUBMIT_NOW, REASON_MISSING_REF, degraded=True
            )
        gap_bps = (open_print - prior) / prior * 1e4
        if abs(gap_bps) < config.min_gap_bps:
            return PolicyDecision(
                policy, ACTION_SUBMIT_NOW, REASON_NO_GAP, gap_bps=gap_bps
            )
        if gap_bps < 0:
            # Gap-down open: for a buy the open is already the cheap print
            # (the measured leak is the inflated gap-UP open) — submit now.
            return PolicyDecision(
                policy, ACTION_SUBMIT_NOW, REASON_GAP_DOWN, gap_bps=gap_bps
            )
        trigger = open_print - config.retrace_frac * (open_print - prior)
        if quote.mid is not None and quote.mid <= trigger:
            return PolicyDecision(
                policy,
                ACTION_SUBMIT_NOW,
                REASON_RETRACE_HIT,
                trigger_price=trigger,
                gap_bps=gap_bps,
            )
        return PolicyDecision(
            policy,
            ACTION_WAIT,
            REASON_WAITING_RETRACE,
            trigger_price=trigger,
            gap_bps=gap_bps,
        )

    if policy in OUT_OF_SCOPE_POLICIES:
        raise ValueError(
            f"policy {policy!r} is explicitly out of scope (order slicing, "
            "Stage 2+) — it must never be evaluated"
        )
    raise ValueError(f"unknown entry-timing policy: {policy!r}")


def decide(
    policy: str,
    *,
    intent: EntryIntent,
    clock: SessionClock,
    quote: QuoteContext,
    config: EntryTimingPolicyConfig,
) -> PolicyDecision:
    """PURE policy decision: SUBMIT-NOW vs WAIT for one (name, policy, tick).

    Ordering of the guards (pre-declared):

    1. non-buy intents are NEVER delayed (exits-always-allowed, §10);
    2. before the entry window opens / before the intent arrives → WAIT;
    3. at/after the entry cutoff → WAIT with ``entry_window_closed`` (the
       evaluator records the cell censored; with live ticks this state is
       unreachable because rule 4 fires first);
    4. HARD-DEADLINE DEGRADATION: if the policy's own logic says WAIT but
       waiting one more tick would reach or cross the hard deadline
       (``now + tick_seconds >= deadline`` — a tick AT the deadline can no
       longer act when the deadline is the entry cutoff), degrade to
       SUBMIT-NOW with ``degraded=true`` — participation is never sacrificed
       silently;
    5. otherwise the policy's own trigger logic decides.
    """
    if str(intent.side).lower() != "buy":
        return PolicyDecision(policy, ACTION_SUBMIT_NOW, REASON_NON_BUY)
    deadline = clock.hard_deadline(config)
    if quote.now < clock.first_eligible or quote.now < intent.arrival_time:
        return PolicyDecision(
            policy, ACTION_WAIT, REASON_WINDOW_NOT_OPEN, deadline=deadline
        )
    if quote.now >= clock.entry_cutoff:
        return PolicyDecision(
            policy, ACTION_WAIT, REASON_WINDOW_CLOSED, deadline=deadline
        )
    natural = _natural_decision(
        policy, intent=intent, clock=clock, quote=quote, config=config
    )
    if natural.action == ACTION_WAIT and (
        quote.now + timedelta(seconds=clock.tick_seconds) >= deadline
    ):
        return PolicyDecision(
            policy,
            ACTION_SUBMIT_NOW,
            REASON_DEADLINE,
            degraded=True,
            trigger_price=natural.trigger_price,
            gap_bps=natural.gap_bps,
            deadline=deadline,
        )
    return PolicyDecision(
        policy,
        natural.action,
        natural.reason,
        degraded=natural.degraded,
        trigger_price=natural.trigger_price,
        gap_bps=natural.gap_bps,
        deadline=deadline,
    )


# ---------------------------------------------------------------------------
# Shadow evaluation — consumes the scheduler's tick-observer seam.
# ---------------------------------------------------------------------------
@dataclass
class _Resolution:
    tick_time: str
    entry_mid: float | None
    degraded: bool
    reason: str
    trigger_price: float | None
    gap_bps: float | None
    deadline: str | None


@dataclass
class _NameState:
    intent: EntryIntent
    resolutions: dict[str, _Resolution] = field(default_factory=dict)
    written: set[str] = field(default_factory=set)


def record_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Idempotency key: one row per (session, ticker, policy)."""
    return (
        str(record.get("session_date")),
        str(record.get("ticker")),
        str(record.get("policy")),
    )


def existing_keys(path: str | Path) -> set[tuple[str, str, str]]:
    """Keys already in the shadow log (empty if absent); malformed lines are
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


class ShadowEntryTimingEvaluator:
    """Runs the pre-declared policy family in shadow inside the scheduler's
    tick loop, and logs per-policy virtual entries + counterfactual costs.

    Consumes the persisted shadow tick records via the scheduler's
    ``tick_observer`` seam (:mod:`.intraday_session_scheduler`): entry intents
    from ``decisions.intents`` (kind ``entry``, side ``BUY`` — exits are never
    tracked, never delayed), per-tick mids from ``inputs.live_state.prices``,
    and the §11b windows from the record's ``windows`` stamp. Observe-only:
    it writes ONLY its own JSONL and never touches the decision payload.

    Rows are written as each policy resolves (baseline resolves first — it is
    evaluated first and submits at the arrival tick), idempotently keyed on
    ``(session_date, ticker, policy)``; unresolved cells are written censored
    by :meth:`flush` (recorded by cause, never imputed).
    """

    def __init__(
        self,
        *,
        config: EntryTimingPolicyConfig,
        log_path: str | Path | None = None,
        prior_close_refs: Mapping[str, float] | None = None,
        tick_seconds: float = 720.0,
        windows: Mapping[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.log_path = Path(log_path) if log_path else default_policy_shadow_log_path()
        self.prior_close_refs = {
            str(k).upper(): float(v) for k, v in (prior_close_refs or {}).items()
        }
        self.tick_seconds = float(tick_seconds)
        self._fallback_windows = dict(windows) if windows else None
        self._clocks: dict[str, SessionClock] = {}
        self._names: dict[tuple[str, str], _NameState] = {}
        self._open_prints: dict[tuple[str, str], float] = {}
        self._seen_keys = existing_keys(self.log_path)
        self.rows_written = 0
        self.ticks_seen = 0
        self.ticks_without_windows = 0

    # -- seam entry point ---------------------------------------------------
    def on_tick(self, record: Mapping[str, Any]) -> None:
        """Consume one persisted shadow tick record (the scheduler seam)."""
        self.ticks_seen += 1
        session_date = str(record.get("session_date"))
        clock = self._clocks.get(session_date)
        if clock is None:
            windows = record.get("windows") or self._fallback_windows
            if not windows:
                self.ticks_without_windows += 1
                return  # cannot do §11b/deadline math without the window stamp
            clock = SessionClock.from_windows_record(
                windows, tick_seconds=self.tick_seconds
            )
            self._clocks[session_date] = clock
        now = _parse_dt(str(record.get("tick_at")))
        inputs = record.get("inputs") or {}
        live_state = inputs.get("live_state") or {}
        prices: dict[str, float] = {}
        for tkr, px in (live_state.get("prices") or {}).items():
            try:
                value = float(px)
            except (TypeError, ValueError):
                continue
            if value > 0:
                prices[str(tkr).upper()] = value
        # Opening prints: first observed in-session mid per name (causal).
        for tkr, px in prices.items():
            self._open_prints.setdefault((session_date, tkr), px)
        # Register newly-arrived BUY entry intents (frozen daily intents).
        decisions = record.get("decisions") or {}
        for intent in decisions.get("intents") or ():
            if str(intent.get("kind", "")).lower() != "entry":
                continue
            if str(intent.get("side", "")).upper() != "BUY":
                continue
            ticker = str(intent.get("symbol", "")).upper()
            if not ticker:
                continue
            key = (session_date, ticker)
            if key in self._names:
                continue
            self._names[key] = _NameState(
                intent=EntryIntent(
                    ticker=ticker,
                    trading_day=session_date,
                    arrival_time=now,
                    side="buy",
                    parent_intent_id=str(intent.get("parent_intent_id", "")),
                    signal_version=(
                        str(intent["signal_version"])
                        if intent.get("signal_version")
                        else None
                    ),
                    prior_close=self.prior_close_refs.get(ticker),
                )
            )
        # Evaluate every unresolved (name, policy) on this tick.
        for (day, ticker), state in self._names.items():
            if day != session_date:
                continue
            quote = QuoteContext(
                now=now,
                mid=prices.get(ticker),
                open_print=self._open_prints.get((day, ticker)),
            )
            for policy in EVALUATED_POLICIES:
                if policy in state.resolutions:
                    continue
                decision = decide(
                    policy,
                    intent=state.intent,
                    clock=clock,
                    quote=quote,
                    config=self.config,
                )
                if decision.action != ACTION_SUBMIT_NOW:
                    continue
                state.resolutions[policy] = _Resolution(
                    tick_time=now.isoformat(),
                    entry_mid=quote.mid,
                    degraded=decision.degraded,
                    reason=decision.reason,
                    trigger_price=decision.trigger_price,
                    gap_bps=decision.gap_bps,
                    deadline=(
                        decision.deadline.isoformat() if decision.deadline else None
                    ),
                )
                self._write_resolved(day, ticker, state, policy)

    # -- row building ---------------------------------------------------------
    def _base_row(self, day: str, ticker: str, state: _NameState, policy: str) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": RECORD_KIND,
            "stage": STAGE,
            "mode": "shadow",
            "observe_only": True,
            "places_orders": False,
            "session_date": day,
            "ticker": ticker,
            "side": "BUY",
            "parent_intent_id": state.intent.parent_intent_id,
            "signal_version": state.intent.signal_version,
            "policy": policy,
            "selected_policy": self.config.policy,
            "policy_params": self.config.policy_params(policy),
            "config_fingerprint": self.config.fingerprint(),
            "arrival_tick_time": state.intent.arrival_time.isoformat(),
            "prior_close_ref": state.intent.prior_close,
            "open_print": self._open_prints.get((day, ticker)),
        }

    def _write_resolved(self, day: str, ticker: str, state: _NameState, policy: str) -> None:
        """Write the row for a resolved (name, policy) once the baseline
        anchor is available (baseline is evaluated first, so it always is by
        the time any policy resolves on the same or a later tick)."""
        if policy in state.written:
            return
        res = state.resolutions[policy]
        base = state.resolutions.get(POLICY_BASELINE)
        saved_bps: float | None = None
        if (
            base is not None
            and base.entry_mid is not None
            and res.entry_mid is not None
            and base.entry_mid > 0
        ):
            saved_bps = (base.entry_mid - res.entry_mid) / base.entry_mid * 1e4
        row = {
            **self._base_row(day, ticker, state, policy),
            "participated": True,
            "action": ACTION_SUBMIT_NOW,
            "decided_tick_time": res.tick_time,
            "virtual_entry_mid": res.entry_mid,
            "degraded": res.degraded,
            "reason": res.reason,
            "trigger_price": res.trigger_price,
            "gap_bps": res.gap_bps,
            "deadline": res.deadline,
            "baseline_entry_mid": base.entry_mid if base else None,
            "baseline_tick_time": base.tick_time if base else None,
            "saved_vs_baseline_bps": saved_bps,
            "censored_reason": None,
        }
        if self._append(row):
            state.written.add(policy)

    def flush(self, reason: str = CENSOR_UNRESOLVED_AT_FLUSH) -> int:
        """Write censored rows for every still-unresolved (name, policy).

        With live ticks running to the entry cutoff the deadline degradation
        resolves everything; censoring here means the session halted early
        (kill switch / error) — recorded by cause, never imputed."""
        written = 0
        for (day, ticker), state in self._names.items():
            for policy in EVALUATED_POLICIES:
                if policy in state.written:
                    continue
                if policy in state.resolutions:
                    self._write_resolved(day, ticker, state, policy)
                    written += 1
                    continue
                base = state.resolutions.get(POLICY_BASELINE)
                row = {
                    **self._base_row(day, ticker, state, policy),
                    "participated": False,
                    "action": ACTION_WAIT,
                    "decided_tick_time": None,
                    "virtual_entry_mid": None,
                    "degraded": False,
                    "reason": None,
                    "trigger_price": None,
                    "gap_bps": None,
                    "deadline": None,
                    "baseline_entry_mid": base.entry_mid if base else None,
                    "baseline_tick_time": base.tick_time if base else None,
                    "saved_vs_baseline_bps": None,
                    "censored_reason": reason,
                }
                if self._append(row):
                    state.written.add(policy)
                    written += 1
        return written

    def _append(self, row: Mapping[str, Any]) -> bool:
        key = record_key(row)
        if key in self._seen_keys:
            return False
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self._seen_keys.add(key)
        self.rows_written += 1
        return True


# ---------------------------------------------------------------------------
# Comparison report — the parameter-tuning surface (counts + distributions,
# NO verdict: the pre-registered selection protocol lives in the design note).
# ---------------------------------------------------------------------------
def load_policy_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read the policy-shadow JSONL (missing file => empty corpus)."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("kind") == RECORD_KIND:
                rows.append(obj)
    return rows


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile over an already-sorted list."""
    if not sorted_values:
        raise ValueError("empty")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def summarize_policy_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-policy cost distributions vs baseline + participation/degradation.

    ``saved_vs_baseline_bps``: positive = entered cheaper than the control.
    Reports distributions and counts ONLY — no PASS/FAIL, no winner; picking
    the policy is the design note's pre-registered selection protocol."""
    per_policy: dict[str, dict[str, Any]] = {}
    sessions: set[str] = set()
    names: set[tuple[str, str]] = set()
    for r in rows:
        policy = str(r.get("policy"))
        sessions.add(str(r.get("session_date")))
        names.add((str(r.get("session_date")), str(r.get("ticker"))))
        b = per_policy.setdefault(
            policy,
            {
                "n_rows": 0,
                "n_participated": 0,
                "n_degraded": 0,
                "n_censored": 0,
                "censored_by_reason": {},
                "reasons": {},
                "_saved": [],
            },
        )
        b["n_rows"] += 1
        if r.get("participated"):
            b["n_participated"] += 1
        else:
            b["n_censored"] += 1
            reason = str(r.get("censored_reason"))
            b["censored_by_reason"][reason] = b["censored_by_reason"].get(reason, 0) + 1
        if r.get("degraded"):
            b["n_degraded"] += 1
        if r.get("reason"):
            reason = str(r.get("reason"))
            b["reasons"][reason] = b["reasons"].get(reason, 0) + 1
        saved = r.get("saved_vs_baseline_bps")
        if saved is not None:
            b["_saved"].append(float(saved))
    for b in per_policy.values():
        saved = sorted(b.pop("_saved"))
        b["participation_rate"] = (
            b["n_participated"] / b["n_rows"] if b["n_rows"] else None
        )
        b["degradation_count"] = b["n_degraded"]
        if saved:
            b["saved_vs_baseline_bps"] = {
                "n_priced": len(saved),
                "mean": sum(saved) / len(saved),
                "median": median(saved),
                "p25": _percentile(saved, 0.25),
                "p75": _percentile(saved, 0.75),
                "min": saved[0],
                "max": saved[-1],
            }
        else:
            b["saved_vs_baseline_bps"] = {"n_priced": 0}
    return {
        "schema_version": SCHEMA_VERSION,
        "n_rows": sum(b["n_rows"] for b in per_policy.values()),
        "n_sessions": len(sessions),
        "n_names": len(names),
        "per_policy": per_policy,
        "selection_protocol": "doc/design/2026-07-03-entry-timing-policy.md",
    }


def render_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "[SHADOW] entry-timing policy comparison — "
        f"{summary['n_sessions']} session(s), {summary['n_names']} name(s), "
        f"{summary['n_rows']} rows",
        "  (saved bps > 0 = cheaper than the baseline control; no verdict is",
        f"   rendered here — selection protocol: {summary['selection_protocol']})",
    ]
    for policy in sorted(summary.get("per_policy", {})):
        b = summary["per_policy"][policy]
        saved = b.get("saved_vs_baseline_bps", {})
        lines.append(f"  {policy}")
        part = b.get("participation_rate")
        lines.append(
            f"    participation : {b['n_participated']}/{b['n_rows']}"
            + (f" ({part:.0%})" if part is not None else "")
        )
        lines.append(f"    degradations  : {b['degradation_count']}")
        if saved.get("n_priced"):
            lines.append(
                "    saved vs base : "
                f"mean {saved['mean']:+.1f} bps, median {saved['median']:+.1f} bps, "
                f"p25 {saved['p25']:+.1f}, p75 {saved['p75']:+.1f} "
                f"(n={saved['n_priced']})"
            )
        else:
            lines.append("    saved vs base : no priced pairs yet")
        if b.get("n_censored"):
            lines.append(
                f"    censored      : {b['n_censored']} {b['censored_by_reason']}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Replay — re-run the evaluator over a persisted shadow decision log (the
# SAME code path as in-loop consumption; backfills already-collected sessions).
# ---------------------------------------------------------------------------
def load_shadow_tick_records(
    path: str | Path, *, date: str | None = None
) -> list[dict[str, Any]]:
    """Read scheduler shadow tick records (optionally one session)."""
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
            if obj.get("kind") != "intraday_decision_shadow_tick":
                continue
            if date is not None and obj.get("session_date") != date:
                continue
            out.append(obj)
    out.sort(key=lambda r: (str(r.get("session_date")), int(r.get("tick_index", 0))))
    return out


def replay_shadow_log(
    *,
    shadow_log: str | Path,
    out: str | Path,
    config: EntryTimingPolicyConfig,
    date: str | None = None,
    manifest: str | Path | None = None,
    prior_close_refs: Mapping[str, float] | None = None,
    tick_seconds: float = 720.0,
) -> ShadowEntryTimingEvaluator:
    """Feed a persisted shadow decision log through the evaluator (read-only
    on the input; idempotent append on the output)."""
    windows: Mapping[str, Any] | None = None
    if manifest is not None:
        payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
        windows = payload.get("windows")
    evaluator = ShadowEntryTimingEvaluator(
        config=config,
        log_path=out,
        prior_close_refs=prior_close_refs,
        tick_seconds=tick_seconds,
        windows=windows,
    )
    for record in load_shadow_tick_records(shadow_log, date=date):
        evaluator.on_tick(record)
    evaluator.flush()
    return evaluator


# ---------------------------------------------------------------------------
# CLI — report (the tuning surface) + replay (backfill). Shadow-only.
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="entry-timing-policy",
        description=(
            "renquant105 entry-timing policy module — SHADOW-EVALUATED ONLY. "
            "'report' aggregates the policy-shadow log into per-policy cost "
            "distributions vs the baseline control; 'replay' re-runs the "
            "evaluator over a persisted shadow decision log. Places nothing."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="per-policy comparison report")
    p_report.add_argument(
        "--log",
        default=str(default_policy_shadow_log_path()),
        help="policy-shadow JSONL (read-only)",
    )
    p_report.add_argument("--json", action="store_true", help="emit JSON")

    p_replay = sub.add_parser(
        "replay", help="replay a persisted shadow decision log through the evaluator"
    )
    p_replay.add_argument(
        "--shadow-log",
        required=True,
        help="scheduler intraday_decisions_shadow.jsonl (read-only)",
    )
    p_replay.add_argument("--date", default=None, help="restrict to one session date")
    p_replay.add_argument(
        "--manifest",
        default=None,
        help="session manifest JSON (supplies §11b windows for logs predating the windows stamp)",
    )
    p_replay.add_argument(
        "--prior-close-refs-json",
        default=None,
        help="JSON object {ticker: prior_close} — the gap reference",
    )
    p_replay.add_argument(
        "--strategy-config", default=None, help="pinned strategy config JSON (for entry_timing keys)"
    )
    p_replay.add_argument("--tick-seconds", type=float, default=720.0)
    p_replay.add_argument(
        "--out",
        default=str(default_policy_shadow_log_path()),
        help="policy-shadow JSONL (append, idempotent)",
    )
    p_replay.add_argument("--json", action="store_true", help="emit a JSON summary")

    args = parser.parse_args(argv)

    if args.command == "report":
        summary = summarize_policy_rows(load_policy_rows(args.log))
        if args.json:
            print(json.dumps(summary, sort_keys=True, indent=2))
        else:
            print(render_report(summary))
        return 0

    # replay
    config = EntryTimingPolicyConfig()
    if args.strategy_config:
        config = load_entry_timing_config(
            json.loads(Path(args.strategy_config).read_text(encoding="utf-8"))
        )
    prior_refs = None
    if args.prior_close_refs_json:
        prior_refs = {
            str(k): float(v)
            for k, v in json.loads(
                Path(args.prior_close_refs_json).read_text(encoding="utf-8")
            ).items()
        }
    evaluator = replay_shadow_log(
        shadow_log=args.shadow_log,
        out=args.out,
        config=config,
        date=args.date,
        manifest=args.manifest,
        prior_close_refs=prior_refs,
        tick_seconds=args.tick_seconds,
    )
    summary = {
        "mode": "shadow-replay",
        "observe_only": True,
        "ticks_seen": evaluator.ticks_seen,
        "ticks_without_windows": evaluator.ticks_without_windows,
        "rows_written": evaluator.rows_written,
        "out": str(evaluator.log_path),
        "config_fingerprint": config.fingerprint(),
        "config_errors": list(config.config_errors),
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(
            f"[SHADOW] entry-timing policy replay: ticks={summary['ticks_seen']} "
            f"rows_written={summary['rows_written']} -> {summary['out']}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
