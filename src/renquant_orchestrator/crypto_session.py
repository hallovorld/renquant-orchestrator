"""24/7 crypto session scheduler (D-C11).

Manages always-open trading sessions for the crypto sleeve. Each session
spans one UTC calendar day (00:00-24:00 UTC). The scheduler ticks at a
configurable cadence (default 900s / 15 min) and gates entries via:

1. Config enabled flag (``crypto_trading.enabled``)
2. Env flag (``RENQUANT_CRYPTO_TRADING``, default OFF)
3. Kill-switch file absent (``data/crypto/kill_switch``)
4. Mode must be ``live`` or ``paper`` for entries (shadow produces records only)
5. Watermark validated (no future bars)
6. Signal digest verified against expected value
7. Protective stop-coverage ready (fail-closed)

Signal leakage prevention:
- Watermark: session D may only consume bars through D-1's close
- Quiet interval: [D 00:00, D 00:15) UTC — no new entries
- Signal snapshot digest verified against expected artifact digest

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
DEFAULT_QUIET_INTERVAL_MINUTES = 15
DEFAULT_NTFY_TOPIC = "renquant-crypto"


@dataclass(frozen=True)
class SessionWindow:
    """One UTC calendar-day session boundary."""

    session_date: dt.date
    open_utc: dt.datetime
    close_utc: dt.datetime
    quiet_end_utc: dt.datetime

    @classmethod
    def for_date(cls, d: dt.date, *, quiet_minutes: int = DEFAULT_QUIET_INTERVAL_MINUTES) -> SessionWindow:
        open_utc = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
        close_utc = open_utc + dt.timedelta(days=1)
        quiet_end = open_utc + dt.timedelta(minutes=quiet_minutes)
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


MAX_WATERMARK_STALENESS_DAYS = 2


CURRENT_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SignalArtifactRef:
    """Provenance reference for the expected signal artifact."""

    expected_digest: str
    artifact_path: str
    schema_version: int
    producer_run_id: str

    def __post_init__(self) -> None:
        if not self.expected_digest or not self.expected_digest.strip():
            raise ValueError("expected_digest must be non-empty")
        if not self.artifact_path or not self.artifact_path.strip():
            raise ValueError("artifact_path must be non-empty")
        if self.schema_version < 1:
            raise ValueError(f"schema_version must be >= 1, got {self.schema_version}")
        if not self.producer_run_id or not self.producer_run_id.strip():
            raise ValueError("producer_run_id must be non-empty")

    def validate(self) -> tuple[bool, str]:
        if not Path(self.artifact_path).exists():
            return False, f"artifact_path does not exist: {self.artifact_path}"
        if self.schema_version != CURRENT_ARTIFACT_SCHEMA_VERSION:
            return False, (
                f"schema_version mismatch: got {self.schema_version}, "
                f"expected {CURRENT_ARTIFACT_SCHEMA_VERSION}"
            )
        return True, "artifact ref valid"


@dataclass(frozen=True)
class StopCoverageReport:
    """Typed execution-side protective-order coverage report."""

    timestamp_utc: dt.datetime
    environment: str
    account_id: str
    positions_covered: int
    violations: int
    source_version: str

    def __post_init__(self) -> None:
        if not self.environment or not self.environment.strip():
            raise ValueError("environment must be non-empty")
        if not self.account_id or not self.account_id.strip():
            raise ValueError("account_id must be non-empty")
        if self.positions_covered < 0:
            raise ValueError(f"positions_covered must be >= 0, got {self.positions_covered}")
        if self.violations < 0:
            raise ValueError(f"violations must be >= 0, got {self.violations}")
        if not self.source_version or not self.source_version.strip():
            raise ValueError("source_version must be non-empty")

    def validate(self) -> tuple[bool, str]:
        if self.environment not in ("live", "paper"):
            return False, f"environment must be live or paper, got {self.environment}"
        if self.timestamp_utc.tzinfo is None:
            return False, "timestamp_utc must be timezone-aware"
        return True, "stop coverage valid"

    def is_fresh(self, now_utc: dt.datetime, max_age_seconds: int = 300) -> bool:
        age = (now_utc - self.timestamp_utc).total_seconds()
        return 0 <= age <= max_age_seconds


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
    quiet_interval_minutes: int = DEFAULT_QUIET_INTERVAL_MINUTES

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
                crypto.get("quiet_interval_minutes", DEFAULT_QUIET_INTERVAL_MINUTES)
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


def validate_watermark(
    snapshot: SignalSnapshot,
    session_date: dt.date,
    *,
    max_staleness_days: int = MAX_WATERMARK_STALENESS_DAYS,
) -> tuple[bool, str]:
    """Validate watermark: no future bars AND not stale beyond threshold."""
    max_watermark = watermark_for_session(session_date)
    if snapshot.bar_watermark_utc > max_watermark:
        return False, (
            f"bar_watermark_utc {snapshot.bar_watermark_utc.isoformat()} "
            f"exceeds session {session_date} max {max_watermark.isoformat()} "
            f"— would include future bars"
        )
    min_watermark = max_watermark - dt.timedelta(days=max_staleness_days)
    if snapshot.bar_watermark_utc < min_watermark:
        return False, (
            f"bar_watermark_utc {snapshot.bar_watermark_utc.isoformat()} "
            f"is stale (>{max_staleness_days}d behind session {session_date} "
            f"min {min_watermark.isoformat()}) — incomplete data"
        )
    return True, "watermark valid"


def validate_digest(
    snapshot: SignalSnapshot,
    expected_digest: str,
) -> tuple[bool, str]:
    """Verify snapshot digest matches the expected artifact-path digest.

    Fail-closed on mismatch.
    """
    actual = snapshot.digest()
    if actual != expected_digest:
        return False, (
            f"digest mismatch: expected={expected_digest[:16]}..., "
            f"actual={actual[:16]}... — signal snapshot may have been modified"
        )
    return True, "digest verified"


def validate_signal_contract(
    snapshot: SignalSnapshot,
) -> tuple[bool, str]:
    """Validate fingerprint completeness on a signal snapshot."""
    if not snapshot.universe_hash:
        return False, "signal snapshot missing universe_hash"
    if not snapshot.model_content_sha256:
        return False, "signal snapshot missing model_content_sha256"
    if not snapshot.calibrator_content_sha256:
        return False, "signal snapshot missing calibrator_content_sha256"
    if snapshot.bar_watermark_utc.tzinfo is None:
        return False, "bar_watermark_utc is not timezone-aware"
    return True, "signal contract valid"


def evaluate_tick(
    *,
    config: CryptoSessionConfig,
    now_utc: dt.datetime | None = None,
    signal_snapshot: SignalSnapshot | None = None,
    artifact_ref: SignalArtifactRef | None = None,
    stop_coverage: StopCoverageReport | None = None,
) -> TickResult:
    """Evaluate one scheduler tick.

    Exits are ALWAYS allowed (§5.4 precedence). Entries are gated by:
    1. Triple gate (config + env + kill switch)
    2. Mode must be ``live`` or ``paper`` (shadow produces decision records only)
    3. Quiet interval (configurable, default 15 min of each UTC day)
    4. Valid signal snapshot for the current session
    5. Watermark validation (no future bars, no stale data)
    6. Digest verification against ``artifact_ref`` (typed provenance)
    7. ``stop_coverage`` report: typed, versioned, fresh, zero violations
    """
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    session_d = current_session_date(now_utc)
    window = SessionWindow.for_date(
        session_d, quiet_minutes=config.quiet_interval_minutes
    )

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

    if config.mode not in ("live", "paper"):
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=f"mode={config.mode} — entries blocked (only live/paper admit entries)",
            signal_snapshot_digest=(
                signal_snapshot.digest() if signal_snapshot else None
            ),
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

    contract_ok, contract_reason = validate_signal_contract(signal_snapshot)
    if not contract_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=contract_reason,
            signal_snapshot_digest=signal_snapshot.digest(),
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

    wm_ok, wm_reason = validate_watermark(signal_snapshot, session_d)
    if not wm_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=wm_reason,
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    if artifact_ref is None:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason="no artifact_ref supplied — entries fail-closed (digest verification required)",
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    ref_ok, ref_reason = artifact_ref.validate()
    if not ref_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=ref_reason,
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    digest_ok, digest_reason = validate_digest(
        signal_snapshot, artifact_ref.expected_digest
    )
    if not digest_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=digest_reason,
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    if stop_coverage is None:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason="no stop_coverage report — entries fail-closed",
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    cov_ok, cov_reason = stop_coverage.validate()
    if not cov_ok:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=cov_reason,
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    if stop_coverage.environment != config.mode:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=(
                f"stop_coverage environment mismatch: "
                f"report={stop_coverage.environment} vs config={config.mode}"
            ),
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    if not stop_coverage.is_fresh(now_utc):
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=(
                f"stop_coverage report stale: "
                f"timestamp={stop_coverage.timestamp_utc.isoformat()}"
            ),
            signal_snapshot_digest=signal_snapshot.digest(),
        )

    if stop_coverage.violations > 0:
        return TickResult(
            session_date=session_d,
            tick_utc=now_utc,
            entries_allowed=False,
            exits_allowed=True,
            reason=f"stop_coverage has {stop_coverage.violations} violations — entries blocked",
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
    artifact_ref: SignalArtifactRef | None = None,
    stop_coverage: StopCoverageReport | None = None,
) -> dict[str, Any]:
    """Build a run bundle for one completed session."""
    bundle: dict[str, Any] = {
        "schema_version": 2,
        "source": "crypto_session",
        "session_date": session_date.isoformat(),
        "environment": config.mode,
        "mode": config.mode,
        "tick_cadence_seconds": config.tick_cadence_seconds,
        "quiet_interval_minutes": config.quiet_interval_minutes,
        "sleeve_budget_usd": config.sleeve_budget_usd,
        "n_ticks": len(tick_results),
        "n_entries_allowed": sum(1 for t in tick_results if t.entries_allowed),
        "n_entries_blocked": sum(1 for t in tick_results if not t.entries_allowed),
        "signal_snapshot_digest": (
            signal_snapshot.digest() if signal_snapshot else None
        ),
        "artifact_ref": (
            {
                "expected_digest": artifact_ref.expected_digest,
                "artifact_path": artifact_ref.artifact_path,
                "schema_version": artifact_ref.schema_version,
                "producer_run_id": artifact_ref.producer_run_id,
            }
            if artifact_ref
            else None
        ),
        "stop_coverage": (
            {
                "timestamp_utc": stop_coverage.timestamp_utc.isoformat(),
                "environment": stop_coverage.environment,
                "account_id": stop_coverage.account_id,
                "positions_covered": stop_coverage.positions_covered,
                "violations": stop_coverage.violations,
                "source_version": stop_coverage.source_version,
            }
            if stop_coverage
            else None
        ),
        "ticks": [t.to_jsonable() for t in tick_results],
    }
    return bundle
