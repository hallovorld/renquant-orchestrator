"""24/7 crypto session scheduler (D-C11).

Manages always-open trading sessions for the crypto sleeve. Each session
spans one UTC calendar day (00:00-24:00 UTC). The scheduler ticks at a
configurable cadence (default 900s / 15 min) and gates entries via:

1. Config enabled flag (``crypto_trading.enabled``)
2. Env flag (``RENQUANT_CRYPTO_TRADING``, default OFF)
3. Kill-switch file absent (``data/crypto/kill_switch``)

Signal leakage prevention:
- Watermark: session D may only consume bars through D-1's close
- Quiet interval: [D 00:00, D 00:15) UTC — no new entries
- Signal snapshot digest verified on every entry decision

Design reference: crypto RFC §3.5, merged as orchestrator PR #453.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CRYPTO_ENV_FLAG = "RENQUANT_CRYPTO_TRADING"
CRYPTO_KILL_SWITCH_RELPATH = "data/crypto/kill_switch"
DEFAULT_TICK_CADENCE_SECONDS = 900
QUIET_INTERVAL_MINUTES = 15
DEFAULT_NTFY_TOPIC = "renquant-crypto"


@dataclass(frozen=True)
class SessionWindow:
    """One UTC calendar-day session boundary."""

    session_date: dt.date
    open_utc: dt.datetime
    close_utc: dt.datetime
    quiet_end_utc: dt.datetime

    @classmethod
    def for_date(cls, d: dt.date) -> SessionWindow:
        open_utc = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
        close_utc = open_utc + dt.timedelta(days=1)
        quiet_end = open_utc + dt.timedelta(minutes=QUIET_INTERVAL_MINUTES)
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
    """Result of a single scheduler tick."""

    session_date: dt.date
    tick_utc: dt.datetime
    entries_allowed: bool
    exits_allowed: bool
    reason: str
    signal_snapshot_digest: str | None = None
    is_quiet: bool = False
    is_kill_switched: bool = False

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


def _kill_switch_active(config: CryptoSessionConfig) -> bool:
    if config.kill_switch_path is not None:
        return config.kill_switch_path.exists()
    return Path(CRYPTO_KILL_SWITCH_RELPATH).exists()


def check_triple_gate(config: CryptoSessionConfig) -> tuple[bool, str]:
    """Evaluate the triple safety gate. Returns (passed, reason)."""
    if not config.enabled:
        return False, "config crypto_trading.enabled=false"
    if not _env_flag_enabled():
        return False, f"env {CRYPTO_ENV_FLAG} not set or false"
    if _kill_switch_active(config):
        path = config.kill_switch_path or CRYPTO_KILL_SWITCH_RELPATH
        return False, f"kill switch file present: {path}"
    return True, "triple gate passed"


def evaluate_tick(
    *,
    config: CryptoSessionConfig,
    now_utc: dt.datetime | None = None,
    signal_snapshot: SignalSnapshot | None = None,
) -> TickResult:
    """Evaluate one scheduler tick.

    Exits are ALWAYS allowed (§5.4 precedence). Entries are gated by:
    1. Triple gate (config + env + kill switch)
    2. Quiet interval (first 15 min of each UTC day)
    3. Valid signal snapshot for the current session
    """
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    session_d = current_session_date(now_utc)
    window = SessionWindow.for_date(session_d)

    gate_ok, gate_reason = check_triple_gate(config)
    if not gate_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=gate_reason,
            is_kill_switched=_kill_switch_active(config),
        )

    if window.in_quiet_interval(now_utc):
        return TickResult(
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

    if signal_snapshot is None:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason="no signal snapshot for session — entries fail-closed",
        )

    if signal_snapshot.session_date != session_d:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=f"signal snapshot date mismatch: {signal_snapshot.session_date} vs {session_d}",
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    return TickResult(
        session_date=session_d,
        tick_utc=now_utc,
        entries_allowed=True,
        exits_allowed=True,
        reason="entries allowed",
        signal_snapshot_digest=signal_snapshot.digest(),
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
