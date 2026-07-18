"""Per-epoch / per-role paired-session telemetry for the two-arm harness.

RenQuant prereg v5 (#494, ``doc/experiments/2026-07-17-equal-weight-
deployment-prereg-v5.md``) §4.7 rule 4 — "Mechanical checkability": the
harness telemetry must report ``n_paired_sessions`` per epoch and per role
(**pilot / terminal / burned**) so the ≥40-pilot prerequisite and every
hygiene exclusion are auditable at activation time from the recorded
manifests alone.

Derivation inputs (ALL read-only):

1. **Harness records** — per-session bundles
   (``<root>/<date>/shadow_ab_session_bundle.json``) and printed session
   payloads (``<root>/session_<date>.json``), both at the experiment output
   root and under ``archive/``. Printed payloads are byte-duplicates of the
   bundle plus volatile keys; records are deduplicated on their canonical
   content with volatile keys stripped.
2. **Epoch registry** — archived epoch freezes
   (``archive/epoch<N>-freeze-*/shadow_ab_freeze.json``) plus the live root
   freeze (the CURRENT epoch; when the root freeze does not exist yet the
   current epoch is enumerated as unminted — the runner self-creates it on
   the first valid session).
3. **Role boundaries** — COMMITTED registration / activation manifest
   files, supplied by path (never inferred from harness state).

IMMUTABLE MANIFEST BINDING: a filesystem path is mutable — a later edit at
the same path must never be able to change historical role assignment.
Therefore (a) a supplied registration manifest MUST carry its source
provenance (``source_repository`` + ``source_commit``; for registration
``pilot_registration_commit`` doubles as the commit) and, when it
references an external burned-sessions manifest, a
``burned_sessions_manifest_sha256`` commitment that the loaded file's raw
bytes must hash to; (b) a supplied activation manifest MUST additionally
carry ``registration_manifest_sha256`` binding it to the exact
registration content it activates; (c) callers may pin either file's
content with an expected SHA-256 (CLI ``--registration-manifest-sha256`` /
``--activation-manifest-sha256``; wrapper env
``RENQUANT_SHADOW_AB_REGISTRATION_MANIFEST_SHA256`` /
``RENQUANT_SHADOW_AB_ACTIVATION_MANIFEST_SHA256``). Every load records the
actual digest in the report's ``manifest_bindings`` block. ANY resolve or
verify failure raises ``EpochTelemetryError`` — fail closed: no report
exists, the recorded payload carries ``telemetry_status: unavailable``,
every session remains burned, and activation is ineligible.

TELEMETRY STATUS (fail-closed activation evidence): every successful
report stamps ``telemetry_status: "complete"`` only after the per-epoch /
per-role counts re-reconcile against the per-session role assignments
(``counts_reconciled``); anything else — a derivation error, a binding
failure, an unreconciled count — surfaces as ``telemetry_status:
"unavailable"``. The activation validator MUST require
``telemetry_status == "complete"`` (plus reconciled counts) before any
report may support the ≥40-pilot condition; a partial/error report can
never support it.

SAFE DEFAULT (§4.7 rule 1): **no registration manifest → every session is
BURNED.** Roles cannot exist before the pilot-registration commit, and a
session whose epoch attribution cannot be PROVEN against a recorded freeze
fingerprint can never be promoted to pilot/terminal — fallback attribution
(archive location / root location) always resolves to burned.

Epoch attribution order:

1. ``freeze_fingerprint`` — the record's stamped ``subrepo_pins`` +
   ``orchestrator_commit`` equal exactly one epoch freeze's frozen values
   (the only attribution strong enough to carry a pilot/terminal role);
2. ``archive_location`` — the record was retired inside an
   ``epoch<N>-freeze-*`` archive (heuristic: later epoch archives also
   sweep stale home files, so this proves scope, not world → burned);
3. ``pre_epoch_archive`` — the record sits in a non-epoch archive
   (pre-arming / strayed attempts) → burned;
4. ``root_location`` — the record only exists at the live root → the
   current epoch, but still burned unless the freeze fingerprint matched.

Role assignment for a deduplicated VALID pair record:

- listed in the burned-sessions manifest → **burned**;
- attribution weaker than ``freeze_fingerprint`` → **burned**;
- epoch differs from the registration ``epoch_id`` → **burned**
  (§4.7 rule 2: no cross-epoch pooling);
- does not STRICTLY postdate ``registered_at`` → **burned** (§4.7 two-stage
  start: the pilot manifest is prospective-only). The record time is the
  sealed ``decision_snapshot.as_of`` when present; otherwise the session
  date at 00:00:00 UTC — the conservative earliest reading, so a
  registration-day session without a sealed as-of burns rather than
  sneaking into the pilot;
- else **terminal** when an activation manifest exists and the record
  strictly postdates ``activated_at`` in the activation epoch;
- else **pilot**.

Non-valid records (precheck aborts, invalidated pairs, VOID) are never
paired sessions — they are reported per epoch as ``n_excluded_records``,
mirroring the harness's own attempted/excluded counter semantics.

This module is derivation-only: it never mutates harness state. The runner
exposes the derived report on the existing reporting surface (the returned
session payload + a sidecar JSON next to ``shadow_ab_counters.json``), and
``main`` provides the standalone audit CLI
(``renquant-orchestrator shadow-ab-epoch-report``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .native_live_context import canonical_json_sha256
from .shadow_ab_runner import BUNDLE_FILENAME, FREEZE_FILENAME, PROTOCOL

EPOCH_ROLE_COUNTERS_FILENAME = "shadow_ab_epoch_role_counters.json"

PREREG_REF = (
    "RenQuant doc/experiments/2026-07-17-equal-weight-deployment-prereg-v5.md "
    "§4.7 rule 4"
)

ROLE_PILOT = "pilot"
ROLE_TERMINAL = "terminal"
ROLE_BURNED = "burned"
ROLES = (ROLE_PILOT, ROLE_TERMINAL, ROLE_BURNED)

#: The activation validator must require exactly this value before a report
#: may support the >=40-pilot condition (no partial/error report ever can).
TELEMETRY_STATUS_COMPLETE = "complete"
TELEMETRY_STATUS_UNAVAILABLE = "unavailable"

#: Keys that differ between the on-disk bundle and the printed session
#: payload for the SAME attempt — stripped before content-dedup so the two
#: copies collapse into one record.
VOLATILE_RECORD_KEYS = ("bundle_path", "epoch_role_counters")

_EPOCH_DIR_RE = re.compile(r"^epoch(\d+)-freeze-")
_SESSION_FILE_RE = re.compile(r"^session_(\d{4}-\d{2}-\d{2})\.json$")


class EpochTelemetryError(ValueError):
    """A malformed registration/activation manifest or derivation input."""


# --- small utilities --------------------------------------------------------------


def _parse_utc(value: str, *, what: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpochTelemetryError(f"{what} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _load_json_with_digest(
    path: Path, *, what: str, expected_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Load a JSON object and the SHA-256 of its RAW bytes (fail closed).

    The digest is the immutable-binding surface: when ``expected_sha256``
    is supplied (a caller pin or an inter-manifest commitment) the loaded
    bytes must hash to it, otherwise the load raises — a later edit at the
    same filesystem path must never silently change role assignment.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EpochTelemetryError(f"{what} unreadable: {path}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        expected = str(expected_sha256).removeprefix("sha256:").strip().lower()
        if digest != expected:
            raise EpochTelemetryError(
                f"{what} content digest mismatch: {path} hashes to "
                f"sha256:{digest} but the binding commitment requires "
                f"sha256:{expected} (immutable manifest binding — a later "
                "edit at the same path must not change role assignment)"
            )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EpochTelemetryError(f"{what} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EpochTelemetryError(f"{what} must be a JSON object: {path}")
    return payload, digest


def _load_json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


# --- epoch registry ---------------------------------------------------------------


@dataclass(frozen=True)
class Epoch:
    epoch_id: str
    number: int
    scope: Path
    freeze: dict[str, Any] | None
    archived: bool

    @property
    def minted(self) -> bool:
        return self.freeze is not None


def enumerate_epochs(output_root: Path) -> list[Epoch]:
    """Archived ``epoch<N>-freeze-*`` scopes + the live root as current epoch."""
    epochs: list[Epoch] = []
    max_number = 0
    archive = output_root / "archive"
    if archive.is_dir():
        for entry in sorted(archive.iterdir()):
            match = _EPOCH_DIR_RE.match(entry.name)
            if not entry.is_dir() or match is None:
                continue
            number = int(match.group(1))
            max_number = max(max_number, number)
            epochs.append(Epoch(
                epoch_id=f"epoch-{number}",
                number=number,
                scope=entry,
                freeze=_load_json_or_none(entry / FREEZE_FILENAME),
                archived=True,
            ))
    current = max_number + 1
    epochs.append(Epoch(
        epoch_id=f"epoch-{current}",
        number=current,
        scope=output_root,
        freeze=_load_json_or_none(output_root / FREEZE_FILENAME),
        archived=False,
    ))
    return epochs


# --- session record collection ----------------------------------------------------


@dataclass
class SessionRecord:
    session_date: str
    status: str
    payload: dict[str, Any]
    sources: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.status == "valid"


def _record_paths(output_root: Path) -> list[Path]:
    paths: list[Path] = []

    def _scan_scope(scope: Path) -> None:
        for entry in sorted(scope.iterdir()):
            if entry.is_file() and _SESSION_FILE_RE.match(entry.name):
                paths.append(entry)
            elif entry.is_dir():
                bundle = entry / BUNDLE_FILENAME
                if bundle.is_file():
                    paths.append(bundle)

    if output_root.is_dir():
        _scan_scope(output_root)
        archive = output_root / "archive"
        if archive.is_dir():
            for scope in sorted(archive.iterdir()):
                if scope.is_dir():
                    _scan_scope(scope)
    return paths


def collect_session_records(output_root: Path) -> list[SessionRecord]:
    """Every recorded session attempt, deduplicated on canonical content."""
    records: dict[str, SessionRecord] = {}
    for path in _record_paths(output_root):
        payload = _load_json_or_none(path)
        if payload is None:
            continue
        if payload.get("protocol") != PROTOCOL or "session_date" not in payload:
            continue
        canon = {
            k: v for k, v in payload.items() if k not in VOLATILE_RECORD_KEYS
        }
        key = canonical_json_sha256(canon)
        rel = str(path.relative_to(output_root))
        record = records.get(key)
        if record is None:
            records[key] = SessionRecord(
                session_date=str(payload["session_date"]),
                status=str(payload.get("status") or "invalidated"),
                payload=canon,
                sources=[rel],
            )
        else:
            record.sources.append(rel)
    return sorted(
        records.values(), key=lambda r: (r.session_date, r.sources[0]),
    )


# --- epoch attribution ------------------------------------------------------------

ATTRIBUTION_FREEZE = "freeze_fingerprint"
ATTRIBUTION_ARCHIVE = "archive_location"
ATTRIBUTION_PRE_EPOCH = "pre_epoch_archive"
ATTRIBUTION_ROOT = "root_location"

PRE_EPOCH_ID = "pre-epoch"


def _record_world(payload: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    for label in ("a", "b"):
        arm = (payload.get("arms") or {}).get(label) or {}
        pins = arm.get("subrepo_pins")
        commit = arm.get("orchestrator_commit")
        if isinstance(pins, dict) and pins and commit:
            return dict(pins), str(commit)
    return None


def attribute_epoch(
    record: SessionRecord, epochs: list[Epoch], output_root: Path,
) -> tuple[str, str]:
    """Return ``(epoch_id, attribution_method)`` for one deduplicated record."""
    world = _record_world(record.payload)
    if world is not None:
        pins, commit = world
        matches = [
            epoch for epoch in epochs
            if epoch.freeze is not None
            and epoch.freeze.get("subrepo_pins") == pins
            and epoch.freeze.get("orchestrator_commit") == commit
        ]
        if len(matches) == 1:
            return matches[0].epoch_id, ATTRIBUTION_FREEZE
        if len(matches) > 1:
            # Identical worlds across a refreeze: scope decides, weakly.
            for epoch in matches:
                if epoch.archived and any(
                    _under(output_root / src, epoch.scope) for src in record.sources
                ):
                    return epoch.epoch_id, ATTRIBUTION_ARCHIVE
            return matches[-1].epoch_id, ATTRIBUTION_ARCHIVE
    archived = [epoch for epoch in epochs if epoch.archived]
    for epoch in archived:
        if any(_under(output_root / src, epoch.scope) for src in record.sources):
            return epoch.epoch_id, ATTRIBUTION_ARCHIVE
    archive_root = output_root / "archive"
    if any(_under(output_root / src, archive_root) for src in record.sources):
        return PRE_EPOCH_ID, ATTRIBUTION_PRE_EPOCH
    return epochs[-1].epoch_id, ATTRIBUTION_ROOT


def _under(path: Path, scope: Path) -> bool:
    try:
        path.relative_to(scope)
    except ValueError:
        return False
    return True


# --- role manifests ---------------------------------------------------------------


@dataclass(frozen=True)
class RegistrationManifest:
    path: str
    epoch_id: str
    registered_at: dt.datetime
    pilot_registration_commit: str | None
    burned_sessions: tuple[tuple[str, str], ...]  # (session_date, epoch_id)
    sha256: str
    source_repository: str
    source_commit: str
    burned_sessions_manifest: str | None
    burned_sessions_manifest_sha256: str | None


@dataclass(frozen=True)
class ActivationManifest:
    path: str
    epoch_id: str
    activated_at: dt.datetime
    sha256: str
    source_repository: str
    source_commit: str
    registration_manifest_sha256: str


def _burned_entries(
    entries: Any, *, what: str,
) -> list[tuple[str, str]]:
    if not isinstance(entries, list):
        raise EpochTelemetryError(f"{what}: 'sessions' must be a list")
    burned: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "session_date" not in entry:
            raise EpochTelemetryError(
                f"{what}: every burned entry needs a 'session_date'"
            )
        burned.append(
            (str(entry["session_date"]), str(entry.get("epoch_id") or "*"))
        )
    return burned


def load_registration_manifest(
    path: str | Path, *, expected_sha256: str | None = None,
) -> RegistrationManifest:
    manifest_path = Path(path)
    payload, digest = _load_json_with_digest(
        manifest_path, what="registration manifest",
        expected_sha256=expected_sha256,
    )
    for key in ("epoch_id", "registered_at"):
        if not payload.get(key):
            raise EpochTelemetryError(
                f"registration manifest missing required key {key!r}: "
                f"{manifest_path}"
            )
    source_repository = payload.get("source_repository")
    source_commit = (
        payload.get("source_commit") or payload.get("pilot_registration_commit")
    )
    if not source_repository or not source_commit:
        raise EpochTelemetryError(
            "registration manifest must carry its source provenance — "
            "'source_repository' and 'source_commit' (or a stamped "
            "'pilot_registration_commit') — so the registration record binds "
            f"an immutable repository commit, not a mutable path: "
            f"{manifest_path}"
        )
    burned: list[tuple[str, str]] = []
    if "burned_sessions" in payload:
        burned.extend(_burned_entries(
            payload["burned_sessions"],
            what=f"registration manifest {manifest_path}",
        ))
    burned_manifest_ref: str | None = None
    burned_manifest_sha256: str | None = None
    if payload.get("burned_sessions_manifest"):
        burned_manifest_ref = str(payload["burned_sessions_manifest"])
        committed_sha = payload.get("burned_sessions_manifest_sha256")
        if not committed_sha:
            raise EpochTelemetryError(
                "registration manifest references an external burned-sessions "
                "manifest without a 'burned_sessions_manifest_sha256' content "
                "commitment (immutable manifest binding): "
                f"{manifest_path}"
            )
        burned_path = Path(burned_manifest_ref)
        if not burned_path.is_absolute():
            burned_path = manifest_path.parent / burned_path
        burned_payload, burned_manifest_sha256 = _load_json_with_digest(
            burned_path, what="burned-sessions manifest",
            expected_sha256=str(committed_sha),
        )
        burned.extend(_burned_entries(
            burned_payload.get("sessions"),
            what=f"burned-sessions manifest {burned_path}",
        ))
    return RegistrationManifest(
        path=str(manifest_path),
        epoch_id=str(payload["epoch_id"]),
        registered_at=_parse_utc(
            payload["registered_at"], what="registration manifest registered_at",
        ),
        pilot_registration_commit=(
            str(payload["pilot_registration_commit"])
            if payload.get("pilot_registration_commit") else None
        ),
        burned_sessions=tuple(burned),
        sha256=digest,
        source_repository=str(source_repository),
        source_commit=str(source_commit),
        burned_sessions_manifest=burned_manifest_ref,
        burned_sessions_manifest_sha256=burned_manifest_sha256,
    )


def load_activation_manifest(
    path: str | Path, *, expected_sha256: str | None = None,
) -> ActivationManifest:
    manifest_path = Path(path)
    payload, digest = _load_json_with_digest(
        manifest_path, what="activation manifest",
        expected_sha256=expected_sha256,
    )
    activated = payload.get("activated_at") or payload.get("start_date")
    if not payload.get("epoch_id") or not activated:
        raise EpochTelemetryError(
            "activation manifest requires 'epoch_id' and "
            f"'activated_at' (or 'start_date'): {manifest_path}"
        )
    source_repository = payload.get("source_repository")
    source_commit = payload.get("source_commit")
    if not source_repository or not source_commit:
        raise EpochTelemetryError(
            "activation manifest must carry its source provenance — "
            "'source_repository' and 'source_commit' — so the activation "
            "record binds an immutable repository commit, not a mutable "
            f"path: {manifest_path}"
        )
    registration_sha = payload.get("registration_manifest_sha256")
    if not registration_sha:
        raise EpochTelemetryError(
            "activation manifest must carry 'registration_manifest_sha256' "
            "binding it to the exact registration content it activates "
            f"(immutable manifest binding): {manifest_path}"
        )
    return ActivationManifest(
        path=str(manifest_path),
        epoch_id=str(payload["epoch_id"]),
        activated_at=_parse_utc(
            activated, what="activation manifest activated_at",
        ),
        sha256=digest,
        source_repository=str(source_repository),
        source_commit=str(source_commit),
        registration_manifest_sha256=(
            str(registration_sha).removeprefix("sha256:").strip().lower()
        ),
    )


# --- role derivation --------------------------------------------------------------


def _record_time(record: SessionRecord) -> dt.datetime:
    snapshot = record.payload.get("decision_snapshot") or {}
    as_of = snapshot.get("as_of")
    if as_of:
        try:
            return _parse_utc(as_of, what="decision_snapshot.as_of")
        except EpochTelemetryError:
            pass
    # Conservative earliest reading: the session date at 00:00:00 UTC.
    return _parse_utc(f"{record.session_date}T00:00:00+00:00", what="session_date")


def _assign_role(
    record: SessionRecord,
    *,
    epoch_id: str,
    attribution: str,
    registration: RegistrationManifest | None,
    activation: ActivationManifest | None,
) -> tuple[str, str]:
    """Role + auditable reason for one VALID pair record."""
    if registration is None:
        return ROLE_BURNED, "no registration manifest (safe default: all burned)"
    for burned_date, burned_epoch in registration.burned_sessions:
        if burned_date == record.session_date and burned_epoch in ("*", epoch_id):
            return ROLE_BURNED, (
                "listed in the committed burned-sessions manifest "
                "(§4.7 rule 1)"
            )
    if attribution != ATTRIBUTION_FREEZE:
        return ROLE_BURNED, (
            f"epoch attribution '{attribution}' is not proven against a "
            "recorded freeze fingerprint"
        )
    if epoch_id != registration.epoch_id:
        return ROLE_BURNED, (
            f"epoch {epoch_id} != registration epoch "
            f"{registration.epoch_id} (§4.7 rule 2: no cross-epoch pooling)"
        )
    when = _record_time(record)
    if when <= registration.registered_at:
        return ROLE_BURNED, (
            "does not strictly postdate the pilot-registration commit "
            f"({when.isoformat()} <= {registration.registered_at.isoformat()})"
        )
    if activation is not None and when > activation.activated_at:
        return ROLE_TERMINAL, (
            f"postdates activation ({activation.activated_at.isoformat()}) "
            f"in epoch {activation.epoch_id}"
        )
    return ROLE_PILOT, (
        "strictly postdates registration "
        f"({registration.registered_at.isoformat()}) in epoch "
        f"{registration.epoch_id}"
    )


def derive_epoch_role_counters(
    output_root: str | Path,
    *,
    registration_manifest: str | Path | None = None,
    activation_manifest: str | Path | None = None,
    registration_manifest_sha256: str | None = None,
    activation_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """The §4.7 rule 4 report: ``n_paired_sessions`` per epoch and per role."""
    output_root = Path(output_root)
    if registration_manifest is None and registration_manifest_sha256 is not None:
        raise EpochTelemetryError(
            "a registration-manifest sha256 pin without a registration "
            "manifest path cannot be verified (fail closed)"
        )
    if activation_manifest is None and activation_manifest_sha256 is not None:
        raise EpochTelemetryError(
            "an activation-manifest sha256 pin without an activation "
            "manifest path cannot be verified (fail closed)"
        )
    if activation_manifest is not None and registration_manifest is None:
        raise EpochTelemetryError(
            "an activation manifest without a registration manifest violates "
            "the §4.7 two-stage start (registration must come first)"
        )
    registration = (
        load_registration_manifest(
            registration_manifest, expected_sha256=registration_manifest_sha256,
        )
        if registration_manifest is not None else None
    )
    activation = (
        load_activation_manifest(
            activation_manifest, expected_sha256=activation_manifest_sha256,
        )
        if activation_manifest is not None else None
    )
    if (
        activation is not None
        and registration is not None
        and activation.registration_manifest_sha256 != registration.sha256
    ):
        raise EpochTelemetryError(
            "activation manifest is not bound to the loaded registration "
            "content: registration_manifest_sha256 "
            f"sha256:{activation.registration_manifest_sha256} != loaded "
            f"registration manifest sha256:{registration.sha256} (immutable "
            "manifest binding — all sessions stay burned, activation "
            "ineligible)"
        )
    if (
        activation is not None
        and registration is not None
        and activation.epoch_id != registration.epoch_id
    ):
        raise EpochTelemetryError(
            "pilot epoch and terminal epoch must be the SAME epoch "
            f"(§4.7 rule 2): registration={registration.epoch_id} "
            f"activation={activation.epoch_id}"
        )

    epochs = enumerate_epochs(output_root)
    records = collect_session_records(output_root)

    def _empty_bucket() -> dict[str, Any]:
        return {
            "n_paired_sessions": {role: 0 for role in ROLES},
            "n_records": 0,
            "n_excluded_records": 0,
        }

    epoch_report: dict[str, dict[str, Any]] = {}
    for epoch in epochs:
        bucket = _empty_bucket()
        bucket["minted"] = epoch.minted
        bucket["archived"] = epoch.archived
        if epoch.freeze is not None:
            bucket["frozen_at"] = epoch.freeze.get("frozen_at")
        epoch_report[epoch.epoch_id] = bucket

    totals = {role: 0 for role in ROLES}
    sessions: list[dict[str, Any]] = []
    for record in records:
        epoch_id, attribution = attribute_epoch(record, epochs, output_root)
        bucket = epoch_report.setdefault(epoch_id, _empty_bucket())
        bucket["n_records"] += 1
        entry: dict[str, Any] = {
            "session_date": record.session_date,
            "epoch_id": epoch_id,
            "attribution": attribution,
            "status": record.status,
            "sources": list(record.sources),
        }
        if record.valid:
            role, reason = _assign_role(
                record,
                epoch_id=epoch_id,
                attribution=attribution,
                registration=registration,
                activation=activation,
            )
            bucket["n_paired_sessions"][role] += 1
            totals[role] += 1
            entry["role"] = role
            entry["role_reason"] = reason
        else:
            bucket["n_excluded_records"] += 1
            entry["role"] = None
            entry["role_reason"] = (
                "not a paired session (paired-inclusion excluded this attempt)"
            )
        sessions.append(entry)

    # Reconcile the per-epoch/per-role buckets against the per-session role
    # assignments before the report may claim completeness: the activation
    # validator requires telemetry_status == "complete" AND reconciled
    # counts — no partial/error report may support the >=40 condition.
    recount = {role: 0 for role in ROLES}
    for entry in sessions:
        if entry["role"] in recount:
            recount[entry["role"]] += 1
    bucket_sums = {
        role: sum(
            bucket["n_paired_sessions"][role] for bucket in epoch_report.values()
        )
        for role in ROLES
    }
    records_sum = sum(
        bucket["n_records"] for bucket in epoch_report.values()
    )
    counts_reconciled = (
        recount == totals
        and bucket_sums == totals
        and records_sum == len(records)
    )

    manifest_bindings: dict[str, Any] = {
        "registration": {
            "path": registration.path,
            "sha256": registration.sha256,
            "source_repository": registration.source_repository,
            "source_commit": registration.source_commit,
            "pinned_sha256": registration_manifest_sha256,
            "burned_sessions_manifest": registration.burned_sessions_manifest,
            "burned_sessions_manifest_sha256": (
                registration.burned_sessions_manifest_sha256
            ),
        } if registration is not None else None,
        "activation": {
            "path": activation.path,
            "sha256": activation.sha256,
            "source_repository": activation.source_repository,
            "source_commit": activation.source_commit,
            "pinned_sha256": activation_manifest_sha256,
            "registration_manifest_sha256": (
                activation.registration_manifest_sha256
            ),
        } if activation is not None else None,
        "note": (
            "digests are SHA-256 over the loaded files' raw bytes, verified "
            "at load against every supplied commitment (caller pins, the "
            "activation->registration binding, the registration->burned-"
            "manifest binding); any resolve/verify failure raises instead of "
            "reporting — all sessions stay burned, activation ineligible"
        ),
    }

    return {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "prereg": PREREG_REF,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "output_root": str(output_root),
        "registration_manifest": registration.path if registration else None,
        "activation_manifest": activation.path if activation else None,
        "manifest_bindings": manifest_bindings,
        "safe_default_applied": registration is None,
        "safe_default_note": (
            "no committed registration manifest was supplied: every recorded "
            "session is burned (§4.7 rule 1)"
        ) if registration is None else None,
        "telemetry_status": (
            TELEMETRY_STATUS_COMPLETE if counts_reconciled
            else TELEMETRY_STATUS_UNAVAILABLE
        ),
        "counts_reconciled": counts_reconciled,
        "epochs": epoch_report,
        "totals": {
            **totals,
            "records": len(records),
        },
        "sessions": sessions,
    }


# --- CLI --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="renquant-orchestrator shadow-ab-epoch-report",
        description=(
            "derive the two-arm harness per-epoch/per-role n_paired_sessions "
            "counters (v5 prereg §4.7 rule 4) from recorded harness state + "
            "committed registration/activation manifests; read-only"
        ),
    )
    parser.add_argument(
        "--output-root", required=True,
        help="experiment session root (freeze, counters, per-session bundles)",
    )
    parser.add_argument(
        "--registration-manifest", default=None,
        help=(
            "COMMITTED pilot-registration manifest json (epoch_id, "
            "registered_at, burned_sessions[_manifest]); omitted -> every "
            "session is burned (safe default)"
        ),
    )
    parser.add_argument(
        "--activation-manifest", default=None,
        help=(
            "COMMITTED activation manifest json (epoch_id, activated_at, "
            "source provenance, registration_manifest_sha256); requires "
            "--registration-manifest (§4.7 two-stage start)"
        ),
    )
    parser.add_argument(
        "--registration-manifest-sha256", default=None,
        help=(
            "expected SHA-256 of the registration manifest's raw bytes "
            "(immutable binding pin); mismatch fails closed"
        ),
    )
    parser.add_argument(
        "--activation-manifest-sha256", default=None,
        help=(
            "expected SHA-256 of the activation manifest's raw bytes "
            "(immutable binding pin); mismatch fails closed"
        ),
    )
    parser.add_argument(
        "--output-json", default=None,
        help="also write the derived report to this path",
    )
    args = parser.parse_args(argv)
    try:
        report = derive_epoch_role_counters(
            args.output_root,
            registration_manifest=args.registration_manifest,
            activation_manifest=args.activation_manifest,
            registration_manifest_sha256=args.registration_manifest_sha256,
            activation_manifest_sha256=args.activation_manifest_sha256,
        )
    except EpochTelemetryError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


__all__ = [
    "ATTRIBUTION_ARCHIVE",
    "ATTRIBUTION_FREEZE",
    "ATTRIBUTION_PRE_EPOCH",
    "ATTRIBUTION_ROOT",
    "EPOCH_ROLE_COUNTERS_FILENAME",
    "ActivationManifest",
    "Epoch",
    "EpochTelemetryError",
    "PRE_EPOCH_ID",
    "ROLE_BURNED",
    "ROLE_PILOT",
    "ROLE_TERMINAL",
    "ROLES",
    "TELEMETRY_STATUS_COMPLETE",
    "TELEMETRY_STATUS_UNAVAILABLE",
    "RegistrationManifest",
    "SessionRecord",
    "attribute_epoch",
    "collect_session_records",
    "derive_epoch_role_counters",
    "enumerate_epochs",
    "load_activation_manifest",
    "load_registration_manifest",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
