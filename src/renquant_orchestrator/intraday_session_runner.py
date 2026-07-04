"""renquant105 session runner — orchestrates Stage-1 + Stage-2 + software stops.

The integration point that wires all 105 modules into a single session
lifecycle:

1. Evaluate the §9.3a quintuple arming gate (``resolve_stage2_arming``)
2. If armed → drive ``LiveTickExecutor`` through the session tick loop
3. If ANY gate missing → delegate to the Stage-1 ``SessionScheduler`` (shadow)
4. Software stops evaluated each tick, signals logged (shadow or folded into
   live decisions when armed)
5. Entry-timing policy shadow evaluator runs as tick observer (same as today)

This was deferred in the Stage-2 PR (round 2, per codex review — "design
cost ahead of the §9.4 economic-authorization decision"). The §9.4 decision
gate is unchanged: this runner does NOT enable live mode — it provides the
orchestration layer that WOULD drive it once the gate opens. Until then,
every invocation falls through to shadow.

Shadow-only by default: all five gates of the quintuple gate must hold for
live execution. The runner never constructs a broker port unless armed.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .intraday_live_executor import (
    ArmDecision,
    LiveActionLog,
    LiveTickExecutor,
    LiveTickWriter,
    Stage2Authorization,
    default_authorization_path,
    default_canary_state_path,
    default_live_actions_path,
    default_live_log_path,
    default_order_state_book_path,
    resolve_stage2_arming,
)
from .intraday_session_scheduler import (
    KillSwitch,
    MODE_LIVE,
    MODE_SHADOW,
    PHASE_BEFORE_SESSION,
    PHASE_CLOSED,
    PHASE_ENTRIES_OPEN,
    PHASE_EXITS_ONLY,
    PHASE_SETTLING,
    SessionCalendar,
    SessionScheduler,
    SessionWindows,
    ShadowTickWriter,
    TickRunner,
    _as_aware,
    _atomic_write_json,
    apply_entry_window_policy,
    assert_shadow_never_submits,
    default_session_calendar,
    default_shadow_log_path,
    env_flag_enabled,
    load_intraday_config,
    normalize_tick_result,
)
from .runtime_paths import default_data_root
from .software_stop import (
    SoftwareStopEvaluator,
    SoftwareStopShadowLog,
    StopConfig,
    default_stop_log_path,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

log = logging.getLogger("renquant.intraday_session_runner")
ET = ZoneInfo("America/New_York")

RUNNER_SCHEMA_VERSION = "rq105-session-runner-v1"
RECORD_KIND_MANIFEST = "session_runner_manifest"


@dataclass
class SessionRunnerConfig:
    """Configuration for the session runner — aggregates all sub-configs."""

    data_root: Path
    strategy_config: dict[str, Any]
    strategy_config_path: Path | None = None
    authorization_path: Path | None = None
    canary_state_path: Path | None = None
    order_state_book_path: Path | None = None
    shadow_log_path: Path | None = None
    live_log_path: Path | None = None
    live_actions_path: Path | None = None
    stop_log_path: Path | None = None
    stop_config: StopConfig = field(default_factory=StopConfig)

    def resolve_paths(self) -> None:
        root = self.data_root
        if self.authorization_path is None:
            self.authorization_path = default_authorization_path(root)
        if self.canary_state_path is None:
            self.canary_state_path = default_canary_state_path(root)
        if self.order_state_book_path is None:
            self.order_state_book_path = default_order_state_book_path(root)
        if self.shadow_log_path is None:
            self.shadow_log_path = default_shadow_log_path(root)
        if self.live_log_path is None:
            self.live_log_path = default_live_log_path(root)
        if self.live_actions_path is None:
            self.live_actions_path = default_live_actions_path(root)
        if self.stop_log_path is None:
            self.stop_log_path = default_stop_log_path(root)


@dataclass
class SessionResult:
    """The outcome of one session run."""

    mode_effective: str
    armed: bool
    status: str
    manifest: dict[str, Any]
    stop_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "kind": RECORD_KIND_MANIFEST,
            "mode_effective": self.mode_effective,
            "armed": self.armed,
            "status": self.status,
        }
        if self.stop_summary is not None:
            out["software_stops"] = self.stop_summary
        out["manifest"] = self.manifest
        return out


def _extract_holdings(session_start: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract per-position holding info from class-B session start data.

    Looks for ``positions`` or ``holdings`` with entry price info. Falls back
    to ``position_hwm`` + ``entry_dates`` (the live_state shape).
    """
    holdings: dict[str, dict[str, Any]] = {}
    positions = session_start.get("positions") or session_start.get("holdings") or {}
    if isinstance(positions, Mapping):
        for sym, info in positions.items():
            if isinstance(info, Mapping):
                entry = info.get("entry_price") or info.get("avg_entry_price")
                if entry is not None:
                    holdings[str(sym).upper()] = {"entry_price": float(entry)}
    if not holdings:
        hwm = session_start.get("position_hwm") or {}
        entry_dates = session_start.get("entry_dates") or {}
        for ticker in entry_dates:
            if ticker in hwm and hwm[ticker]:
                holdings[str(ticker).upper()] = {"entry_price": float(hwm[ticker])}
    return holdings


def _extract_quotes(live_state: Mapping[str, Any]) -> dict[str, float]:
    """Extract current quotes from a live_state dict."""
    quotes: dict[str, float] = {}
    for key in ("prices", "marks", "quotes"):
        source = live_state.get(key)
        if isinstance(source, Mapping):
            for sym, px in source.items():
                try:
                    price = float(px)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    quotes[str(sym).upper()] = price
    return quotes


class SessionRunner:
    """Drives one complete intraday session with all 105 subsystems wired.

    Shadow by default — the quintuple gate determines whether the session
    actually submits orders. The runner never constructs a broker port
    unless all gates arm live mode.
    """

    def __init__(
        self,
        *,
        runner_config: SessionRunnerConfig,
        tick_runner: TickRunner,
        signal_loader: Callable[[str], Mapping[str, Any]],
        session_start_provider: Callable[[str, datetime], Mapping[str, Any]],
        live_state_provider: Callable[..., Mapping[str, Any]],
        calendar: SessionCalendar | None = None,
        port_factory: Callable[[], Any] | None = None,
        tick_observer: Callable[[Mapping[str, Any]], None] | None = None,
        exit_orders_provider: Callable[[datetime], Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.config = runner_config
        self.config.resolve_paths()
        self.intraday_config = load_intraday_config(runner_config.strategy_config)
        self.tick_runner = tick_runner
        self.signal_loader = signal_loader
        self.session_start_provider = session_start_provider
        self.live_state_provider = live_state_provider
        self.calendar = calendar or default_session_calendar()
        self.port_factory = port_factory
        self.tick_observer = tick_observer
        self.exit_orders_provider = exit_orders_provider
        self._stop_evaluator = SoftwareStopEvaluator(
            config=runner_config.stop_config,
        )
        self._stop_log = SoftwareStopShadowLog(runner_config.stop_log_path)

    def _build_kill_switch(self) -> KillSwitch:
        kill_path = (
            Path(self.intraday_config.kill_switch_file)
            if self.intraday_config.kill_switch_file
            else Path(self.config.data_root) / "data" / "rq105" / "intraday_decisioning.KILL"
        )
        return KillSwitch(kill_path)

    def _evaluate_arming(
        self, *, kill_switch: KillSwitch, today: str
    ) -> ArmDecision:
        return resolve_stage2_arming(
            config=self.intraday_config,
            authorization_path=self.config.authorization_path,
            canary_state_path=self.config.canary_state_path,
            kill_switch=kill_switch,
            today=today,
        )

    def run_session(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_cycles: int | None = None,
    ) -> SessionResult:
        """Run one session: arm → drive (live or shadow) → close."""
        now_fn = now_fn or (lambda: datetime.now(ET))
        now = now_fn()
        session_date = _as_aware(now).astimezone(ET).date().isoformat()
        kill_switch = self._build_kill_switch()

        arming = self._evaluate_arming(
            kill_switch=kill_switch, today=session_date
        )

        if not arming.armed:
            log.info(
                "quintuple gate NOT armed — delegating to Stage-1 shadow "
                "scheduler (mode_effective=%s, downgraded=%s, reasons=%s)",
                arming.mode_effective,
                arming.downgraded,
                arming.reasons,
            )
            return self._run_shadow(
                arming=arming,
                kill_switch=kill_switch,
                session_date=session_date,
                now_fn=now_fn,
                sleep_fn=sleep_fn,
                max_cycles=max_cycles,
            )

        log.info(
            "quintuple gate ARMED — driving Stage-2 live session "
            "(authorization=%s)",
            arming.authorization.content_sha256[:12] if arming.authorization else "?",
        )
        return self._run_live(
            arming=arming,
            kill_switch=kill_switch,
            session_date=session_date,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
            max_cycles=max_cycles,
        )

    def _run_shadow(
        self,
        *,
        arming: ArmDecision,
        kill_switch: KillSwitch,
        session_date: str,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        max_cycles: int | None,
    ) -> SessionResult:
        """Delegate to the unchanged Stage-1 scheduler (shadow mode)."""
        from renquant_artifacts import hash_jsonable

        manifest_path = (
            Path(self.config.data_root)
            / "logs"
            / "renquant105_pilot"
            / f"session_manifest_{session_date}.json"
        )
        scheduler = SessionScheduler(
            config=self.intraday_config,
            tick_runner=self.tick_runner,
            signal_loader=self.signal_loader,
            session_start_provider=self.session_start_provider,
            live_state_provider=self.live_state_provider,
            writer=ShadowTickWriter(self.config.shadow_log_path),
            manifest_path=manifest_path,
            kill_switch=kill_switch,
            calendar=self.calendar,
            exit_orders_provider=self.exit_orders_provider,
            strategy_config_fingerprint=hash_jsonable(self.config.strategy_config),
            tick_observer=self.tick_observer,
        )
        manifest = scheduler.run_session(
            now_fn=now_fn, sleep_fn=sleep_fn, max_cycles=max_cycles
        )
        manifest["stage2_arming"] = arming.to_manifest_record()
        return SessionResult(
            mode_effective=MODE_SHADOW,
            armed=False,
            status=manifest.get("status", "unknown"),
            manifest=manifest,
            stop_summary=self._stop_evaluator.to_record(),
        )

    def _run_live(
        self,
        *,
        arming: ArmDecision,
        kill_switch: KillSwitch,
        session_date: str,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        max_cycles: int | None,
    ) -> SessionResult:
        """Drive a Stage-2 live session with all safety invariants."""
        assert arming.armed and arming.authorization is not None

        if self.port_factory is None:
            log.error(
                "quintuple gate armed but no port_factory provided — "
                "cannot construct a submitting broker client; falling back "
                "to shadow"
            )
            return self._run_shadow(
                arming=arming,
                kill_switch=kill_switch,
                session_date=session_date,
                now_fn=now_fn,
                sleep_fn=sleep_fn,
                max_cycles=max_cycles,
            )

        port = self.port_factory()
        executor = LiveTickExecutor(
            account="primary",
            trading_day=session_date,
            port=port,
            action_log=LiveActionLog(self.config.live_actions_path),
            book_path=self.config.order_state_book_path,
            authorization=arming.authorization,
            canary_state_path=self.config.canary_state_path,
        )
        live_writer = LiveTickWriter(self.config.live_log_path)

        begin_result = executor.begin_session()
        now = now_fn()
        bounds = self.calendar.session_bounds(_as_aware(now).astimezone(ET).date())
        if bounds is None:
            return SessionResult(
                mode_effective=MODE_LIVE,
                armed=True,
                status="non_session_day",
                manifest={
                    "stage2_arming": arming.to_manifest_record(),
                    "session_begin": begin_result,
                },
            )

        windows = SessionWindows.from_bounds(bounds, self.intraday_config)
        signal = dict(self.signal_loader(session_date))
        session_start: dict[str, Any] | None = None
        tick_index = 0
        cycles = 0
        status = "completed"
        tick_results: list[dict[str, Any]] = []

        while True:
            now = now_fn()
            if kill_switch.engaged():
                status = "halted_kill_switch"
                break
            phase = windows.phase(now)
            if phase == PHASE_CLOSED:
                break
            if phase in (PHASE_ENTRIES_OPEN, PHASE_EXITS_ONLY):
                if session_start is None:
                    gate_inputs = self.session_start_provider(session_date, now)
                    session_start = dict(gate_inputs)
                    holdings = _extract_holdings(session_start)
                    self._stop_evaluator.load_positions(holdings)

                live_state = dict(
                    self.live_state_provider(now=now, trading_day=session_date)
                )
                raw = self.tick_runner(
                    signal=signal,
                    session_start=session_start,
                    live_state=live_state,
                    session_counters={},
                    in_flight_parent_intents=[],
                    exit_orders=[],
                )
                decisions = apply_entry_window_policy(
                    normalize_tick_result(raw), phase=phase, counters_before={}
                )

                quotes = _extract_quotes(live_state)
                stop_signals = self._stop_evaluator.evaluate_tick(quotes, now=now)
                for sig in stop_signals:
                    self._stop_log.append(sig, session_date=session_date)
                    intents = list(decisions.get("intents") or [])
                    intents.append(sig.to_intent())
                    decisions["intents"] = intents

                tick_result = executor.process_tick(decisions, now=now)
                record = {
                    "schema_version": RUNNER_SCHEMA_VERSION,
                    "kind": "live_tick",
                    "session_date": session_date,
                    "tick_index": tick_index,
                    "tick_at": _as_aware(now).astimezone(ET).isoformat(),
                    "mode": MODE_LIVE,
                    "window_phase": phase,
                    "decisions": decisions,
                    "execution": tick_result,
                    "stop_signals": [s.to_intent() for s in stop_signals],
                }
                live_writer.append(record)
                if self.tick_observer is not None:
                    try:
                        self.tick_observer(record)
                    except Exception:
                        pass
                tick_results.append(tick_result)
                tick_index += 1
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                status = "stopped_max_cycles"
                break
            sleep_fn(self.intraday_config.tick_seconds)

        close_result = executor.close_session(now=now_fn())
        manifest = {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "kind": RECORD_KIND_MANIFEST,
            "session_date": session_date,
            "mode_effective": MODE_LIVE,
            "status": status,
            "stage2_arming": arming.to_manifest_record(),
            "session_begin": begin_result,
            "session_close": close_result,
            "tick_count": tick_index,
            "cycles": cycles,
        }
        return SessionResult(
            mode_effective=MODE_LIVE,
            armed=True,
            status=status,
            manifest=manifest,
            stop_summary=self._stop_evaluator.to_record(),
        )
