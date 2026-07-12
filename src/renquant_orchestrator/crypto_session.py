"""24/7 crypto session scheduler (D-C11).

Manages always-open trading sessions for the crypto sleeve. Each session
spans one UTC calendar day (00:00-24:00 UTC). The scheduler ticks at a
configurable cadence (default 900s / 15 min) and gates entries via a
``renquant_common.pipeline`` Task/Job/Pipeline chain (round-3 self-fix):

1. Config enabled flag (``crypto_trading.enabled``)
2. Env flag (``RENQUANT_CRYPTO_TRADING``, default OFF)
3. Kill-switch file absent (``data/crypto/kill_switch``)
4. Mode must be ``live`` or ``paper`` for entries (shadow produces records only)
5. Live mode additionally requires a SEPARATE, explicit live-authorization
   marker file (paper stays reachable via config alone)
6. Quiet interval elapsed
7. Signal snapshot present for the current session
8. Watermark validated (no future bars, not stale)
9. Fingerprint fields (universe/model/calibrator) are non-empty, non-placeholder
10. Signal digest verified against a PERSISTED artifact-ref sidecar file
    (loaded + schema/producer-id validated from disk — never a caller-supplied
    in-memory value)
11. Protective stop-coverage ready: PERSISTED report (loaded + schema/
    freshness/environment validated from disk), fail-closed

Signal leakage prevention:
- Watermark: session D may only consume bars through D-1's close
- Quiet interval: [D 00:00, D 00:15) UTC — no new entries
- Signal snapshot digest verified against a digest read from a real artifact
  file on disk, not an in-memory value the caller can fabricate
- Stop-coverage evidence is likewise read from a real file execution is
  expected to have written — this module never imports renquant_execution

Design reference: crypto RFC §3.5, merged as orchestrator PR #453.
Review history: PR #497 (Codex round 1 + round 2, CHANGES_REQUESTED),
PR #501 round 3 self-fix (this revision) closing the trust-boundary gaps
Codex flagged twice: caller-fabricable digest/stop-coverage evidence,
unvalidated fingerprint fields, no pipeline-primitive integration, and no
distinct live-mode authorization chain.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from renquant_common import Job, Pipeline, Task


CRYPTO_ENV_FLAG = "RENQUANT_CRYPTO_TRADING"
CRYPTO_KILL_SWITCH_RELPATH = "data/crypto/kill_switch"
DEFAULT_TICK_CADENCE_SECONDS = 900
DEFAULT_QUIET_INTERVAL_MINUTES = 15
DEFAULT_NTFY_TOPIC = "renquant-crypto"

# Documented convention for the execution-side stop-coverage sidecar path.
# This module never resolves this path itself by default (no CWD-relative
# fallback) — callers/wrappers must pass the resolved path explicitly to
# evaluate_tick, matching the fail-closed philosophy (see load_stop_coverage_report).
DEFAULT_STOP_COVERAGE_RELPATH = "data/crypto/stop_coverage_report.json"


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

# ── Fingerprint validation ───────────────────────────────────────────────────

_PLACEHOLDER_FINGERPRINT_VALUES = frozenset({
    "missing", "unknown", "todo", "tbd", "n/a", "na", "none", "null", "nil",
    "fixme", "changeme", "placeholder", "xxx", "<unset>", "unset",
})


def _is_valid_fingerprint(value: str | None) -> bool:
    """Reject empty, whitespace-only, and known placeholder fingerprint values.

    Exact-match (post strip+lowercase) against a placeholder blocklist — NOT
    substring matching, so legitimate hashes like "test_hash" are not
    mistakenly rejected.
    """
    if value is None or not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.lower() in _PLACEHOLDER_FINGERPRINT_VALUES:
        return False
    return True


def validate_signal_contract(snapshot: SignalSnapshot) -> tuple[bool, str]:
    """Validate universe/model/calibrator fingerprints are real, non-placeholder values.

    Fail-closed: an empty string, whitespace, or a known placeholder token
    (e.g. "MISSING", "UNKNOWN", "TODO") in ANY of the three fingerprint fields
    blocks the gate — these must never flow into ``digest()`` unvalidated.
    """
    for field_name, value in (
        ("universe_hash", snapshot.universe_hash),
        ("model_content_sha256", snapshot.model_content_sha256),
        ("calibrator_content_sha256", snapshot.calibrator_content_sha256),
    ):
        if not _is_valid_fingerprint(value):
            return False, (
                f"invalid fingerprint {field_name}={value!r} — empty/whitespace/"
                f"placeholder fingerprints are not permitted"
            )
    return True, "fingerprints valid"


def _looks_like_sha256_hex(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in value)


# ── Signal artifact ref: real persisted provenance ──────────────────────────

ARTIFACT_REF_SCHEMA_VERSION = 1


class ArtifactRefError(RuntimeError):
    """Raised when a signal artifact ref sidecar file is missing or invalid."""


@dataclass(frozen=True)
class SignalArtifactRef:
    """Provenance reference for the expected signal artifact.

    Instances should normally be constructed via ``load_signal_artifact_ref``,
    which loads and validates this from a real JSON sidecar file that an
    upstream signal producer wrote. Constructing this directly (as tests may
    do to build fixtures for the loader to read) does not by itself grant
    trust — ``evaluate_tick`` only accepts a PATH and always goes through the
    loader, so a caller can no longer fabricate an in-memory ref that
    trivially matches its own snapshot.

    ``__post_init__`` enforces cheap construction-time invariants (non-empty
    fields, ``schema_version >= 1``) regardless of how the instance was
    built. ``validate()`` is a further, structural (not cryptographic) check
    — does the referenced ``artifact_path`` still exist, does
    ``schema_version`` match what this module currently understands —
    layered ON TOP of what ``load_signal_artifact_ref`` already verifies
    (that check is called automatically by the loader; it is exposed here
    too for any caller that constructs a ref directly).
    """

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
        """Structural check: does the referenced artifact still exist on
        disk, and does schema_version match the current version. This is
        NOT the cryptographic check (that's ``validate_digest`` against
        ``expected_digest``) — it catches a dangling/stale reference."""
        if not Path(self.artifact_path).exists():
            return False, f"artifact_path does not exist: {self.artifact_path}"
        if self.schema_version != ARTIFACT_REF_SCHEMA_VERSION:
            return False, (
                f"schema_version mismatch: got {self.schema_version}, "
                f"expected {ARTIFACT_REF_SCHEMA_VERSION}"
            )
        return True, "artifact ref valid"


def load_signal_artifact_ref(path: Path) -> SignalArtifactRef:
    """Load + validate a persisted signal artifact ref sidecar JSON file.

    Expected JSON schema (schema_version=1)::

        {
          "schema_version": 1,
          "producer_run_id": "<non-empty, non-placeholder run id>",
          "expected_digest": "<sha256 hex digest of the SignalSnapshot the producer emitted>",
          "artifact_path": "<optional informational path to the underlying signal artifact>"
        }

    If ``artifact_path`` is omitted, it defaults to the sidecar file's own
    path (which trivially exists); if given explicitly, it must point to a
    real, still-existing file (checked via ``SignalArtifactRef.validate()``,
    called automatically at the end of this loader) — catching a stale/
    dangling reference to a signal artifact that has since been moved or
    deleted.

    Fail-closed: missing file / unreadable file / unparseable JSON / non-dict
    body / schema_version mismatch / missing-or-placeholder producer_run_id /
    missing-or-malformed expected_digest / dangling artifact_path all raise
    ``ArtifactRefError``. Callers MUST catch this and treat it as an
    entries-blocked condition — never silently proceed with a default/
    assumed value.
    """
    path = Path(path)
    if not path.exists():
        raise ArtifactRefError(f"signal artifact ref file not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactRefError(f"signal artifact ref file unreadable: {path}: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ArtifactRefError(f"signal artifact ref file malformed JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ArtifactRefError(f"signal artifact ref file is not a JSON object: {path}")

    schema_version = raw.get("schema_version")
    if schema_version != ARTIFACT_REF_SCHEMA_VERSION:
        raise ArtifactRefError(
            f"signal artifact ref schema_version mismatch: expected "
            f"{ARTIFACT_REF_SCHEMA_VERSION}, got {schema_version!r} ({path})"
        )

    producer_run_id = raw.get("producer_run_id")
    if not _is_valid_fingerprint(producer_run_id):
        raise ArtifactRefError(
            f"signal artifact ref producer_run_id missing/placeholder: "
            f"{producer_run_id!r} ({path})"
        )

    expected_digest = raw.get("expected_digest")
    if not isinstance(expected_digest, str) or not _looks_like_sha256_hex(expected_digest):
        raise ArtifactRefError(
            f"signal artifact ref expected_digest missing/malformed "
            f"(expected 64-char sha256 hex): {expected_digest!r} ({path})"
        )

    artifact_path = raw.get("artifact_path")
    if artifact_path is not None and not isinstance(artifact_path, str):
        raise ArtifactRefError(f"signal artifact ref artifact_path must be a string: {artifact_path!r} ({path})")

    ref = SignalArtifactRef(
        expected_digest=expected_digest.lower(),
        artifact_path=str(artifact_path) if artifact_path is not None else str(path),
        schema_version=schema_version,
        producer_run_id=producer_run_id,
    )
    ref_ok, ref_reason = ref.validate()
    if not ref_ok:
        raise ArtifactRefError(f"signal artifact ref failed validate(): {ref_reason} ({path})")
    return ref


# ── Stop coverage: real persisted execution-side evidence ───────────────────

STOP_COVERAGE_SCHEMA_VERSION = 1
_KNOWN_ENVIRONMENTS = frozenset({"live", "paper"})


class StopCoverageError(RuntimeError):
    """Raised when a stop-coverage report sidecar file is missing or invalid."""


@dataclass(frozen=True)
class StopCoverageReport:
    """Typed execution-side protective-order coverage report.

    Instances should normally be constructed via ``load_stop_coverage_report``,
    which loads and validates this from a real JSON file that
    ``renquant_execution`` (or its stage-0 battery) is expected to have
    written. This module NEVER imports renquant_execution — the contract is
    a pure file boundary.

    ``__post_init__`` enforces cheap construction-time invariants (non-empty
    strings, non-negative counts) regardless of how the instance was built.
    ``validate()`` is a further structural check (environment is a
    live-trading environment; timestamp is timezone-aware) layered ON TOP of
    what ``load_stop_coverage_report`` already verifies (called automatically
    by the loader; exposed here too for direct-construction callers).
    """

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
        """Structural check: environment must be a live-trading environment
        (shadow never reaches this gate — see StopCoverageGateTask — so a
        stop-coverage report is only meaningful for live/paper), and
        timestamp_utc must be timezone-aware (a naive timestamp cannot be
        safely compared against ``now_utc`` for freshness)."""
        if self.environment not in ("live", "paper"):
            return False, f"environment must be live or paper, got {self.environment}"
        if self.timestamp_utc.tzinfo is None:
            return False, "timestamp_utc must be timezone-aware"
        return True, "stop coverage valid"

    def is_fresh(self, now_utc: dt.datetime, max_age_seconds: int = 300) -> bool:
        age = (now_utc - self.timestamp_utc).total_seconds()
        return 0 <= age <= max_age_seconds


def load_stop_coverage_report(path: Path) -> StopCoverageReport:
    """Load + validate a persisted execution-side stop-coverage report.

    Pure file-contract boundary: renquant_execution (or its battery script)
    is expected to WRITE this JSON file after checking protective-order
    coverage on the broker side. This module never imports renquant_execution
    and never talks to a broker directly — see Codex round-2 finding #2.

    Expected JSON schema (schema_version=1), suggested default path
    ``data/crypto/stop_coverage_report.json`` (see ``DEFAULT_STOP_COVERAGE_RELPATH``,
    not auto-applied by this loader — callers pass the resolved path explicitly)::

        {
          "schema_version": 1,
          "timestamp_utc": "<ISO-8601 UTC timestamp, MUST include a UTC offset>",
          "environment": "live"|"paper",
          "account_id": "<non-empty, non-placeholder trading account identifier>",
          "positions_covered": <int >= 0>,
          "violations": <int >= 0>,
          "source_version": "<non-empty, non-placeholder producer identifier>"
        }

    Fail-closed: missing file / unreadable / unparseable JSON / non-dict body /
    schema_version mismatch / unparseable OR timezone-naive timestamp /
    environment not live-or-paper / missing-or-placeholder account_id /
    invalid positions_covered or violations / missing-or-placeholder
    source_version all raise ``StopCoverageError`` (the last two checks are
    additionally enforced via ``StopCoverageReport.validate()``, called
    automatically at the end of this loader). Freshness (age vs. tick
    ``now_utc``) is checked separately by the caller via ``is_fresh`` since
    the loader has no notion of "now."
    """
    path = Path(path)
    if not path.exists():
        raise StopCoverageError(f"stop coverage report file not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StopCoverageError(f"stop coverage report file unreadable: {path}: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StopCoverageError(f"stop coverage report malformed JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise StopCoverageError(f"stop coverage report is not a JSON object: {path}")

    schema_version = raw.get("schema_version")
    if schema_version != STOP_COVERAGE_SCHEMA_VERSION:
        raise StopCoverageError(
            f"stop coverage report schema_version mismatch: expected "
            f"{STOP_COVERAGE_SCHEMA_VERSION}, got {schema_version!r} ({path})"
        )

    timestamp_raw = raw.get("timestamp_utc")
    try:
        timestamp_utc = dt.datetime.fromisoformat(str(timestamp_raw))
    except (TypeError, ValueError) as exc:
        raise StopCoverageError(
            f"stop coverage report timestamp_utc unparseable: {timestamp_raw!r} ({path})"
        ) from exc
    if timestamp_utc.tzinfo is None:
        # Fail-closed rather than silently assuming UTC: an execution-side
        # report is untrusted input, and a naive timestamp is ambiguous
        # about which wall-clock it represents. Matches StopCoverageReport.validate().
        raise StopCoverageError(
            f"stop coverage report timestamp_utc is not timezone-aware: "
            f"{timestamp_raw!r} ({path})"
        )

    environment = raw.get("environment")
    if environment not in _KNOWN_ENVIRONMENTS:
        raise StopCoverageError(
            f"stop coverage report environment unknown/invalid: {environment!r} "
            f"(expected one of {sorted(_KNOWN_ENVIRONMENTS)}) ({path})"
        )

    account_id = raw.get("account_id")
    if not _is_valid_fingerprint(account_id):
        raise StopCoverageError(
            f"stop coverage report account_id missing/placeholder: {account_id!r} ({path})"
        )

    positions_covered = raw.get("positions_covered")
    if (
        not isinstance(positions_covered, int)
        or isinstance(positions_covered, bool)
        or positions_covered < 0
    ):
        raise StopCoverageError(
            f"stop coverage report positions_covered invalid: {positions_covered!r} ({path})"
        )

    violations = raw.get("violations")
    if not isinstance(violations, int) or isinstance(violations, bool) or violations < 0:
        raise StopCoverageError(f"stop coverage report violations invalid: {violations!r} ({path})")

    source_version = raw.get("source_version")
    if not _is_valid_fingerprint(source_version):
        raise StopCoverageError(
            f"stop coverage report source_version missing/placeholder: {source_version!r} ({path})"
        )

    report = StopCoverageReport(
        timestamp_utc=timestamp_utc,
        environment=environment,
        account_id=account_id,
        positions_covered=positions_covered,
        violations=violations,
        source_version=source_version,
    )
    report_ok, report_reason = report.validate()
    if not report_ok:
        raise StopCoverageError(f"stop coverage report failed validate(): {report_reason} ({path})")
    return report


# ── Live-mode authorization: separate evidence chain ─────────────────────────

LIVE_AUTHORIZATION_SCHEMA_VERSION = 1


def _parse_utc_datetime_or_none(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def check_live_authorization(
    path: Path | None,
    now_utc: dt.datetime,
) -> tuple[bool, str]:
    """Validate the distinct live-mode authorization marker.

    Live-mode entries require a SEPARATE authorization file beyond the
    ordinary triple gate + ``mode`` config value — this keeps live
    categorically harder to reach than paper, per Codex round-2 finding #5
    ("Keep paper eligibility only behind a distinct environment=paper
    evidence chain. Live should remain separately authorized..."). Paper mode
    must never call this gate — it stays reachable via config alone.

    Expected JSON schema (schema_version=1)::

        {
          "schema_version": 1,
          "authorized": true,
          "authorized_at": "<ISO-8601 UTC timestamp>",
          "expires_at": "<ISO-8601 UTC timestamp>"
        }

    ``expires_at`` is REQUIRED (not optional) by design — a stale
    authorization must not silently persist forever; every grant needs an
    explicit bound. Fail-closed: missing path / missing file / unreadable /
    malformed JSON / non-dict body / schema mismatch / ``authorized`` not
    exactly ``true`` / unparseable timestamps / ``now_utc`` outside
    ``[authorized_at, expires_at)`` all block live entries.
    """
    if path is None:
        return False, "live authorization requires live_authorization_path to be configured — none set"
    path = Path(path)
    if not path.exists():
        return False, f"live authorization file not found: {path}"
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"live authorization file unreadable: {path}: {exc}"
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return False, f"live authorization file malformed JSON: {path}: {exc}"
    if not isinstance(raw, dict):
        return False, f"live authorization file is not a JSON object: {path}"

    schema_version = raw.get("schema_version")
    if schema_version != LIVE_AUTHORIZATION_SCHEMA_VERSION:
        return False, (
            f"live authorization schema_version mismatch: expected "
            f"{LIVE_AUTHORIZATION_SCHEMA_VERSION}, got {schema_version!r} ({path})"
        )

    if raw.get("authorized") is not True:
        return False, f"live authorization not granted (authorized != true) ({path})"

    authorized_at = _parse_utc_datetime_or_none(raw.get("authorized_at"))
    if authorized_at is None:
        return False, f"live authorization authorized_at unparseable: {raw.get('authorized_at')!r} ({path})"

    expires_at = _parse_utc_datetime_or_none(raw.get("expires_at"))
    if expires_at is None:
        return False, f"live authorization expires_at unparseable/missing: {raw.get('expires_at')!r} ({path})"

    if now_utc < authorized_at:
        return False, f"live authorization not yet active (authorized_at={authorized_at.isoformat()}) ({path})"
    if now_utc >= expires_at:
        return False, f"live authorization expired (expires_at={expires_at.isoformat()}) ({path})"

    return True, "live authorization valid"


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
    pipeline_steps: tuple[dict[str, Any], ...] = field(default_factory=tuple)

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
            "pipeline_steps": list(self.pipeline_steps),
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
    live_authorization_path: Path | None = None

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
            live_authorization_path=(
                Path(crypto["live_authorization_path"])
                if crypto.get("live_authorization_path")
                else None
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
    """Validate watermark: timezone-aware, no future bars, not stale beyond threshold."""
    if snapshot.bar_watermark_utc.tzinfo is None:
        return False, (
            "bar_watermark_utc is not timezone-aware — cannot safely compare "
            "to the session watermark (naive-vs-aware comparisons raise, they "
            "don't fail closed cleanly)"
        )
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


# ── Gate pipeline: Task/Job/Pipeline primitives (renquant_common.pipeline) ──


@dataclass
class TickContext:
    """Mutable per-tick context shared across the entry-gate pipeline.

    ``artifact_ref_path``/``stop_coverage_path`` are PATHS, not pre-built
    objects — every gate goes through the validating loader
    (``load_signal_artifact_ref`` / ``load_stop_coverage_report``) so a
    caller can no longer fabricate an in-memory ref/report that trivially
    satisfies the check.
    """

    config: CryptoSessionConfig
    now_utc: dt.datetime
    signal_snapshot: SignalSnapshot | None = None
    artifact_ref_path: Path | None = None
    stop_coverage_path: Path | None = None

    session_date: dt.date = field(init=False)
    window: SessionWindow = field(init=False)

    entries_allowed: bool = field(init=False, default=True)
    reason: str = field(init=False, default="entries allowed")
    is_quiet: bool = field(init=False, default=False)
    is_kill_switched: bool = field(init=False, default=False)
    signal_snapshot_digest: str | None = field(init=False, default=None)
    blocked: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.session_date = current_session_date(self.now_utc)
        self.window = SessionWindow.for_date(
            self.session_date, quiet_minutes=self.config.quiet_interval_minutes
        )

    def block(self, reason: str) -> None:
        """Record the first gate failure; the first reason wins."""
        if self.blocked:
            return
        self.blocked = True
        self.entries_allowed = False
        self.reason = reason


class _GateJob(Job):
    """Base Job that auto-skips once an earlier gate has blocked entries.

    Each gate is its OWN Job (wrapping exactly one Task) rather than all
    gates sharing a single Job. This is a deliberate deviation from a literal
    reading of "composed into one Job" (see the D-C11 v3 revision note in
    doc/progress/2026-07-12-crypto-session-scheduler-v2.md): renquant_common's
    Pipeline records one PipelineStepRecord (job_name, skipped, elapsed_sec)
    PER JOB, not per Task. A single Job containing all 9 Tasks would only
    ever produce ONE audit record for the whole gate chain — collapsing
    exactly the per-gate audit trail this refactor exists to provide. Making
    each gate its own Job, all run through one Pipeline, gives a genuine
    per-gate record: which gates ran, which were short-circuit-skipped once
    an earlier gate blocked (via should_skip), and how long each took.
    """

    def should_skip(self, ctx: TickContext) -> bool:
        return ctx.blocked


class TripleGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        ctx.is_kill_switched = _kill_switch_active(ctx.config)
        ok, reason = check_triple_gate(ctx.config)
        if not ok:
            ctx.block(reason)
            return False
        return True


class TripleGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [TripleGateTask()]


class ModeGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.signal_snapshot is not None:
            ctx.signal_snapshot_digest = ctx.signal_snapshot.digest()
        if ctx.config.mode not in ("live", "paper"):
            ctx.block(
                f"mode={ctx.config.mode} — entries blocked (only live/paper admit entries)"
            )
            return False
        return True


class ModeGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [ModeGateTask()]


class LiveAuthorizationGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.config.mode != "live":
            return True  # paper stays reachable via config alone (no extra file needed)
        ok, reason = check_live_authorization(ctx.config.live_authorization_path, ctx.now_utc)
        if not ok:
            ctx.block(f"live mode blocked — {reason}")
            return False
        return True


class LiveAuthorizationGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [LiveAuthorizationGateTask()]


class QuietIntervalGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.window.in_quiet_interval(ctx.now_utc):
            ctx.is_quiet = True
            ctx.block("quiet interval — no new entries")
            return False
        return True


class QuietIntervalGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [QuietIntervalGateTask()]


class SnapshotPresenceGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.signal_snapshot is None:
            ctx.block("no signal snapshot for session — entries fail-closed")
            return False
        if ctx.signal_snapshot.session_date != ctx.session_date:
            ctx.block(
                f"signal snapshot date mismatch: "
                f"{ctx.signal_snapshot.session_date} vs {ctx.session_date}"
            )
            return False
        return True


class SnapshotPresenceGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [SnapshotPresenceGateTask()]


class WatermarkGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        ok, reason = validate_watermark(ctx.signal_snapshot, ctx.session_date)
        if not ok:
            ctx.block(reason)
            return False
        return True


class WatermarkGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [WatermarkGateTask()]


class FingerprintValidationGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        ok, reason = validate_signal_contract(ctx.signal_snapshot)
        if not ok:
            ctx.block(reason)
            return False
        return True


class FingerprintValidationGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [FingerprintValidationGateTask()]


class DigestVerificationGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.artifact_ref_path is None:
            ctx.block(
                "no artifact_ref_path supplied — entries fail-closed "
                "(digest verification requires a persisted artifact ref)"
            )
            return False
        try:
            ref = load_signal_artifact_ref(ctx.artifact_ref_path)
        except ArtifactRefError as exc:
            ctx.block(f"artifact ref invalid — entries fail-closed: {exc}")
            return False
        ok, reason = validate_digest(ctx.signal_snapshot, ref.expected_digest)
        if not ok:
            ctx.block(reason)
            return False
        return True


class DigestVerificationGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [DigestVerificationGateTask()]


class StopCoverageGateTask(Task):
    def run(self, ctx: TickContext) -> bool | None:
        if ctx.stop_coverage_path is None:
            ctx.block("no stop_coverage_path supplied — entries fail-closed")
            return False
        try:
            report = load_stop_coverage_report(ctx.stop_coverage_path)
        except StopCoverageError as exc:
            ctx.block(f"stop coverage report invalid — entries fail-closed: {exc}")
            return False
        if report.environment != ctx.config.mode:
            ctx.block(
                f"stop_coverage environment mismatch: "
                f"report={report.environment} vs config={ctx.config.mode}"
            )
            return False
        if not report.is_fresh(ctx.now_utc):
            ctx.block(
                f"stop_coverage report stale: timestamp={report.timestamp_utc.isoformat()}"
            )
            return False
        if report.violations > 0:
            ctx.block(f"stop_coverage has {report.violations} violations — entries blocked")
            return False
        return True


class StopCoverageGateJob(_GateJob):
    @property
    def tasks(self) -> list[Task]:
        return [StopCoverageGateTask()]


def _build_gate_pipeline() -> Pipeline:
    return Pipeline(
        [
            TripleGateJob(),
            ModeGateJob(),
            LiveAuthorizationGateJob(),
            QuietIntervalGateJob(),
            SnapshotPresenceGateJob(),
            WatermarkGateJob(),
            FingerprintValidationGateJob(),
            DigestVerificationGateJob(),
            StopCoverageGateJob(),
        ],
        name="crypto-session-entry-gates",
    )


# Stateless — safe to build once and reuse across ticks.
_GATE_PIPELINE = _build_gate_pipeline()


def evaluate_tick(
    *,
    config: CryptoSessionConfig,
    now_utc: dt.datetime | None = None,
    signal_snapshot: SignalSnapshot | None = None,
    artifact_ref_path: Path | None = None,
    stop_coverage_path: Path | None = None,
) -> TickResult:
    """Evaluate one scheduler tick via the ``renquant_common.pipeline`` gate chain.

    Exits are ALWAYS allowed (§5.4 precedence). Entries are gated by, in order:
    1. Triple gate (config + env + kill switch)
    2. Mode must be ``live`` or ``paper`` (shadow produces decision records only)
    3. Live mode additionally requires a distinct, explicit live-authorization
       file (paper needs no such file)
    4. Quiet interval (configurable, default 15 min of each UTC day)
    5. Valid signal snapshot for the current session
    6. Watermark validation (no future bars, no stale data)
    7. Fingerprint fields (universe/model/calibrator) non-empty, non-placeholder
    8. Digest verification against a PERSISTED artifact-ref file at
       ``artifact_ref_path`` (loaded + schema/producer-id validated)
    9. Stop-coverage: PERSISTED report at ``stop_coverage_path`` (loaded +
       schema/freshness/environment validated), zero violations

    This is a thin wrapper: it builds a ``TickContext``, runs the shared
    ``_GATE_PIPELINE``, and converts the result into the stable public
    ``TickResult`` shape (unchanged external contract; see ``to_jsonable``).
    ``TickResult.pipeline_steps`` additionally carries the per-gate
    ``PipelineStepRecord``s (job_name/skipped/elapsed_sec) for genuine
    per-gate audit — see ``build_session_bundle``.
    """
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)

    ctx = TickContext(
        config=config,
        now_utc=now_utc,
        signal_snapshot=signal_snapshot,
        artifact_ref_path=artifact_ref_path,
        stop_coverage_path=stop_coverage_path,
    )
    pipeline_result = _GATE_PIPELINE.run(ctx)

    return TickResult(
        session_date=ctx.session_date,
        tick_utc=now_utc,
        entries_allowed=ctx.entries_allowed,
        exits_allowed=True,
        reason=ctx.reason,
        signal_snapshot_digest=ctx.signal_snapshot_digest,
        is_quiet=ctx.is_quiet,
        is_kill_switched=ctx.is_kill_switched,
        pipeline_steps=tuple(
            {"job_name": s.job_name, "skipped": s.skipped, "elapsed_sec": s.elapsed_sec}
            for s in pipeline_result.steps
        ),
    )


def _aggregate_gate_stats(tick_results: list[TickResult]) -> dict[str, dict[str, int]]:
    """Roll up per-gate ran/skipped counts across a session's ticks."""
    stats: dict[str, dict[str, int]] = {}
    for tick in tick_results:
        for step in tick.pipeline_steps:
            bucket = stats.setdefault(step["job_name"], {"ran": 0, "skipped": 0})
            if step["skipped"]:
                bucket["skipped"] += 1
            else:
                bucket["ran"] += 1
    return stats


def build_session_bundle(
    *,
    config: CryptoSessionConfig,
    session_date: dt.date,
    tick_results: list[TickResult],
    signal_snapshot: SignalSnapshot | None = None,
    artifact_ref: SignalArtifactRef | None = None,
    stop_coverage: StopCoverageReport | None = None,
) -> dict[str, Any]:
    """Build a run bundle for one completed session.

    ``ticks`` entries each carry ``pipeline_steps`` (per-gate job_name/
    skipped/elapsed_sec), and ``gate_audit`` rolls those up into a
    session-level ran/skipped count per gate — a genuine per-gate audit
    trail rather than a flat dict of booleans.

    ``artifact_ref``/``stop_coverage`` are OPTIONAL, purely-informational
    provenance for the persisted bundle record — by the time a session
    bundle is assembled, the caller has already resolved and validated
    these via ``load_signal_artifact_ref``/``load_stop_coverage_report``
    during each tick; passing the (already-trusted) loaded objects here
    just captures that identity in the durable record. This function does
    NOT itself re-verify them — the trust boundary is enforced exclusively
    inside ``evaluate_tick``'s gate pipeline, never here.
    """
    return {
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
        "gate_audit": _aggregate_gate_stats(tick_results),
        "ticks": [t.to_jsonable() for t in tick_results],
    }
