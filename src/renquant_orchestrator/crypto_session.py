"""24/7 crypto session scheduler (D-C11).

Manages always-open trading sessions for the crypto sleeve. Each session
spans one UTC calendar day (00:00-24:00 UTC). The scheduler ticks at a
configurable cadence (default 900s / 15 min) and gates entries via:

1. Config enabled flag (``crypto_trading.enabled``)
2. Env flag (``RENQUANT_CRYPTO_TRADING``, default OFF)
3. Kill-switch file absent (``data/crypto/kill_switch``, resolved from the
   audited data root — see :func:`default_crypto_kill_switch_path`)

Signal leakage prevention (all ENFORCED in :func:`evaluate_tick`, not merely
computed/echoed):
- Watermark: session D may only consume bars through D-1's close.
  ``signal_snapshot.bar_watermark_utc`` must match
  :func:`watermark_for_session` EXACTLY or entries fail closed.
- Quiet interval: [D 00:00, D 00:00 + ``quiet_interval_minutes``) UTC — no
  new entries.
- Signal snapshot digest: the caller must supply an
  ``expected_signal_snapshot_digest`` sourced from an independently
  verified artifact path (the run bundle / artifact ledger) — self-hashing
  ``signal_snapshot`` is never treated as proof, only as an echo for the
  decision record.

Two further unbypassable, entry-only gates (never affect ``exits_allowed``):
- ``config.mode`` must be in ``CRYPTO_ENTRY_ELIGIBLE_MODES`` (``"live"`` or
  ``"paper"`` — paper trades against Alpaca's paper endpoint, a genuinely
  authorized, no-real-capital-at-risk state) — any other mode (e.g. the
  default ``"shadow"``) still produces a full, richly-populated decision
  record (digest, watermark outcome, quiet-interval flag, ...) but with
  ``entries_allowed`` forced to ``False``.
- ``crypto_stop_coverage_violations`` (the caller-supplied result of
  ``renquant_execution``'s ``AlpacaBroker.check_crypto_stop_coverage()``)
  must be an empty list (fully covered). ``None`` — the precondition was
  never evaluated by the caller — is deliberately NOT treated as "assume
  covered": an unproven-safe state fails closed exactly like a confirmed
  violation.

Design reference: crypto RFC §3.5, merged as orchestrator PR #453. Revised
per Codex CHANGES_REQUESTED review on PR #497 (2026-07-12): watermark/digest
enforcement, the mode gate, configurable quiet interval, and the
stop-coverage precondition were all previously unenforced — see
``doc/progress/2026-07-12-crypto-session-scheduler.md`` "Revision note".
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .runtime_paths import default_data_root


CRYPTO_ENV_FLAG = "RENQUANT_CRYPTO_TRADING"
CRYPTO_KILL_SWITCH_RELPATH = "data/crypto/kill_switch"
CRYPTO_LIVE_MODE = "live"
CRYPTO_PAPER_MODE = "paper"
# Entry-eligible modes (2026-07-12, reconciling #497/#499): "paper" trades
# against Alpaca's paper (fake-money) endpoint -- the same account this
# codebase's Stage-0 paper battery (D-C12, execution#32/orchestrator#500)
# exercises -- so it is a genuinely authorized, safe-to-enter runtime state,
# not a record-only one. Restricting to "live" alone (an earlier revision
# of this module did) would make it impossible to ever validate this
# scheduler end-to-end before flipping to real capital. "shadow" (the
# default) is the only mode that stays record-only.
CRYPTO_ENTRY_ELIGIBLE_MODES = frozenset({CRYPTO_LIVE_MODE, CRYPTO_PAPER_MODE})
DEFAULT_TICK_CADENCE_SECONDS = 900
QUIET_INTERVAL_MINUTES = 15
MAX_QUIET_INTERVAL_MINUTES = 24 * 60
MAX_TICK_CADENCE_SECONDS = 3600
DEFAULT_NTFY_TOPIC = "renquant-crypto"


@dataclass(frozen=True)
class SessionWindow:
    """One UTC calendar-day session boundary."""

    session_date: dt.date
    open_utc: dt.datetime
    close_utc: dt.datetime
    quiet_end_utc: dt.datetime

    @classmethod
    def for_date(
        cls,
        d: dt.date,
        quiet_interval_minutes: int = QUIET_INTERVAL_MINUTES,
    ) -> SessionWindow:
        """Build the session window for UTC calendar date ``d``.

        ``quiet_interval_minutes`` defaults to the module constant for
        backward-compatible call sites, but any caller holding a
        ``CryptoSessionConfig`` MUST pass ``config.quiet_interval_minutes``
        explicitly — see :func:`evaluate_tick`.
        """
        open_utc = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
        close_utc = open_utc + dt.timedelta(days=1)
        quiet_end = open_utc + dt.timedelta(minutes=quiet_interval_minutes)
        return cls(
            session_date=d,
            open_utc=open_utc,
            close_utc=close_utc,
            quiet_end_utc=quiet_end,
        )

    def in_quiet_interval(self, now_utc: dt.datetime) -> bool:
        return self.open_utc <= now_utc < self.quiet_end_utc

    def is_active(self, now_utc: dt.datetime) -> bool:
        return self.open_utc <= now_utc < self.close_utc


def current_session_date(now_utc: dt.datetime | None = None) -> dt.date:
    """Return the current session's UTC calendar date."""
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)
    return now_utc.date()


@dataclass(frozen=True)
class SignalSnapshot:
    """Immutable signal identity for one session."""

    session_date: dt.date
    bar_watermark_utc: dt.datetime
    universe_hash: str
    model_content_sha256: str
    calibrator_content_sha256: str

    def digest(self) -> str:
        canonical = json.dumps(
            {
                "bar_watermark_utc": self.bar_watermark_utc.isoformat(),
                "calibrator_content_sha256": self.calibrator_content_sha256,
                "model_content_sha256": self.model_content_sha256,
                "session_date": self.session_date.isoformat(),
                "universe_hash": self.universe_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class TickResult:
    """Result of a single scheduler tick — a decision RECORD.

    ``mode`` names the ``crypto_trading.mode`` that produced this record
    (e.g. ``"live"`` or ``"shadow"``) even when it is the reason
    ``entries_allowed`` is ``False`` — a DARK/shadow-mode tick still yields
    a full record (digest, watermark outcome, quiet-interval flag, ...),
    never a degraded/empty one.
    """

    session_date: dt.date
    tick_utc: dt.datetime
    entries_allowed: bool
    exits_allowed: bool
    reason: str
    signal_snapshot_digest: str | None = None
    is_quiet: bool = False
    is_kill_switched: bool = False
    mode: str = "shadow"

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "session_date": self.session_date.isoformat(),
            "tick_utc": self.tick_utc.isoformat(),
            "entries_allowed": self.entries_allowed,
            "exits_allowed": self.exits_allowed,
            "reason": self.reason,
            "signal_snapshot_digest": self.signal_snapshot_digest,
            "is_quiet": self.is_quiet,
            "is_kill_switched": self.is_kill_switched,
            "mode": self.mode,
        }


@dataclass
class CryptoSessionConfig:
    """Configuration for the crypto session scheduler."""

    enabled: bool = False
    tick_cadence_seconds: int = DEFAULT_TICK_CADENCE_SECONDS
    mode: str = "shadow"
    kill_switch_path: Path | None = None
    ntfy_topic: str = DEFAULT_NTFY_TOPIC
    sleeve_budget_usd: float = 0.0
    max_drawdown_pct: float = 10.0
    quiet_interval_minutes: int = QUIET_INTERVAL_MINUTES

    def __post_init__(self) -> None:
        """Fail closed at construction time on nonsensical timing config.

        Applies to every construction path (direct ``CryptoSessionConfig(...)``
        and :meth:`from_dict`, since ``__post_init__`` runs unconditionally
        after ``__init__``) — an invalid scheduler config should never make
        it into ``evaluate_tick`` in the first place.
        """
        if not (0 <= self.quiet_interval_minutes < MAX_QUIET_INTERVAL_MINUTES):
            raise ValueError(
                "quiet_interval_minutes must satisfy 0 <= value < "
                f"{MAX_QUIET_INTERVAL_MINUTES} (one day), got "
                f"{self.quiet_interval_minutes!r}"
            )
        if not (0 < self.tick_cadence_seconds <= MAX_TICK_CADENCE_SECONDS):
            raise ValueError(
                "tick_cadence_seconds must satisfy 0 < value <= "
                f"{MAX_TICK_CADENCE_SECONDS}, got {self.tick_cadence_seconds!r}"
            )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CryptoSessionConfig:
        crypto = d.get("crypto_trading", {})
        return cls(
            enabled=bool(crypto.get("enabled", False)),
            tick_cadence_seconds=int(
                crypto.get("tick_cadence_seconds", DEFAULT_TICK_CADENCE_SECONDS)
            ),
            mode=str(crypto.get("mode", "shadow")),
            kill_switch_path=(
                Path(crypto["kill_switch_path"])
                if crypto.get("kill_switch_path")
                else None
            ),
            ntfy_topic=str(crypto.get("ntfy_topic", DEFAULT_NTFY_TOPIC)),
            sleeve_budget_usd=float(crypto.get("sleeve_budget_usd", 0.0)),
            max_drawdown_pct=float(crypto.get("max_drawdown_pct", 10.0)),
            quiet_interval_minutes=int(
                crypto.get("quiet_interval_minutes", QUIET_INTERVAL_MINUTES)
            ),
        )


def _env_flag_enabled() -> bool:
    val = os.environ.get(CRYPTO_ENV_FLAG, "").strip().lower()
    return val in ("1", "true", "yes", "on")


def default_crypto_kill_switch_path(data_root: Path | None = None) -> Path:
    """Default kill-switch path, resolved from the audited data root.

    A bare relative ``Path(CRYPTO_KILL_SWITCH_RELPATH)`` resolves against
    the process's current working directory, which is not reliable for a
    scheduled/cron/launchd-launched process. Instead this resolves against
    :func:`~renquant_orchestrator.runtime_paths.default_data_root` — the
    same convention ``intraday_session_scheduler.default_kill_switch_path``
    already uses for the analogous rq105 kill switch.
    """
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / CRYPTO_KILL_SWITCH_RELPATH


def _kill_switch_active(config: CryptoSessionConfig) -> bool:
    if config.kill_switch_path is not None:
        return config.kill_switch_path.exists()
    return default_crypto_kill_switch_path().exists()


def check_triple_gate(config: CryptoSessionConfig) -> tuple[bool, str]:
    """Evaluate the triple safety gate. Returns (passed, reason)."""
    if not config.enabled:
        return False, "config crypto_trading.enabled=false"
    if not _env_flag_enabled():
        return False, f"env {CRYPTO_ENV_FLAG} not set or false"
    if _kill_switch_active(config):
        path = config.kill_switch_path or default_crypto_kill_switch_path()
        return False, f"kill switch file present: {path}"
    return True, "triple gate passed"


def _apply_final_entry_gates(
    result: TickResult,
    *,
    config: CryptoSessionConfig,
    crypto_stop_coverage_violations: list[dict[str, Any]] | None,
) -> TickResult:
    """Apply the two unbypassable, entry-only final gates.

    These run AFTER every other check in :func:`evaluate_tick` (triple gate,
    quiet interval, signal-snapshot presence/date/watermark/digest). They
    can only ever turn a would-be-allowed entry into a blocked one — never
    the reverse — and they never erase or overwrite the record fields
    (``signal_snapshot_digest``, ``is_quiet``, ``is_kill_switched``, ...)
    already on ``result``, so a shadow/DARK-mode or coverage-unproven tick
    still yields a full, richly-populated decision record, not a degraded
    one. ``exits_allowed`` is never touched here.
    """
    entries_allowed = result.entries_allowed
    reason = result.reason

    # Fix 3 (Codex #497 review item 3): crypto_trading.mode must be an
    # explicit, authorized entry-eligible value -- "live" or "paper" (see
    # CRYPTO_ENTRY_ELIGIBLE_MODES). "shadow" (the default) and any other
    # value produce a decision record only.
    if entries_allowed and config.mode not in CRYPTO_ENTRY_ELIGIBLE_MODES:
        entries_allowed = False
        reason = (
            f"{reason}; mode={config.mode}, not in the entry-eligible set "
            f"{sorted(CRYPTO_ENTRY_ELIGIBLE_MODES)}"
        )

    # Fix 5 (Codex #497 review item 5): protective-stop coverage precondition.
    # None means the caller never checked — an UNPROVEN-safe state, not a
    # proven-safe one — and fails closed exactly like a confirmed violation.
    if entries_allowed:
        if crypto_stop_coverage_violations is None:
            entries_allowed = False
            reason = (
                f"{reason}; stop-coverage precondition not evaluated "
                "(caller never called check_crypto_stop_coverage — an "
                "unproven-safe state fails closed the same as a confirmed "
                "violation)"
            )
        elif crypto_stop_coverage_violations:
            symbols = sorted(
                {
                    str(v.get("symbol", v))
                    for v in crypto_stop_coverage_violations
                }
            )
            entries_allowed = False
            reason = (
                f"{reason}; crypto stop-coverage violations for: "
                f"{', '.join(symbols)}"
            )

    return replace(
        result,
        entries_allowed=entries_allowed,
        reason=reason,
        mode=config.mode,
    )


def evaluate_tick(
    *,
    config: CryptoSessionConfig,
    now_utc: dt.datetime | None = None,
    signal_snapshot: SignalSnapshot | None = None,
    expected_signal_snapshot_digest: str | None = None,
    crypto_stop_coverage_violations: list[dict[str, Any]] | None = None,
) -> TickResult:
    """Evaluate one scheduler tick.

    Exits are ALWAYS allowed (§5.4 precedence), regardless of every gate
    below. Entries are gated by, in order:

    1. Triple gate (config + env + kill switch) — :func:`check_triple_gate`.
    2. Quiet interval (first ``config.quiet_interval_minutes`` of each UTC
       day).
    3. A signal snapshot present for the current session.
    4. The snapshot's ``session_date`` matching the current session.
    5. The snapshot's ``bar_watermark_utc`` matching
       :func:`watermark_for_session` EXACTLY — a snapshot whose bars reach
       into the current session (or the future) fails closed instead of
       merely being echoed.
    6. ``expected_signal_snapshot_digest``, supplied by the CALLER from an
       independently verified artifact path (the run bundle / artifact
       ledger) — never derived from ``signal_snapshot`` itself, since
       self-hashing untrusted input is provenance decoration, not
       verification — must equal ``signal_snapshot.digest()`` exactly.
       ``None`` (no expected digest supplied) fails closed distinctly from
       a mismatch.
    7. ``config.mode`` must be in ``CRYPTO_ENTRY_ELIGIBLE_MODES`` (unbypassable
       final gate, see :func:`_apply_final_entry_gates`) — ``"live"`` or
       ``"paper"`` (Alpaca's paper endpoint, no real capital at risk); every
       other mode (including the default ``"shadow"``) still yields a full
       decision record with ``entries_allowed=False``.
    8. ``crypto_stop_coverage_violations`` (unbypassable final gate) must be
       an empty list. ``None`` — the caller never evaluated the
       precondition — is deliberately NOT treated as "assume covered": it
       fails closed exactly like a confirmed violation, per Codex's framing
       that a scheduler which can admit an entry without proving
       protective-order readiness is not fail-closed.

    Gates 7-8 are applied uniformly to whatever gates 1-6 produced, so they
    can only ever narrow a would-be-allowed entry, never widen a blocked
    one, and never destroy the reason/record information gates 1-6 set.
    """
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    session_d = current_session_date(now_utc)
    window = SessionWindow.for_date(
        session_d, quiet_interval_minutes=config.quiet_interval_minutes
    )

    gate_ok, gate_reason = check_triple_gate(config)
    if not gate_ok:
        result = TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=gate_reason,
            is_kill_switched=_kill_switch_active(config),
        )
    elif window.in_quiet_interval(now_utc):
        result = TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason="quiet interval — no new entries",
            is_quiet=True,
            signal_snapshot_digest=(
                signal_snapshot.digest() if signal_snapshot else None
            ),
        )
    elif signal_snapshot is None:
        result = TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason="no signal snapshot for session — entries fail-closed",
        )
    elif signal_snapshot.session_date != session_d:
        result = TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=(
                "signal snapshot date mismatch: "
                f"{signal_snapshot.session_date} vs {session_d}"
            ),
            signal_snapshot_digest=signal_snapshot.digest(),
        )
    else:
        expected_watermark = watermark_for_session(session_d)
        digest = signal_snapshot.digest()
        if signal_snapshot.bar_watermark_utc != expected_watermark:
            result = TickResult(
                session_date=session_d,
                tick_utc=now_utc,
                entries_allowed=False,
                exits_allowed=True,
                reason=(
                    "signal snapshot watermark mismatch: expected "
                    f"{expected_watermark.isoformat()}, got "
                    f"{signal_snapshot.bar_watermark_utc.isoformat()}"
                ),
                signal_snapshot_digest=digest,
            )
        elif expected_signal_snapshot_digest is None:
            result = TickResult(
                session_date=session_d,
                tick_utc=now_utc,
                entries_allowed=False,
                exits_allowed=True,
                reason=(
                    "no expected signal-snapshot digest supplied by the "
                    "caller — entries fail-closed (self-hashing the "
                    "snapshot is not verification; the expected digest "
                    "must come from the run bundle / artifact ledger)"
                ),
                signal_snapshot_digest=digest,
            )
        elif digest != expected_signal_snapshot_digest:
            result = TickResult(
                session_date=session_d,
                tick_utc=now_utc,
                entries_allowed=False,
                exits_allowed=True,
                reason=(
                    "signal snapshot digest mismatch: expected "
                    f"{expected_signal_snapshot_digest}, got {digest}"
                ),
                signal_snapshot_digest=digest,
            )
        else:
            result = TickResult(
                session_date=session_d,
                tick_utc=now_utc,
                entries_allowed=True,
                exits_allowed=True,
                reason="entries allowed",
                signal_snapshot_digest=digest,
            )

    return _apply_final_entry_gates(
        result,
        config=config,
        crypto_stop_coverage_violations=crypto_stop_coverage_violations,
    )


def build_session_bundle(
    *,
    config: CryptoSessionConfig,
    session_date: dt.date,
    tick_results: list[TickResult],
    signal_snapshot: SignalSnapshot | None = None,
) -> dict[str, Any]:
    """Build a run bundle for one completed session."""
    return {
        "schema_version": 1,
        "source": "crypto_session",
        "session_date": session_date.isoformat(),
        "mode": config.mode,
        "tick_cadence_seconds": config.tick_cadence_seconds,
        "sleeve_budget_usd": config.sleeve_budget_usd,
        "n_ticks": len(tick_results),
        "n_entries_allowed": sum(1 for t in tick_results if t.entries_allowed),
        "n_entries_blocked": sum(1 for t in tick_results if not t.entries_allowed),
        "signal_snapshot_digest": (
            signal_snapshot.digest() if signal_snapshot else None
        ),
        "ticks": [t.to_jsonable() for t in tick_results],
    }


def watermark_for_session(session_date: dt.date) -> dt.datetime:
    """Return the bar-close watermark for a given session date.

    Session D may only consume bars through D-1's close, which is
    D 00:00:00 UTC (the end of the D-1 UTC day).
    """
    return dt.datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        tzinfo=dt.timezone.utc,
    )
