"""renquant105 Stage-1 intraday session scheduler — SHADOW MODE ONLY.

M1 SLICE 3 of the Stage-1 build (RFC #208
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``
§8 row 3): the orchestrator slice — session scheduling, control-plane flag
plumbing, and the shadow decision log the replay/audit harness
(:mod:`.intraday_replay_audit`) verifies. Consumes slice 1
(renquant-execution #20, order-state machine) and slice 2
(renquant-pipeline #163, ``run_intraday_decision_tick``) strictly through
their contracts; implements neither.

**Nothing here can place an order.** The scheduler holds no trading client
with a submit path (class-C reads are GET-only, see
:mod:`.intraday_session_inputs`), the only implemented mode is
``"shadow"`` (``mode: "live"`` in config is DOWNGRADED to shadow with a
warning counter — Stage-2 authorization is a separate future decision per
§9.3a), and :func:`assert_shadow_never_submits` is a RUNTIME assertion
evaluated on every tick before its record is persisted: a non-shadow mode
or any broker-submission evidence in the tick payload raises
:class:`ShadowModeViolation` instead of writing the line. This is
deliberately stronger than the repo's earlier shadow tasks, whose
never-submit property was a docstring invariant only.

Default-OFF, triple-gated (§10): the pinned strategy config section
``intraday_decisioning`` must set ``enabled: true`` (absent section =>
disabled), the env kill switch ``RENQUANT_INTRADAY_DECISIONING`` must be
truthy, and the kill-switch FILE must be absent — the file is re-checked
every cycle, so dropping it mid-session halts the loop before the next tick.

Session semantics (§5 / §11b), all derived from the injected NYSE calendar
(:func:`~renquant_orchestrator.intraday_quote_logger.default_session_calendar`
— the same half-day-aware primitive the quote logger and execution use), so
early closes scale the windows with no hard-coded clock times:

- fixed tick cadence, default 180 s (3-min tick);
- first eligible decision tick at ``open + 5 min`` (auction settling);
- **entries stop** at ``close − 30 min`` (the entry cutoff); **exits
  continue to the bell** — past the cutoff the tick still runs, and
  :func:`apply_entry_window_policy` moves any entry intents to ``skipped``
  with reason ``entries_closed_window_cutoff`` while exit intents pass;
- non-session days (weekend/holiday) produce a manifest stamp and no ticks.

Every session writes two run-bundle artifacts under the operator data root
(never the umbrella git tree): the append-only shadow decision log
``logs/renquant105_pilot/intraday_decisions_shadow.jsonl`` (schema-versioned,
one line per tick: intents + blocked_by + envelope counters + input
fingerprints + the class-C/D inputs the replay harness re-runs against) and
the session manifest ``intraday_session_manifest_<date>.json`` (frozen
class-A/B inputs + fingerprints, tick count, calendar id, config
fingerprint) updated atomically after every tick.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from renquant_artifacts import hash_jsonable

from .env_files import load_env_file
from .intraday_quote_logger import (
    ET,
    SessionBounds,
    SessionCalendar,
    _as_aware,
    default_session_calendar,
)
from .intraday_session_inputs import (
    FrozenSignalError,
    SignalLeakError,
    assert_signal_predates_session,
    capture_session_start,
    live_state_fingerprint,
    verify_session_start,
)
from .runtime_paths import default_data_root, default_strategy_config_path

log = logging.getLogger("renquant.intraday_session_scheduler")

SCHEDULER_SCHEMA_VERSION = "rq105-intraday-shadow-v1"
RECORD_KIND_TICK = "intraday_decision_shadow_tick"
RECORD_KIND_MANIFEST = "intraday_session_manifest"
STAGE = "renquant105-stage1-operations-only"

#: §10 global kill switch env flag — default OFF; nothing runs until it is
#: explicitly set truthy AND the pinned config enables the feature.
ENV_FLAG = "RENQUANT_INTRADAY_DECISIONING"
_ENV_TRUTHY = frozenset({"1", "true", "yes", "on"})

MODE_SHADOW = "shadow"
MODE_LIVE = "live"

#: §5 / §11b Stage-1 defaults (seconds). All half-day aware because they are
#: applied to the calendar's actual session bounds.
DEFAULT_TICK_SECONDS = 180  # 3-min tick cadence (operator directive 2026-07-06)
DEFAULT_ENTRY_OPEN_DELAY_SECONDS = 300  # no entries in the first 5 min
DEFAULT_ENTRY_CLOSE_CUTOFF_SECONDS = 1800  # no NEW entries in the last 30 min

#: Window phases, in session order.
PHASE_BEFORE_SESSION = "before_session"
PHASE_SETTLING = "settling"  # open .. first eligible tick: no decisions yet
PHASE_ENTRIES_OPEN = "entries_open"
PHASE_EXITS_ONLY = "exits_only"  # past the entry cutoff: exits to the bell
PHASE_CLOSED = "closed"
PHASE_NON_SESSION = "non_session"

#: Audit reason stamped on entry intents suppressed past the cutoff (§11b).
REASON_ENTRY_WINDOW_CUTOFF = "entries_closed_window_cutoff"

#: Broker-submission evidence: none of these may ever appear inside a shadow
#: tick's decision payload (intents are pipeline INTENTS, never orders).
FORBIDDEN_SUBMISSION_KEYS = frozenset(
    {
        "broker_order_id",
        "client_order_id",
        "child_order_id",
        "submitted_at",
        "filled_qty",
        "fill_price",
        "broker_status",
    }
)


class ShadowModeViolation(RuntimeError):
    """The Stage-1 never-submit invariant would be violated (hard failure)."""


class PipelineContractUnavailable(RuntimeError):
    """The slice-2 pipeline contract is not importable — fail closed."""


# ---------------------------------------------------------------------------
# Config plumbing — pinned strategy config section, safe defaults.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IntradayDecisioningConfig:
    """The ``intraday_decisioning`` control-plane section (§8 row 3, §10).

    Absent section => disabled. Any malformed value forces ``enabled=False``
    (fail closed) and is reported in ``config_errors`` rather than silently
    defaulted, so a typo'd enable can never half-arm the scheduler.
    """

    enabled: bool = False
    mode: str = MODE_SHADOW
    tick_seconds: float = DEFAULT_TICK_SECONDS
    entry_open_delay_seconds: float = DEFAULT_ENTRY_OPEN_DELAY_SECONDS
    entry_close_cutoff_seconds: float = DEFAULT_ENTRY_CLOSE_CUTOFF_SECONDS
    canary_allowlist: tuple[str, ...] = ()
    kill_switch_file: str | None = None
    config_errors: tuple[str, ...] = ()

    def to_manifest_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["canary_allowlist"] = list(self.canary_allowlist)
        record["config_errors"] = list(self.config_errors)
        return record


def load_intraday_config(strategy_config: Mapping[str, Any]) -> IntradayDecisioningConfig:
    """Read ``intraday_decisioning`` from the pinned strategy config.

    Safe defaults: a missing/empty section is DISABLED; malformed values are
    collected into ``config_errors`` and force ``enabled=False``.
    """
    section = (strategy_config or {}).get("intraday_decisioning")
    if section is None:
        return IntradayDecisioningConfig()
    errors: list[str] = []
    if not isinstance(section, Mapping):
        return IntradayDecisioningConfig(
            config_errors=("intraday_decisioning is not a mapping",)
        )

    def _positive_seconds(key: str, default: float) -> float:
        raw = section.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{key} is not a number: {raw!r}")
            return default
        if not value > 0:
            errors.append(f"{key} must be > 0: {raw!r}")
            return default
        return value

    enabled_raw = section.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        errors.append(f"enabled must be a boolean: {enabled_raw!r}")
        enabled_raw = False
    mode = str(section.get("mode", MODE_SHADOW) or MODE_SHADOW)
    if mode not in (MODE_SHADOW, MODE_LIVE):
        errors.append(f"mode must be 'shadow' or 'live': {mode!r}")
        mode = MODE_SHADOW
    tick = _positive_seconds("tick_seconds", DEFAULT_TICK_SECONDS)
    open_delay = _positive_seconds(
        "entry_open_delay_seconds", DEFAULT_ENTRY_OPEN_DELAY_SECONDS
    )
    close_cutoff = _positive_seconds(
        "entry_close_cutoff_seconds", DEFAULT_ENTRY_CLOSE_CUTOFF_SECONDS
    )
    allow_raw = section.get("canary_allowlist", [])
    if isinstance(allow_raw, (list, tuple)):
        allowlist = tuple(str(t).upper() for t in allow_raw if str(t).strip())
    else:
        errors.append(f"canary_allowlist must be a list: {allow_raw!r}")
        allowlist = ()
    kill_raw = section.get("kill_switch_file")
    kill_file = str(kill_raw) if kill_raw else None

    return IntradayDecisioningConfig(
        enabled=bool(enabled_raw) and not errors,
        mode=mode,
        tick_seconds=tick,
        entry_open_delay_seconds=open_delay,
        entry_close_cutoff_seconds=close_cutoff,
        canary_allowlist=allowlist,
        kill_switch_file=kill_file,
        config_errors=tuple(errors),
    )


def env_flag_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """§10 global kill switch: ``RENQUANT_INTRADAY_DECISIONING``, default OFF."""
    env = os.environ if environ is None else environ
    return str(env.get(ENV_FLAG, "")).strip().lower() in _ENV_TRUTHY


def resolve_mode(config: IntradayDecisioningConfig) -> tuple[str, bool]:
    """Effective mode: always shadow in Stage 1.

    ``mode: "live"`` is NOT implemented — it downgrades to shadow and the
    downgrade is counted in the manifest (``live_mode_downgraded_count``),
    per the RFC's separate Stage-2 authorization bar (§9.3a).
    """
    if config.mode == MODE_LIVE:
        log.warning(
            "intraday_decisioning mode='live' is not implemented in Stage 1 "
            "— DOWNGRADING to shadow (see RFC #208 §9.3a)"
        )
        return MODE_SHADOW, True
    return MODE_SHADOW, False


# ---------------------------------------------------------------------------
# Kill switch — a file, honored mid-session (checked every cycle).
# ---------------------------------------------------------------------------
def default_kill_switch_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "data" / "rq105" / "intraday_decisioning.KILL"


@dataclass(frozen=True)
class KillSwitch:
    """Presence-of-file kill switch: touch the file to halt mid-session."""

    path: Path

    def engaged(self) -> bool:
        return self.path.exists()


# ---------------------------------------------------------------------------
# §11b session windows — derived from the calendar's actual bounds.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SessionWindows:
    """One session's decision windows (aware ET datetimes).

    ``entry_cutoff`` may not precede ``first_eligible_tick`` on a very short
    session — then the entry window is simply empty (exits-only session),
    never inverted.
    """

    open: datetime
    first_eligible_tick: datetime
    entry_cutoff: datetime
    close: datetime

    @classmethod
    def from_bounds(
        cls, bounds: SessionBounds, config: IntradayDecisioningConfig
    ) -> "SessionWindows":
        first = bounds.open + timedelta(seconds=config.entry_open_delay_seconds)
        cutoff = bounds.close - timedelta(seconds=config.entry_close_cutoff_seconds)
        if cutoff < first:
            cutoff = first  # empty entry window; exits still run to the bell
        return cls(
            open=bounds.open,
            first_eligible_tick=first,
            entry_cutoff=cutoff,
            close=bounds.close,
        )

    def phase(self, now: datetime) -> str:
        moment = _as_aware(now)
        if moment < self.open:
            return PHASE_BEFORE_SESSION
        if moment < self.first_eligible_tick:
            return PHASE_SETTLING
        if moment >= self.close:
            return PHASE_CLOSED
        if moment < self.entry_cutoff:
            return PHASE_ENTRIES_OPEN
        return PHASE_EXITS_ONLY

    def to_record(self) -> dict[str, str]:
        return {
            "open": self.open.isoformat(),
            "first_eligible_tick": self.first_eligible_tick.isoformat(),
            "entry_cutoff": self.entry_cutoff.isoformat(),
            "close": self.close.isoformat(),
        }


# ---------------------------------------------------------------------------
# Shadow never-submit runtime assertion.
# ---------------------------------------------------------------------------
def _scan_forbidden_keys(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_SUBMISSION_KEYS:
                found.append(here)
            found.extend(_scan_forbidden_keys(value, here))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            found.extend(_scan_forbidden_keys(value, f"{path}[{i}]"))
    return found


def assert_shadow_never_submits(*, mode: str, decisions: Mapping[str, Any]) -> None:
    """RUNTIME never-submit assertion, evaluated on every tick (§9 shadow bar).

    Two independent checks, either of which hard-fails the tick BEFORE its
    record is persisted:

    1. the effective mode must literally be ``"shadow"`` — there is no code
       path that submits, and this pins that there is no code path that even
       *claims* another mode;
    2. the decision payload must carry no broker-submission evidence
       (``FORBIDDEN_SUBMISSION_KEYS`` — child ids, fill fields, broker
       statuses). Intents are pipeline intents; anything shaped like an
       order lifecycle row means some upstream component actually submitted,
       and the shadow harness must halt loudly, not log it as shadow data.
    """
    if mode != MODE_SHADOW:
        raise ShadowModeViolation(
            f"effective mode {mode!r} != 'shadow': Stage-1 slice 3 has no "
            "authorized submit path (RFC #208 §9.3a)"
        )
    found = _scan_forbidden_keys(decisions)
    if found:
        raise ShadowModeViolation(
            "broker-submission evidence inside a shadow tick payload: "
            + ", ".join(sorted(found))
        )


# ---------------------------------------------------------------------------
# Tick-runner seam (slice-2 contract) + result normalization.
# ---------------------------------------------------------------------------
class TickRunner(Protocol):
    """The slice-2 decision tick, consumed structurally.

    Inputs are plain JSON-able mappings (the shapes recorded in the manifest
    and shadow log); the default binding converts them to the pipeline's
    dataclasses. Tests inject deterministic fakes.
    """

    def __call__(
        self,
        *,
        signal: Mapping[str, Any],
        session_start: Mapping[str, Any],
        live_state: Mapping[str, Any],
        session_counters: Mapping[str, Any],
        in_flight_parent_intents: Sequence[str],
        exit_orders: Sequence[Mapping[str, Any]],
    ) -> Any: ...


_ZERO_COUNTERS = {
    "entries_count": 0,
    "deployed_notional": 0.0,
    "turnover_notional": 0.0,
}


def normalize_tick_result(raw: Any) -> dict[str, Any]:
    """Canonical JSON-able decision payload from a tick-runner result.

    Accepts the pipeline's ``IntradayTickResult`` dataclass or an equivalent
    mapping (test doubles). Unknown extra keys are preserved.
    """
    if dataclasses.is_dataclass(raw) and not isinstance(raw, type):
        payload: dict[str, Any] = dataclasses.asdict(raw)
    elif isinstance(raw, Mapping):
        payload = {str(k): v for k, v in raw.items()}
    else:
        raise ShadowModeViolation(
            f"tick runner returned an unrecognizable result type: {type(raw)!r}"
        )
    payload.setdefault("enabled", True)
    payload.setdefault("reason", "ok")
    payload["intents"] = [dict(i) for i in payload.get("intents") or ()]
    payload["skipped"] = [dict(s) for s in payload.get("skipped") or ()]
    payload["blocked_by"] = dict(payload.get("blocked_by") or {})
    counters = payload.get("counters") or {}
    if dataclasses.is_dataclass(counters) and not isinstance(counters, type):
        counters = dataclasses.asdict(counters)
    payload["counters"] = {**_ZERO_COUNTERS, **dict(counters)}
    for intent in payload["intents"]:
        intent.setdefault("kind", "entry" if str(intent.get("side", "")).upper() == "BUY" else "exit")
    return payload


def apply_entry_window_policy(
    decisions: Mapping[str, Any],
    *,
    phase: str,
    counters_before: Mapping[str, Any],
) -> dict[str, Any]:
    """§11b envelope-cutoff semantics: past the cutoff, entries stop, exits
    continue.

    In ``exits_only`` every ENTRY intent is moved to ``skipped`` with reason
    ``entries_closed_window_cutoff`` and backed out of the session counters
    (it never happened); EXIT intents pass untouched — no window, envelope,
    or budget rule may ever block a protective exit (§10
    exits-always-allowed).
    """
    payload = {str(k): v for k, v in decisions.items()}
    if phase != PHASE_EXITS_ONLY:
        return payload
    kept: list[dict[str, Any]] = []
    skipped = [dict(s) for s in payload.get("skipped") or ()]
    counters = {**_ZERO_COUNTERS, **dict(payload.get("counters") or {})}
    for intent in payload.get("intents") or ():
        intent = dict(intent)
        if str(intent.get("kind", "")).lower() == "exit":
            kept.append(intent)
            continue
        notional = float(intent.get("notional") or 0.0)
        counters["entries_count"] = max(0, int(counters["entries_count"]) - 1)
        counters["deployed_notional"] = max(
            0.0, float(counters["deployed_notional"]) - notional
        )
        counters["turnover_notional"] = max(
            float(counters_before.get("turnover_notional", 0.0)),
            float(counters["turnover_notional"]) - notional,
        )
        skipped.append(
            {
                "symbol": intent.get("symbol", ""),
                "side": intent.get("side", "BUY"),
                "parent_intent_id": intent.get("parent_intent_id", ""),
                "reasons": [REASON_ENTRY_WINDOW_CUTOFF],
            }
        )
    payload["intents"] = kept
    payload["skipped"] = skipped
    payload["counters"] = counters
    return payload


def bind_pipeline_tick_runner(
    *,
    strategy_config: Mapping[str, Any],
    data_manifest: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
) -> TickRunner:
    """Default binding of the slice-2 contract (lazy import; fail closed).

    Raises :class:`PipelineContractUnavailable` when
    ``renquant_pipeline.intraday_decisioning`` is not importable — i.e.
    until pipeline #163 is merged AND the pins advance (§8 merge order). The
    scheduler CLI refuses to run in that case rather than inventing a local
    decision path (hard boundary: no decision/sizing internals here).
    """
    try:
        from renquant_pipeline import intraday_decisioning as contract  # noqa: PLC0415
    except ImportError as exc:
        raise PipelineContractUnavailable(
            "renquant_pipeline.intraday_decisioning is not importable — "
            "slice 2 (renquant-pipeline #163) must be merged and pinned "
            f"before the scheduler can run real ticks ({exc})"
        )

    def runner(
        *,
        signal: Mapping[str, Any],
        session_start: Mapping[str, Any],
        live_state: Mapping[str, Any],
        session_counters: Mapping[str, Any],
        in_flight_parent_intents: Sequence[str],
        exit_orders: Sequence[Mapping[str, Any]],
    ) -> Any:
        state = dict(live_state)
        return contract.run_intraday_decision_tick(
            strategy_config=dict(strategy_config),
            data_manifest=dict(data_manifest),
            artifact_manifest=dict(artifact_manifest),
            signal=contract.FrozenDailySignal(
                signal_version=str(signal["signal_version"]),
                as_of=str(signal["as_of"]),
                scores=dict(signal["scores"]),
            ),
            session_start=contract.SessionStartSnapshot(
                captured_at=str(session_start["captured_at"]),
                gate_inputs=dict(session_start["gate_inputs"]),
                gate_input_fingerprint=str(session_start["gate_input_fingerprint"]),
            ),
            live_state=contract.LiveStateSnapshot(
                as_of=str(state["as_of"]),
                trading_day=str(state["trading_day"]),
                account=str(state["account"]),
                cash=float(state["cash"]),
                equity=float(state["equity"]),
                positions=dict(state.get("positions") or {}),
                prices=dict(state.get("prices") or {}),
                open_buy_reservations=dict(state.get("open_buy_reservations") or {}),
                unsettled_buys=float(state.get("unsettled_buys") or 0.0),
                pending_broker_tickers=tuple(state.get("pending_broker_tickers") or ()),
            ),
            in_flight_parent_intents=tuple(in_flight_parent_intents),
            exit_orders=[dict(o) for o in exit_orders],
            session_counters=contract.SessionEnvelopeCounters(
                entries_count=int(session_counters.get("entries_count", 0)),
                deployed_notional=float(session_counters.get("deployed_notional", 0.0)),
                turnover_notional=float(session_counters.get("turnover_notional", 0.0)),
            ),
        )

    return runner


# ---------------------------------------------------------------------------
# Persistence: append-only shadow log + atomic session manifest.
# ---------------------------------------------------------------------------
def default_shadow_log_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_decisions_shadow.jsonl"


def default_manifest_path(session_date: str, data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return (
        Path(root)
        / "logs"
        / "renquant105_pilot"
        / f"intraday_session_manifest_{session_date}.json"
    )


class ShadowTickWriter:
    """Append-only, idempotent JSONL writer keyed on ``(session_date,
    tick_index)`` — a re-run or restart never duplicates a tick line, and
    nothing is ever rewritten in place."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen = self._load_keys()

    def _load_keys(self) -> set[tuple[str, int]]:
        keys: set[tuple[str, int]] = set()
        if not self.path.exists():
            return keys
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") != RECORD_KIND_TICK:
                    continue
                keys.add((str(row.get("session_date")), int(row.get("tick_index", -1))))
        return keys

    def append(self, record: Mapping[str, Any]) -> bool:
        key = (str(record.get("session_date")), int(record.get("tick_index", -1)))
        if key in self._seen:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        self._seen.add(key)
        return True


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, path)


# ---------------------------------------------------------------------------
# The scheduler.
# ---------------------------------------------------------------------------
@dataclass
class SessionScheduler:
    """Drives the §5 tick cadence for one session, shadow-only.

    Everything nondeterministic is injected: calendar, clock, sleep,
    class-A loader, class-B provider, class-C provider, exit-order provider,
    and the tick runner itself — tests run whole sessions with no
    wall-clock, no network, and no broker.
    """

    config: IntradayDecisioningConfig
    tick_runner: TickRunner
    signal_loader: Callable[[str], Mapping[str, Any]]
    session_start_provider: Callable[[str, datetime], Mapping[str, Any]]
    live_state_provider: Callable[..., Mapping[str, Any]]
    writer: ShadowTickWriter
    manifest_path: Path
    kill_switch: KillSwitch
    calendar: SessionCalendar | None = None
    exit_orders_provider: Callable[[datetime], Sequence[Mapping[str, Any]]] | None = None
    environ: Mapping[str, str] | None = None
    strategy_config_fingerprint: str = ""
    #: Optional OBSERVE-ONLY consumer of each persisted tick record (e.g. the
    #: entry-timing policy shadow evaluator, :mod:`.entry_timing_policy`). It
    #: is invoked AFTER the never-submit assertion and AFTER the record is
    #: appended; it cannot alter the decision payload, and an observer
    #: exception is counted in the manifest and swallowed — a diagnostic
    #: surface may never halt the shadow decision loop.
    tick_observer: Callable[[Mapping[str, Any]], None] | None = None
    _windows: SessionWindows | None = None
    _manifest: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.calendar is None:
            self.calendar = default_session_calendar()

    # -- manifest ------------------------------------------------------------
    def _init_manifest(self, session_date: str, mode: str, downgraded: bool) -> None:
        self._manifest = {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "kind": RECORD_KIND_MANIFEST,
            "stage": STAGE,
            "session_date": session_date,
            "calendar_id": getattr(self.calendar, "name", "unknown"),
            "status": "starting",
            "mode_requested": self.config.mode,
            "mode_effective": mode,
            "live_mode_downgraded_count": 1 if downgraded else 0,
            "config": self.config.to_manifest_record(),
            "config_fingerprint": hash_jsonable(self.config.to_manifest_record()),
            "strategy_config_fingerprint": self.strategy_config_fingerprint,
            "canary_allowlist": list(self.config.canary_allowlist),
            "kill_switch_file": str(self.kill_switch.path),
            "kill_switch_engaged": False,
            "tick_count": 0,
            "last_tick_at": None,
            "counters": dict(_ZERO_COUNTERS),
            "errors": [],
            "shadow_log": str(self.writer.path),
        }

    def _stamp(self, status: str, **extra: Any) -> dict[str, Any]:
        self._manifest["status"] = status
        self._manifest.update(extra)
        self._manifest["updated_at"] = datetime.now(ET).isoformat()
        _atomic_write_json(self.manifest_path, self._manifest)
        return dict(self._manifest)

    # -- one decision tick ----------------------------------------------------
    def _run_tick(
        self,
        *,
        now: datetime,
        phase: str,
        tick_index: int,
        signal: Mapping[str, Any],
        session_start: Mapping[str, Any],
        counters: Mapping[str, Any],
        seen_parents: set[str],
        mode: str,
        session_date: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        live_state = dict(
            self.live_state_provider(now=now, trading_day=session_date)
        )
        exit_orders = list(
            self.exit_orders_provider(now) if self.exit_orders_provider else ()
        )
        in_flight = sorted(
            seen_parents
            | set(live_state.get("open_buy_reservations") or {})
            | set(live_state.get("in_flight_parent_intents") or ())
        )
        verify_session_start(session_start)  # class B still frozen (§6)
        raw = self.tick_runner(
            signal=signal,
            session_start=session_start,
            live_state=live_state,
            session_counters=dict(counters),
            in_flight_parent_intents=in_flight,
            exit_orders=exit_orders,
        )
        decisions = apply_entry_window_policy(
            normalize_tick_result(raw), phase=phase, counters_before=counters
        )
        record = {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "kind": RECORD_KIND_TICK,
            "stage": STAGE,
            "session_date": session_date,
            "tick_index": tick_index,
            "tick_at": _as_aware(now).astimezone(ET).isoformat(),
            "mode": mode,
            "window_phase": phase,
            "calendar_id": getattr(self.calendar, "name", "unknown"),
            # §11b windows stamped per tick (additive) so downstream shadow
            # consumers (entry-timing policy evaluator, replay) can do
            # window/deadline math without re-deriving the calendar.
            "windows": self._windows.to_record() if self._windows else None,
            "fingerprints": {
                "signal_version": str(signal.get("signal_version", "")),
                "score_content_sha256": str(signal.get("score_content_sha256", "")),
                "gate_input_fingerprint": str(
                    session_start.get("gate_input_fingerprint", "")
                ),
                "live_state_sha256": live_state_fingerprint(live_state),
                "strategy_config_fingerprint": self.strategy_config_fingerprint,
            },
            "inputs": {
                "live_state": live_state,
                "in_flight_parent_intents": in_flight,
                "counters_before": dict(counters),
                "exit_orders": exit_orders,
            },
            "decisions": decisions,
        }
        # THE Stage-1 runtime assertion: shadow mode, and nothing in the
        # payload is broker-submission evidence. Raises before persisting.
        assert_shadow_never_submits(mode=mode, decisions=record["decisions"])
        self.writer.append(record)
        if self.tick_observer is not None:
            try:
                self.tick_observer(record)
            except Exception as exc:  # noqa: BLE001 — observe-only diagnostics
                # may never halt the shadow decision loop: count + continue.
                log.warning(
                    "tick observer failed (%s: %s) — continuing (observe-only)",
                    type(exc).__name__,
                    exc,
                )
                self._manifest["tick_observer_errors"] = (
                    int(self._manifest.get("tick_observer_errors", 0)) + 1
                )
        return record, dict(decisions.get("counters") or counters)

    # -- the session loop ------------------------------------------------------
    def run_session(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_cycles: int | None = None,
    ) -> dict[str, Any]:
        """Run (or refuse) one session. Returns the final manifest."""
        now_fn = now_fn or (lambda: datetime.now(ET))
        now = now_fn()
        session_date = _as_aware(now).astimezone(ET).date().isoformat()
        mode, downgraded = resolve_mode(self.config)
        self._init_manifest(session_date, mode, downgraded)

        if self.config.config_errors:
            return self._stamp(
                "disabled_config_invalid", errors=list(self.config.config_errors)
            )
        if not self.config.enabled:
            return self._stamp("disabled_config")
        if not env_flag_enabled(self.environ):
            return self._stamp("disabled_env_flag")
        if self.kill_switch.engaged():
            return self._stamp("halted_kill_switch", kill_switch_engaged=True)

        bounds = self.calendar.session_bounds(
            _as_aware(now).astimezone(ET).date()
        )
        if bounds is None:
            return self._stamp("non_session_day")
        windows = SessionWindows.from_bounds(bounds, self.config)
        self._windows = windows
        self._manifest["windows"] = windows.to_record()

        # Class A ONCE per session, leak-guarded twice (§6).
        try:
            signal = dict(self.signal_loader(session_date))
            assert_signal_predates_session(signal, session_date)
        except SignalLeakError as exc:
            return self._stamp("aborted_class_a_leak", errors=[str(exc)])
        except FrozenSignalError as exc:
            return self._stamp("aborted_class_a_unavailable", errors=[str(exc)])
        self._manifest["class_a"] = {
            "signal_version": signal.get("signal_version"),
            "as_of": signal.get("as_of"),
            "source_run_id": signal.get("source_run_id"),
            "score_content_sha256": signal.get("score_content_sha256"),
            "scores": dict(signal.get("scores") or {}),
        }
        self._stamp("running")

        session_start: dict[str, Any] | None = None
        counters: dict[str, Any] = dict(_ZERO_COUNTERS)
        seen_parents: set[str] = set()
        tick_index = 0
        cycles = 0
        status = "completed"

        while True:
            now = now_fn()
            if self.kill_switch.engaged():
                status = "halted_kill_switch"
                self._manifest["kill_switch_engaged"] = True
                break
            phase = windows.phase(now)
            if phase == PHASE_CLOSED:
                break
            if phase in (PHASE_ENTRIES_OPEN, PHASE_EXITS_ONLY):
                if session_start is None:
                    gate_inputs = self.session_start_provider(session_date, now)
                    session_start = capture_session_start(
                        gate_inputs,
                        captured_at=_as_aware(now).astimezone(ET).isoformat(),
                    )
                    self._manifest["class_b"] = dict(session_start)
                try:
                    record, counters = self._run_tick(
                        now=now,
                        phase=phase,
                        tick_index=tick_index,
                        signal=signal,
                        session_start=session_start,
                        counters=counters,
                        seen_parents=seen_parents,
                        mode=mode,
                        session_date=session_date,
                    )
                except ShadowModeViolation:
                    self._stamp("halted_shadow_violation")
                    raise
                except Exception as exc:
                    # Fail closed and loudly: stamp the manifest so the
                    # session is auditable, then propagate (the launchd
                    # wrapper alerts on a non-zero exit).
                    self._stamp("halted_tick_error", errors=[f"{type(exc).__name__}: {exc}"])
                    raise
                seen_parents |= {
                    str(i.get("parent_intent_id"))
                    for i in record["decisions"].get("intents", [])
                    if i.get("parent_intent_id")
                }
                tick_index += 1
                self._manifest["tick_count"] = tick_index
                self._manifest["last_tick_at"] = record["tick_at"]
                self._manifest["counters"] = dict(counters)
                self._stamp("running")
            # PHASE_BEFORE_SESSION / PHASE_SETTLING: wait, no decisions yet.
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                status = "stopped_max_cycles"
                break
            sleep_fn(self.config.tick_seconds)

        return self._stamp(status)


# ---------------------------------------------------------------------------
# CLI — files + read-only inputs only; fail closed without the pipeline pin.
# ---------------------------------------------------------------------------
def _load_json_object(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def main(
    argv: Sequence[str] | None = None,
    *,
    tick_runner: TickRunner | None = None,
    live_state_provider: Callable[..., Mapping[str, Any]] | None = None,
    calendar: SessionCalendar | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-session-scheduler",
        description=(
            "renquant105 Stage-1 SHADOW-ONLY intraday session scheduler "
            "(RFC #208 §8 row 3). Logs what the intraday decision tick "
            "WOULD do; never submits anything (runtime-asserted)."
        ),
    )
    parser.add_argument("--strategy-config", default=None, help="pinned strategy config JSON")
    parser.add_argument("--data-root", default=None, help="operator data root")
    parser.add_argument("--db", default=None, help="runs.alpaca.db path (read-only)")
    parser.add_argument("--out", default=None, help="shadow decisions JSONL path")
    parser.add_argument("--manifest", default=None, help="session manifest JSON path")
    parser.add_argument(
        "--order-state-file",
        default=None,
        help="slice-1 OrderStateBook snapshot for today's reservations (optional)",
    )
    parser.add_argument(
        "--data-manifest", default=None, help="data manifest JSON for the pipeline tick"
    )
    parser.add_argument(
        "--artifact-manifest",
        default=None,
        help="artifact manifest JSON for the pipeline tick",
    )
    parser.add_argument("--env-file", default=None, help=".env with Alpaca credentials")
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="print the final manifest")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    if args.env_file:
        load_env_file(args.env_file)

    data_root = Path(args.data_root) if args.data_root else default_data_root()
    strategy_config_path = (
        Path(args.strategy_config) if args.strategy_config else default_strategy_config_path()
    )
    strategy_config = _load_json_object(strategy_config_path)
    config = load_intraday_config(strategy_config)

    cal = calendar or default_session_calendar()
    session_date = datetime.now(ET).date().isoformat()
    db_path = Path(args.db) if args.db else data_root / "data" / "runs.alpaca.db"
    kill_path = (
        Path(config.kill_switch_file)
        if config.kill_switch_file
        else default_kill_switch_path(data_root)
    )
    manifest_path = (
        Path(args.manifest) if args.manifest else default_manifest_path(session_date, data_root)
    )
    out_path = Path(args.out) if args.out else default_shadow_log_path(data_root)

    if tick_runner is None:
        if not (args.data_manifest and args.artifact_manifest):
            print(
                "refusing to run: --data-manifest and --artifact-manifest are "
                "required for the real pipeline tick (fail closed; RFC #208 §8)",
                flush=True,
            )
            return 2
        try:
            tick_runner = bind_pipeline_tick_runner(
                strategy_config=strategy_config,
                data_manifest=_load_json_object(args.data_manifest),
                artifact_manifest=_load_json_object(args.artifact_manifest),
            )
        except PipelineContractUnavailable as exc:
            print(f"refusing to run: {exc}", flush=True)
            return 2

    if live_state_provider is None:
        from .intraday_quote_logger import AlpacaQuoteSource, load_watchlist  # noqa: PLC0415
        from .intraday_session_inputs import AlpacaLiveStateSource  # noqa: PLC0415

        source = AlpacaLiveStateSource(
            quote_source=AlpacaQuoteSource(),
            tickers=load_watchlist(strategy_config_path),
            order_state_path=args.order_state_file,
            paper=False,
        )

        def live_state_provider(**kwargs: Any) -> Mapping[str, Any]:
            return source.snapshot(**kwargs)

    from .intraday_session_inputs import load_frozen_daily_signal  # noqa: PLC0415

    def signal_loader(day: str) -> Mapping[str, Any]:
        return load_frozen_daily_signal(db_path=db_path, session_date=day, calendar=cal)

    def session_start_provider(day: str, now: datetime) -> Mapping[str, Any]:
        return {
            "session_date": day,
            "strategy_config_path": str(strategy_config_path),
            "watchlist": list(strategy_config.get("watchlist") or []),
            "canary_allowlist": list(config.canary_allowlist),
        }

    # Entry-timing policy SHADOW evaluator (the default and only wired mode of
    # .entry_timing_policy): observes each persisted tick record and logs what
    # each pre-declared policy WOULD have done + counterfactual costs. Absent
    # config section => baseline defaults; it never touches the decision path.
    from .entry_timing_policy import (  # noqa: PLC0415
        ShadowEntryTimingEvaluator,
        default_policy_shadow_log_path,
        load_entry_timing_config,
    )

    et_config = load_entry_timing_config(strategy_config)
    if et_config.config_errors:
        log.warning(
            "entry_timing config errors (fail-safe to baseline): %s",
            "; ".join(et_config.config_errors),
        )
    prior_close_refs: dict[str, float] | None = None
    if et_config.prior_close_refs_path:
        try:
            prior_close_refs = {
                str(k): float(v)
                for k, v in _load_json_object(et_config.prior_close_refs_path).items()
            }
        except (OSError, ValueError, TypeError) as exc:
            log.warning(
                "entry_timing prior_close_refs_path unreadable (%s) — gap "
                "reference absent; reversion policy will record degraded rows",
                exc,
            )
    evaluator = ShadowEntryTimingEvaluator(
        config=et_config,
        log_path=(
            Path(et_config.shadow_log)
            if et_config.shadow_log
            else default_policy_shadow_log_path(data_root)
        ),
        prior_close_refs=prior_close_refs,
        tick_seconds=config.tick_seconds,
    )

    scheduler = SessionScheduler(
        config=config,
        tick_runner=tick_runner,
        signal_loader=signal_loader,
        session_start_provider=session_start_provider,
        live_state_provider=live_state_provider,
        writer=ShadowTickWriter(out_path),
        manifest_path=manifest_path,
        kill_switch=KillSwitch(kill_path),
        calendar=cal,
        strategy_config_fingerprint=hash_jsonable(strategy_config),
        tick_observer=evaluator.on_tick,
    )
    try:
        manifest = scheduler.run_session(max_cycles=args.max_cycles)
    finally:
        # Censored cells are recorded by cause, never dropped, even when the
        # session halts early (kill switch / tick error).
        evaluator.flush()
    if args.json:
        print(json.dumps(manifest, sort_keys=True, indent=2))
    ok_statuses = {
        "completed",
        "stopped_max_cycles",
        "non_session_day",
        "disabled_config",
        "disabled_env_flag",
    }
    return 0 if manifest.get("status") in ok_statuses else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
