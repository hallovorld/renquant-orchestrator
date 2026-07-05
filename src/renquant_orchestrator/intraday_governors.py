"""renquant105 intraday CADENCE + GOVERNOR module — SHADOW-EVALUATED ONLY.

Engineering infrastructure for controlling HOW OFTEN the system reacts during
a trading session and what safety limits apply. This module provides:

1. **Cadence checkpoints**: Named session checkpoints (open+30m, midday,
   power hour) that define WHEN evaluations happen, in addition to the
   fixed-interval tick cadence the session scheduler already drives.
2. **Governors**: Rate limiters / circuit breakers that prevent excessive
   intraday trading:
   - Max actions (entries + exits) per session
   - Max portfolio turnover per day (as fraction of equity)
   - Min time between actions on the same ticker (cooldown)
   - Post-loss cooldown: pause entries after a realized loss
3. **Governor evaluation**: A pure function that checks all governors before
   any intraday action intent and returns ALLOW / BLOCK with reasons.

All governor checks are SHADOW-EVALUATED: they record what WOULD have been
blocked and why, but do not enforce in production until explicitly armed.
The module is testable in isolation (pure functions, injected state, no
wall-clock, no network, no broker).

Default OFF: the ``intraday_governors`` section in the pinned strategy config
must be present and ``enabled: true`` to activate. Absent section => all
governors disabled (every intent passes). This is INDEPENDENT of the
intraday_decisioning triple gate — governors layer on TOP of the session
scheduler's own controls.

Integration point: the governor evaluator is designed to be called from the
session scheduler's ``_run_tick`` path (or the live executor) AFTER the
pipeline tick produces intents and BEFORE they are persisted / submitted.
In shadow mode, blocked intents are still logged (with ``blocked_by_governor``
reason) — the governor never suppresses shadow data, only annotates it.

Hard boundary: this module contains NO trading strategy, sizing, or signal
logic. It is pure control-plane engineering.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

log = logging.getLogger("renquant.intraday_governors")

ET = ZoneInfo("America/New_York")

SCHEMA_VERSION = "rq105-intraday-governors-v1"
RECORD_KIND = "intraday_governor_evaluation"
STAGE = "renquant105-stage1-operations-only"

# ---------------------------------------------------------------------------
# Cadence checkpoints — named session moments for evaluation scheduling
# ---------------------------------------------------------------------------
# Default checkpoint definitions: minutes from session open.
# The session scheduler's fixed tick cadence (720s = 12min) already drives
# periodic evaluation; checkpoints add NAMED evaluation windows at
# strategically important session moments. A checkpoint is "due" when the
# session clock reaches its offset AND no tick has been run in its window yet.
DEFAULT_CHECKPOINTS: tuple[tuple[str, int], ...] = (
    ("open_plus_30", 30),       # 30 min after open — auction settled, range forming
    ("midday", 180),            # 3 hours after open (~12:30 ET for regular session)
    ("power_hour", -60),        # 60 min before close — negative = from close
)


@dataclass(frozen=True)
class CadenceCheckpoint:
    """A named evaluation checkpoint within a session.

    ``offset_minutes`` is relative to session open (positive) or session close
    (negative). The absolute time is derived from the calendar-resolved session
    bounds, so early closes scale naturally.
    """
    name: str
    offset_minutes: int  # positive = from open, negative = from close

    def resolve(self, session_open: datetime, session_close: datetime) -> datetime:
        """Resolve to an absolute ET datetime for this session."""
        if self.offset_minutes < 0:
            return session_close + timedelta(minutes=self.offset_minutes)
        return session_open + timedelta(minutes=self.offset_minutes)


def resolve_checkpoints(
    checkpoints: Sequence[CadenceCheckpoint],
    session_open: datetime,
    session_close: datetime,
) -> list[tuple[str, datetime]]:
    """Resolve all checkpoints to absolute times, sorted chronologically.

    Checkpoints that fall outside ``[open, close)`` are excluded (e.g. a
    power-hour checkpoint on a very short half-day session).
    """
    resolved: list[tuple[str, datetime]] = []
    for cp in checkpoints:
        t = cp.resolve(session_open, session_close)
        if session_open <= t < session_close:
            resolved.append((cp.name, t))
    resolved.sort(key=lambda x: x[1])
    return resolved


def active_checkpoint(
    checkpoints: Sequence[tuple[str, datetime]],
    now: datetime,
    *,
    window_seconds: float = 60.0,
) -> str | None:
    """Return the name of the checkpoint whose window contains ``now``, or
    ``None`` if no checkpoint is active.

    A checkpoint is "active" when ``checkpoint_time <= now < checkpoint_time +
    window_seconds``. Only the FIRST matching checkpoint wins (they don't
    overlap for reasonable offsets).
    """
    for name, t in checkpoints:
        if t <= now < t + timedelta(seconds=window_seconds):
            return name
    return None


# ---------------------------------------------------------------------------
# Governor configuration — loaded from pinned strategy config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GovernorConfig:
    """The ``intraday_governors`` control-plane section.

    Absent section => disabled (all intents pass, governors are inert).
    Any malformed value forces ``enabled=False`` (fail closed) and is
    reported in ``config_errors``.
    """
    enabled: bool = False

    # --- per-session action cap ---
    # Max total actions (entries + exits) per session. 0 = unlimited.
    max_actions_per_session: int = 0

    # --- portfolio turnover cap ---
    # Max intraday turnover as fraction of portfolio equity. 0.0 = unlimited.
    # Turnover = sum of absolute notional of all actions / equity.
    max_turnover_fraction: float = 0.0

    # --- per-ticker cooldown ---
    # Min seconds between actions on the same ticker. 0 = no cooldown.
    min_seconds_between_same_ticker: float = 0.0

    # --- post-loss cooldown ---
    # After a realized loss, pause entries for this many seconds. 0 = no pause.
    loss_cooldown_seconds: float = 0.0
    # Only trigger loss cooldown if the loss exceeds this USD threshold.
    # Tiny losses (rounding, commissions) should not trigger a pause.
    loss_threshold_usd: float = 0.0

    # --- cadence checkpoints ---
    # Named checkpoints; if empty, only the fixed tick cadence drives evaluation.
    checkpoint_names: tuple[str, ...] = ()

    # --- config errors ---
    config_errors: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["checkpoint_names"] = list(self.checkpoint_names)
        record["config_errors"] = list(self.config_errors)
        return record

    def fingerprint(self) -> str:
        """Stable short hash of the governor config for audit provenance."""
        blob = json.dumps(self.to_record(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


def load_governor_config(strategy_config: Mapping[str, Any]) -> GovernorConfig:
    """Read ``intraday_governors`` from the pinned strategy config.

    Safe defaults: a missing/empty section is DISABLED; malformed values are
    collected into ``config_errors`` and force ``enabled=False``.
    """
    section = (strategy_config or {}).get("intraday_governors")
    if section is None:
        return GovernorConfig()
    errors: list[str] = []
    if not isinstance(section, Mapping):
        return GovernorConfig(
            config_errors=("intraday_governors is not a mapping",)
        )

    def _nonneg_int(key: str, default: int) -> int:
        raw = section.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors.append(f"{key} is not an integer: {raw!r}")
            return default
        if value < 0:
            errors.append(f"{key} must be >= 0: {raw!r}")
            return default
        return value

    def _nonneg_float(key: str, default: float) -> float:
        raw = section.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{key} is not a number: {raw!r}")
            return default
        if value < 0:
            errors.append(f"{key} must be >= 0: {raw!r}")
            return default
        return value

    enabled_raw = section.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        errors.append(f"enabled must be a boolean: {enabled_raw!r}")
        enabled_raw = False

    max_actions = _nonneg_int("max_actions_per_session", 0)
    max_turnover = _nonneg_float("max_turnover_fraction", 0.0)
    min_ticker_cd = _nonneg_float("min_seconds_between_same_ticker", 0.0)
    loss_cd = _nonneg_float("loss_cooldown_seconds", 0.0)
    loss_thresh = _nonneg_float("loss_threshold_usd", 0.0)

    cp_raw = section.get("checkpoint_names", [])
    if isinstance(cp_raw, (list, tuple)):
        checkpoint_names = tuple(str(c).strip() for c in cp_raw if str(c).strip())
    else:
        errors.append(f"checkpoint_names must be a list: {cp_raw!r}")
        checkpoint_names = ()

    return GovernorConfig(
        enabled=bool(enabled_raw) and not errors,
        max_actions_per_session=max_actions,
        max_turnover_fraction=max_turnover,
        min_seconds_between_same_ticker=min_ticker_cd,
        loss_cooldown_seconds=loss_cd,
        loss_threshold_usd=loss_thresh,
        checkpoint_names=checkpoint_names,
        config_errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Session governor state — accumulated during a session, never persisted
# across sessions (each session starts clean)
# ---------------------------------------------------------------------------
@dataclass
class GovernorState:
    """Mutable per-session state the governors track.

    Accumulated during a session by :meth:`GovernorEvaluator.record_action`;
    starts empty at session open. NOT persisted across sessions — each session
    is independent (the scheduler creates a fresh state at session start).
    """
    # Total actions taken this session (entries + exits).
    action_count: int = 0

    # Cumulative absolute notional of all actions this session.
    cumulative_turnover_notional: float = 0.0

    # Portfolio equity at session start (set once, used for turnover fraction).
    session_equity: float = 0.0

    # Per-ticker: last action time (aware ET datetime).
    last_action_by_ticker: dict[str, datetime] = field(default_factory=dict)

    # Last realized loss time and amount (for loss cooldown).
    last_loss_at: datetime | None = None
    last_loss_usd: float = 0.0

    def record_action(
        self,
        *,
        ticker: str,
        notional: float,
        at: datetime,
        realized_pnl: float | None = None,
        loss_threshold_usd: float = 0.0,
    ) -> None:
        """Record one action for governor tracking."""
        self.action_count += 1
        self.cumulative_turnover_notional += abs(notional)
        self.last_action_by_ticker[ticker] = at
        if realized_pnl is not None and realized_pnl < -abs(loss_threshold_usd):
            self.last_loss_at = at
            self.last_loss_usd = realized_pnl

    def turnover_fraction(self) -> float:
        """Current session turnover as fraction of equity."""
        if self.session_equity <= 0:
            return 0.0
        return self.cumulative_turnover_notional / self.session_equity

    def to_record(self) -> dict[str, Any]:
        return {
            "action_count": self.action_count,
            "cumulative_turnover_notional": self.cumulative_turnover_notional,
            "session_equity": self.session_equity,
            "turnover_fraction": self.turnover_fraction(),
            "last_action_by_ticker": {
                t: dt.isoformat() for t, dt in self.last_action_by_ticker.items()
            },
            "last_loss_at": self.last_loss_at.isoformat() if self.last_loss_at else None,
            "last_loss_usd": self.last_loss_usd,
        }


# ---------------------------------------------------------------------------
# Governor evaluation — pure function, returns ALLOW / BLOCK with reasons
# ---------------------------------------------------------------------------
BLOCK_MAX_ACTIONS = "governor_max_actions_per_session"
BLOCK_MAX_TURNOVER = "governor_max_turnover_fraction"
BLOCK_TICKER_COOLDOWN = "governor_ticker_cooldown"
BLOCK_LOSS_COOLDOWN = "governor_loss_cooldown"


@dataclass(frozen=True)
class GovernorVerdict:
    """The governor's verdict on one intent: ALLOW or BLOCK.

    ``blocked_reasons`` is empty when allowed. When blocked, it contains one
    or more reason codes (a single intent can trip multiple governors
    simultaneously). ``details`` provides human-readable context for each
    block reason.
    """
    allowed: bool
    blocked_reasons: tuple[str, ...] = ()
    details: dict[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked_reasons": list(self.blocked_reasons),
            "details": dict(self.details),
        }


def _as_aware(moment: datetime) -> datetime:
    """Treat a naive datetime as ET; leave an aware one alone."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=ET)


def evaluate_governor(
    *,
    config: GovernorConfig,
    state: GovernorState,
    ticker: str,
    side: str,
    notional: float,
    now: datetime,
) -> GovernorVerdict:
    """Evaluate all governors against one intent. Pure function.

    Returns :class:`GovernorVerdict` — ``allowed=True`` when all governors
    pass, else ``allowed=False`` with every tripped reason.

    Governor checks (all independent — every tripped governor is reported,
    not just the first):

    1. **Max actions per session**: ``state.action_count >= config.max_actions_per_session``
       (when the cap is >0).
    2. **Max turnover fraction**: would the new action push session turnover
       past ``config.max_turnover_fraction`` (when >0)?
    3. **Per-ticker cooldown**: has the ticker been acted on within
       ``config.min_seconds_between_same_ticker`` (when >0)?
    4. **Post-loss cooldown** (entries only — exits are NEVER blocked by
       loss cooldown, per the §10 exits-always-allowed invariant): has a
       realized loss exceeding the threshold occurred within
       ``config.loss_cooldown_seconds`` (when >0)?
    """
    if not config.enabled:
        return GovernorVerdict(allowed=True)

    now_aware = _as_aware(now)
    reasons: list[str] = []
    details: dict[str, str] = {}

    # 1. Max actions per session
    if config.max_actions_per_session > 0:
        if state.action_count >= config.max_actions_per_session:
            reasons.append(BLOCK_MAX_ACTIONS)
            details[BLOCK_MAX_ACTIONS] = (
                f"action_count={state.action_count} >= "
                f"max={config.max_actions_per_session}"
            )

    # 2. Max turnover fraction
    if config.max_turnover_fraction > 0 and state.session_equity > 0:
        projected_turnover = (
            state.cumulative_turnover_notional + abs(notional)
        ) / state.session_equity
        if projected_turnover > config.max_turnover_fraction:
            reasons.append(BLOCK_MAX_TURNOVER)
            details[BLOCK_MAX_TURNOVER] = (
                f"projected_turnover={projected_turnover:.4f} > "
                f"max={config.max_turnover_fraction:.4f}"
            )

    # 3. Per-ticker cooldown
    if config.min_seconds_between_same_ticker > 0:
        last = state.last_action_by_ticker.get(ticker)
        if last is not None:
            elapsed = (now_aware - _as_aware(last)).total_seconds()
            if elapsed < config.min_seconds_between_same_ticker:
                reasons.append(BLOCK_TICKER_COOLDOWN)
                details[BLOCK_TICKER_COOLDOWN] = (
                    f"elapsed={elapsed:.1f}s < "
                    f"min={config.min_seconds_between_same_ticker:.1f}s "
                    f"for {ticker}"
                )

    # 4. Post-loss cooldown (entries only — exits NEVER blocked)
    is_entry = str(side).upper() in ("BUY", "ENTRY")
    if is_entry and config.loss_cooldown_seconds > 0:
        if state.last_loss_at is not None:
            since_loss = (now_aware - _as_aware(state.last_loss_at)).total_seconds()
            if since_loss < config.loss_cooldown_seconds:
                reasons.append(BLOCK_LOSS_COOLDOWN)
                details[BLOCK_LOSS_COOLDOWN] = (
                    f"since_loss={since_loss:.1f}s < "
                    f"cooldown={config.loss_cooldown_seconds:.1f}s "
                    f"(loss={state.last_loss_usd:.2f})"
                )

    if reasons:
        return GovernorVerdict(
            allowed=False,
            blocked_reasons=tuple(reasons),
            details=details,
        )
    return GovernorVerdict(allowed=True)


# ---------------------------------------------------------------------------
# Batch evaluation — evaluate all intents from a tick, annotating each
# ---------------------------------------------------------------------------
def evaluate_tick_intents(
    *,
    config: GovernorConfig,
    state: GovernorState,
    intents: Sequence[Mapping[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Evaluate governors on a batch of intents from one tick.

    Returns a list of annotated intents: each original intent dict is extended
    with ``governor_verdict`` (the :class:`GovernorVerdict` record) and
    ``governor_blocked`` (bool shorthand). In shadow mode, ALL intents are
    kept (blocked ones are annotated, not removed) so the shadow log captures
    what would have been blocked.

    This does NOT update ``state`` — the caller decides whether to
    :meth:`GovernorState.record_action` based on whether the intent is
    ultimately executed (shadow vs live).
    """
    annotated: list[dict[str, Any]] = []
    for intent in intents:
        intent_dict = dict(intent)
        ticker = str(intent_dict.get("symbol", intent_dict.get("ticker", "")))
        side = str(intent_dict.get("side", ""))
        notional = float(intent_dict.get("notional", 0.0))
        verdict = evaluate_governor(
            config=config,
            state=state,
            ticker=ticker,
            side=side,
            notional=notional,
            now=now,
        )
        intent_dict["governor_verdict"] = verdict.to_record()
        intent_dict["governor_blocked"] = not verdict.allowed
        annotated.append(intent_dict)
    return annotated


# ---------------------------------------------------------------------------
# Governor evaluator — the integration point for the session scheduler
# ---------------------------------------------------------------------------
class GovernorEvaluator:
    """Stateful governor evaluator for one session.

    Created at session start, accumulates state through
    :meth:`record_action`, evaluates intents through :meth:`evaluate`.
    The evaluator is OBSERVE-ONLY in shadow mode: it annotates intents
    with governor verdicts but never prevents them from being logged.

    Integration: the session scheduler (or live executor) creates one
    evaluator per session and calls :meth:`evaluate` on each tick's intents
    after the pipeline produces them. The verdicts are stamped into the
    shadow tick record for downstream audit.
    """

    def __init__(
        self,
        config: GovernorConfig,
        *,
        session_equity: float = 0.0,
    ) -> None:
        self.config = config
        self.state = GovernorState(session_equity=session_equity)
        self._tick_count = 0

    def evaluate(
        self,
        intents: Sequence[Mapping[str, Any]],
        *,
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Evaluate all intents and return annotated copies."""
        self._tick_count += 1
        return evaluate_tick_intents(
            config=self.config,
            state=self.state,
            intents=intents,
            now=now,
        )

    def record_action(
        self,
        *,
        ticker: str,
        notional: float,
        at: datetime,
        realized_pnl: float | None = None,
    ) -> None:
        """Record a completed action (entry or exit) for governor tracking."""
        self.state.record_action(
            ticker=ticker,
            notional=notional,
            at=at,
            realized_pnl=realized_pnl,
            loss_threshold_usd=self.config.loss_threshold_usd,
        )

    def summary(self) -> dict[str, Any]:
        """Operational summary for the session manifest."""
        return {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE,
            "record_kind": RECORD_KIND,
            "governor_config_fingerprint": self.config.fingerprint(),
            "governor_enabled": self.config.enabled,
            "ticks_evaluated": self._tick_count,
            "state": self.state.to_record(),
            "config": self.config.to_record(),
        }


# ---------------------------------------------------------------------------
# Shadow tick observer — plugs into the scheduler's tick_observer seam
# ---------------------------------------------------------------------------
class GovernorShadowObserver:
    """SHADOW-ONLY tick observer that evaluates governors on each tick's
    intents and logs the verdicts.

    Designed to be wired into the session scheduler's ``tick_observer`` seam
    (same pattern as :class:`.entry_timing_policy.ShadowEntryTimingEvaluator`).
    It is invoked AFTER the never-submit assertion and AFTER the tick record
    is persisted; it cannot alter the decision payload. An observer exception
    is swallowed by the scheduler (observe-only diagnostics may never halt
    the shadow decision loop).

    Governor state is accumulated from the tick records it observes: each
    intent (entry or exit) that the governor ITSELF allowed this tick is
    counted as an action, building up the per-session governor state so
    later ticks see the accumulated action count, turnover, and per-ticker
    timestamps. A shadow-blocked intent is deliberately excluded from this
    accumulation — it never executes in the world being modeled, so it must
    not advance state as if it had.
    """

    def __init__(
        self,
        evaluator: GovernorEvaluator,
    ) -> None:
        self.evaluator = evaluator
        self._evaluations: list[dict[str, Any]] = []

    def on_tick(self, record: Mapping[str, Any]) -> None:
        """Process one persisted shadow tick record."""
        decisions = record.get("decisions") or {}
        intents = decisions.get("intents") or []
        tick_at_raw = record.get("tick_at")
        if not tick_at_raw:
            return

        try:
            now = datetime.fromisoformat(str(tick_at_raw))
            if now.tzinfo is None:
                now = now.replace(tzinfo=ET)
        except (ValueError, TypeError):
            return

        # Evaluate governors on the tick's intents
        annotated = self.evaluator.evaluate(intents, now=now)

        # Record the evaluation
        evaluation = {
            "schema_version": SCHEMA_VERSION,
            "kind": RECORD_KIND,
            "stage": STAGE,
            "session_date": record.get("session_date"),
            "tick_index": record.get("tick_index"),
            "tick_at": str(tick_at_raw),
            "n_intents": len(intents),
            "n_blocked": sum(1 for a in annotated if a.get("governor_blocked")),
            "verdicts": [
                {
                    "symbol": a.get("symbol", a.get("ticker", "")),
                    "side": a.get("side", ""),
                    "governor_blocked": a.get("governor_blocked", False),
                    "blocked_reasons": a.get("governor_verdict", {}).get("blocked_reasons", []),
                }
                for a in annotated
            ],
            "state_after": self.evaluator.state.to_record(),
        }
        self._evaluations.append(evaluation)

        # Accumulate governor state ONLY from intents the governor itself
        # allowed this tick. A shadow-blocked intent never executes in the
        # world this evaluator is modeling — feeding it into record_action()
        # anyway would advance action_count/turnover/cooldown state as if a
        # blocked action had actually happened, self-contaminating later
        # ticks' evaluations and systematically overstating cascading
        # blocks (once one governor trips, phantom state from the blocked
        # intent makes subsequent intents look more likely to trip too).
        for annotated_intent in annotated:
            if annotated_intent.get("governor_blocked"):
                continue
            ticker = str(annotated_intent.get("symbol", annotated_intent.get("ticker", "")))
            notional = float(annotated_intent.get("notional", 0.0))
            self.evaluator.record_action(
                ticker=ticker,
                notional=notional,
                at=now,
            )

    @property
    def evaluations(self) -> list[dict[str, Any]]:
        """All governor evaluations this session (for testing / reporting)."""
        return list(self._evaluations)


__all__ = [
    "BLOCK_LOSS_COOLDOWN",
    "BLOCK_MAX_ACTIONS",
    "BLOCK_MAX_TURNOVER",
    "BLOCK_TICKER_COOLDOWN",
    "CadenceCheckpoint",
    "DEFAULT_CHECKPOINTS",
    "GovernorConfig",
    "GovernorEvaluator",
    "GovernorShadowObserver",
    "GovernorState",
    "GovernorVerdict",
    "RECORD_KIND",
    "SCHEMA_VERSION",
    "STAGE",
    "active_checkpoint",
    "evaluate_governor",
    "evaluate_tick_intents",
    "load_governor_config",
    "resolve_checkpoints",
]
