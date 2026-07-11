"""R5 persistence guard for the native live path — SHADOW-SOAK STAGE.

Addresses T6/D6-F3 (doc/design/2026-07-10-architecture-compliance-registry.md):
``native_live_run.py`` — the module that, since #107, can submit live orders
AND commit live-state/trade-journal persistence mutations — had NO
strategy/data/artifact fingerprint gate at all, against the orchestrator
CLAUDE.md hard rule ("do not silently continue without strategy/data/artifact
fingerprints"). This module implements that gate.

**Honest scope statement (Codex review r1 on #465): this stage ships
OBSERVABILITY plus OPT-IN enforcement — it does NOT protect the path.**
Arming the guard is a caller decision; an invocation that passes no guard
inputs still submits orders and mutates persistence UNVERIFIED, and is merely
stamped ``persistence_guard.armed: false`` in the audit so the unverified
state is visible per run. No unarmed broker submit or persistence mutation
may be characterized as guarded. Making the guard mandatory for
``--commit-persistence`` is the R5 default-flip — a separate, pre-registered
behavior-change step whose rollout plan (soak criteria, operator key
replacement, orchestrator self-pin) is frozen in
``doc/progress/2026-07-10-r5-native-persistence-guard.md``.

Design (the approved R5 remediation shape, verbatim from the registry):

* **Fail-closed verification (when armed) before any mutation.** Reuses the
  project's existing verification primitives — never a new hash
  implementation (calibrator/scorer triple-impl incident history):

  - :func:`renquant_orchestrator.shadow_ab_runner.load_run_manifest` /
    :func:`~renquant_orchestrator.shadow_ab_runner.verify_run_manifest`
    (#460 Codex r2): every required repo checkout must exist, sit at the
    manifest commit, and be CLEAN;
  - :func:`renquant_orchestrator.native_live_context.verify_config_artifact_shas`
    (#456): the strategy config's resolved model/calibrator artifacts must
    fingerprint (via the ONE unified ``renquant_common.model_fingerprint``
    implementation) to the shas frozen by the caller;
  - optional decision-snapshot binding: when the caller hands in the frozen
    §2a ``decision_snapshot_digest``, the inference payload's metadata must
    carry the SAME digest with ``decision_snapshot_verified: true`` (stamped
    by the digest-verified ``native-live-context`` step) — binding the order
    intents about to be executed/persisted to the verified input world.

* **SIGNED expiring operator incident token — the ONLY override.** NOT a
  standing environment variable (rejected by Codex review round 1 on the
  registry), and NOT a bare JSON file any caller could fabricate (rejected by
  Codex review r1 on #465). A token is a specific, time-bounded,
  independently verifiable authorization tied to a named incident:

  - **payload**: incident, operator, reason, ``issued_at``/``expires_at``
    (window no longer than :data:`MAX_INCIDENT_TOKEN_TTL`), and a ``scope``
    binding the EXACT ``run_id`` (single-run — any further use requires
    re-authorization), the specific failed ``checks`` being overridden, and
    the identities being overridden (``model_content_sha256`` +
    ``strategy_config_sha256``) so a token cannot be replayed against a
    different run, failure, model, or config;
  - **signature**: a detached OpenSSH signature (``ssh-keygen -Y sign``,
    namespace :data:`SIGNATURE_NAMESPACE`) over the exact token file bytes,
    verified (``ssh-keygen -Y verify``) against the COMMITTED
    ``security/persistence_guard_allowed_signers`` file with the token's
    ``operator`` as the principal. The operator's private key never exists
    in any agent-accessible location; the committed entry is a clearly
    labeled TEST-ONLY placeholder the operator must replace before the
    enforcement flip (see the rollout plan). ``ssh-keygen`` ships with
    macOS/OpenSSH — zero new runtime dependencies.

  Unsigned, forged, expired, mis-scoped, over-long, or wrong-key tokens
  NEVER unblock. Every override is stamped in full (payload + signature
  provenance) into the guard result and from there into the persistence
  audit — logged, never silent. Issuing tokens is an operator action; this
  module only validates them.

* **Shadow soak support** (R5: "shadow the fail-closed verdicts for N
  sessions first"): with ``enforce=False`` (the readonly native path) a
  failing verdict is recorded as ``would_have_blocked: true`` instead of
  raising, so would-have-blocked days can be counted before the default
  flips.

Guard-input problems (unreadable manifest/config, malformed schema) are
wiring bugs, not incidents — they raise :class:`PersistenceGuardError`
unconditionally and are NEVER token-overridable.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .native_live_context import (
    DecisionSnapshotMismatchError,
    canonical_json_sha256,
    verify_config_artifact_shas,
)
from .shadow_ab_runner import (
    GitProbe,
    ShadowABContractError,
    load_run_manifest,
    verify_run_manifest,
)

GUARD_SCHEMA_VERSION = 1

INCIDENT_TOKEN_KIND = "persistence_guard_incident_token"
INCIDENT_TOKEN_SCHEMA_VERSION = 1

#: Hard ceiling on a token's ``expires_at - issued_at`` window. A token that
#: outlives an incident window is a standing override by construction — the
#: exact mechanism the R5 correction forbids.
MAX_INCIDENT_TOKEN_TTL = dt.timedelta(hours=24)

#: OpenSSH signature namespace for incident tokens. Domain-separates these
#: signatures from every other use of the same key (a signature made for any
#: other purpose can never validate a token, and vice versa).
SIGNATURE_NAMESPACE = "renquant-persistence-guard"

#: The committed public-key registry the token signature is verified against.
#: The as-committed content is a clearly labeled TEST-ONLY placeholder; the
#: operator replaces it with their real public key before the enforcement
#: flip (rollout step — see the progress doc).
ALLOWED_SIGNERS_RELPATH = Path("security") / "persistence_guard_allowed_signers"


def default_allowed_signers_path() -> Path:
    """The committed allowed_signers file at this orchestrator checkout's root.

    Deliberately NOT a CLI flag on the run surface: the execution agent must
    not be able to point verification at a self-supplied key registry via
    arguments. (Residual risk — a locally edited checkout — is closed by the
    rollout plan's orchestrator self-pin step; see the progress doc.)
    """
    return Path(__file__).resolve().parents[2] / ALLOWED_SIGNERS_RELPATH

CHECK_RUN_MANIFEST = "run_manifest"
CHECK_ARTIFACT_SHA = "artifact_sha"
CHECK_DECISION_SNAPSHOT = "decision_snapshot"

#: The full set of failure categories an incident token may name in
#: ``scope.checks``. Anything else in a token's scope is a validation error.
OVERRIDABLE_CHECKS = (
    CHECK_RUN_MANIFEST,
    CHECK_ARTIFACT_SHA,
    CHECK_DECISION_SNAPSHOT,
)


class PersistenceGuardError(RuntimeError):
    """The persistence guard failed closed; no mutation may proceed."""


class IncidentTokenError(PersistenceGuardError):
    """An incident token was presented but rejected (never unblocks)."""


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str, problems: list[str]) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{field} must be an ISO-8601 timestamp string")
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        problems.append(f"{field} is not a valid ISO-8601 timestamp: {value!r}")
        return None
    if parsed.tzinfo is None:
        problems.append(
            f"{field} must carry an explicit UTC offset (naive timestamps "
            "make expiry ambiguous): " f"{value!r}"
        )
        return None
    return parsed.astimezone(dt.timezone.utc)


def load_incident_token(path: str | Path) -> dict[str, Any]:
    """Read a token file. Read/shape problems are hard errors (a broken token
    file must block, exactly like an absent one)."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IncidentTokenError(
            f"incident token unreadable or not JSON ({path}): {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise IncidentTokenError(f"incident token must be a JSON object: {path}")
    return payload


def verify_incident_token_signature(
    token_path: str | Path,
    *,
    operator: str,
    signature_path: str | Path | None = None,
    allowed_signers: str | Path | None = None,
    namespace: str = SIGNATURE_NAMESPACE,
) -> dict[str, Any]:
    """Verify the token file's detached OpenSSH signature (fail-closed).

    The signature must cover the EXACT token file bytes (default detached
    signature path: ``<token>.sig``, the ``ssh-keygen -Y sign`` convention),
    validate in :data:`SIGNATURE_NAMESPACE`, and chain to the token's
    ``operator`` principal in the committed allowed_signers registry. Any
    missing file, tool failure, principal mismatch, tampered payload, or
    wrong key raises :class:`IncidentTokenError` — an unsigned or unverifiable
    token is exactly as blocking as no token.

    Returns the signature provenance block stamped into the audit.
    """
    token_file = Path(token_path)
    sig_file = (
        Path(signature_path)
        if signature_path is not None
        else token_file.with_name(token_file.name + ".sig")
    )
    signers = (
        Path(allowed_signers) if allowed_signers is not None else default_allowed_signers_path()
    )
    if not sig_file.is_file():
        raise IncidentTokenError(
            f"incident token has NO detached signature ({sig_file}); unsigned "
            "tokens never unblock — sign with: ssh-keygen -Y sign "
            f"-f <operator_private_key> -n {namespace} {token_file}"
        )
    if not signers.is_file():
        raise IncidentTokenError(
            f"allowed_signers registry missing ({signers}); cannot verify any "
            "incident token"
        )
    try:
        token_bytes = token_file.read_bytes()
    except OSError as exc:
        raise IncidentTokenError(f"incident token unreadable: {exc}") from exc
    try:
        proc = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(signers),
                "-I",
                operator,
                "-n",
                namespace,
                "-s",
                str(sig_file),
            ],
            input=token_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise IncidentTokenError(
            f"cannot run ssh-keygen for signature verification: {exc}"
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise IncidentTokenError(
            "incident token signature verification FAILED for principal "
            f"{operator!r} in namespace {namespace!r} against {signers} "
            f"(forged, tampered, wrong-key, or wrong-principal tokens never "
            f"unblock): {detail}"
        )
    return {
        "signature_path": str(sig_file),
        "allowed_signers": str(signers),
        "principal": operator,
        "namespace": namespace,
        "verified": True,
    }


def validate_incident_token(
    token: Mapping[str, Any],
    *,
    run_id: str | None,
    model_content_sha256: str,
    strategy_config_sha256: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Validate an operator incident token against the R5 override contract.

    Returns the normalized token record on success; raises
    :class:`IncidentTokenError` listing EVERY problem otherwise. The contract
    (registry R5, Codex-corrected; #465 r1 identity binding): named incident
    + named operator + reason, explicit ``issued_at``/``expires_at``
    (UTC-offset-carrying ISO-8601) bounded by :data:`MAX_INCIDENT_TOKEN_TTL`,
    not yet expired, not future-dated, and a scope binding ``run_id`` (equal
    to THIS run's id — single-run authorization, reuse requires a new token),
    the REQUIRED explicit ``checks`` list being overridden, and the REQUIRED
    ``model_content_sha256`` / ``strategy_config_sha256`` identities this run
    is actually using — a token cannot authorize a different run, failure
    class, model, or config than the operator saw when signing.

    Signature verification is a SEPARATE mandatory step
    (:func:`verify_incident_token_signature`); this function validates the
    already-authenticated payload.
    """
    now = now if now is not None else _utc_now()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    problems: list[str] = []
    if token.get("kind") != INCIDENT_TOKEN_KIND:
        problems.append(
            f"kind must be {INCIDENT_TOKEN_KIND!r}, got {token.get('kind')!r}"
        )
    if token.get("schema_version") != INCIDENT_TOKEN_SCHEMA_VERSION:
        problems.append(
            "schema_version must be "
            f"{INCIDENT_TOKEN_SCHEMA_VERSION}, got {token.get('schema_version')!r}"
        )
    for field in ("incident", "operator", "reason"):
        value = token.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field} must be a non-empty string (named authorization)")

    issued_at = _parse_utc(token.get("issued_at"), "issued_at", problems)
    expires_at = _parse_utc(token.get("expires_at"), "expires_at", problems)

    checks: list[str] | None = None
    scope = token.get("scope")
    if not isinstance(scope, Mapping):
        problems.append(
            "scope must be an object binding run_id, checks, "
            "model_content_sha256, and strategy_config_sha256"
        )
    else:
        scope_run_id = scope.get("run_id")
        if not isinstance(scope_run_id, str) or not scope_run_id.strip():
            problems.append("scope.run_id must be a non-empty string")
        elif run_id is None or scope_run_id != run_id:
            problems.append(
                f"scope.run_id {scope_run_id!r} does not authorize this run "
                f"(run_id={run_id!r}); tokens are single-run — any further "
                "use requires re-authorization"
            )
        raw_checks = scope.get("checks")
        if (
            not isinstance(raw_checks, list)
            or not raw_checks
            or not all(isinstance(c, str) for c in raw_checks)
            or not set(raw_checks) <= set(OVERRIDABLE_CHECKS)
        ):
            problems.append(
                "scope.checks is REQUIRED: a non-empty list of the specific "
                f"failed checks being overridden, drawn from "
                f"{sorted(OVERRIDABLE_CHECKS)}"
            )
        else:
            checks = sorted(set(raw_checks))
        scope_model_sha = scope.get("model_content_sha256")
        if not isinstance(scope_model_sha, str) or not scope_model_sha.strip():
            problems.append(
                "scope.model_content_sha256 is REQUIRED (identity binding)"
            )
        elif scope_model_sha != model_content_sha256:
            problems.append(
                f"scope.model_content_sha256 {scope_model_sha!r} does not "
                f"match this run's frozen model sha {model_content_sha256!r}; "
                "a token cannot authorize a different model"
            )
        scope_config_sha = scope.get("strategy_config_sha256")
        if not isinstance(scope_config_sha, str) or not scope_config_sha.strip():
            problems.append(
                "scope.strategy_config_sha256 is REQUIRED (identity binding)"
            )
        elif scope_config_sha != strategy_config_sha256:
            problems.append(
                f"scope.strategy_config_sha256 {scope_config_sha!r} does not "
                "match the canonical sha of the strategy config this run "
                f"actually loaded ({strategy_config_sha256!r}); a token "
                "cannot authorize a different config"
            )

    if issued_at is not None and expires_at is not None:
        if expires_at <= issued_at:
            problems.append("expires_at must be after issued_at")
        elif expires_at - issued_at > MAX_INCIDENT_TOKEN_TTL:
            problems.append(
                f"token lifetime {expires_at - issued_at} exceeds the "
                f"{MAX_INCIDENT_TOKEN_TTL} maximum (no standing overrides)"
            )
        if now < issued_at:
            problems.append(f"token is not yet valid (issued_at {_iso(issued_at)} is in the future)")
    if expires_at is not None and now >= expires_at:
        problems.append(
            f"token EXPIRED at {_iso(expires_at)} (now {_iso(now)}); "
            "re-authorization required"
        )

    if problems:
        raise IncidentTokenError("incident token rejected: " + "; ".join(problems))

    assert issued_at is not None and expires_at is not None
    assert checks is not None
    return {
        "kind": INCIDENT_TOKEN_KIND,
        "schema_version": INCIDENT_TOKEN_SCHEMA_VERSION,
        "incident": str(token["incident"]).strip(),
        "operator": str(token["operator"]).strip(),
        "reason": str(token["reason"]).strip(),
        "issued_at": _iso(issued_at),
        "expires_at": _iso(expires_at),
        "scope": {
            "run_id": str(run_id),
            "checks": checks,
            "model_content_sha256": model_content_sha256,
            "strategy_config_sha256": strategy_config_sha256,
        },
    }


def _assert_scope_covers(
    token_record: Mapping[str, Any],
    failures: list[dict[str, str]],
) -> None:
    checks = (token_record.get("scope") or {}).get("checks") or []
    uncovered = sorted({f["check"] for f in failures} - set(checks))
    if uncovered:
        raise IncidentTokenError(
            "incident token scope does not cover failed check(s): "
            + ", ".join(uncovered)
        )


def verify_persistence_guard(
    *,
    run_manifest_json: str | Path,
    strategy_config_json: str | Path,
    model_content_sha256: str,
    calibrator_content_sha256: str | None = None,
    decision_snapshot_digest: str | None = None,
    inference_metadata: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    strategy_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    incident_token_json: str | Path | None = None,
    incident_token_signature: str | Path | None = None,
    allowed_signers: str | Path | None = None,
    enforce: bool = True,
    git_probe: GitProbe | None = None,
    fingerprint_from_path: Callable[[str | Path], str] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Run every guard check and return the verified-identities block.

    With ``enforce=True`` (any ``--execute-live`` invocation) a failing
    verdict raises :class:`PersistenceGuardError` unless a SIGNED, valid,
    unexpired incident token — signature verified against the committed
    allowed_signers registry, scope bound to this ``run_id`` and this run's
    model/config identities — covers every failed check; in which case the
    full token record plus signature provenance is stamped into the result's
    ``override`` field (logged authorization, never silent). With
    ``enforce=False`` (readonly soak) failures are recorded with
    ``would_have_blocked: true`` and nothing raises.

    ``allowed_signers`` is injectable for tests only; the run surface never
    exposes it (see :func:`default_allowed_signers_path`).

    The returned block is what :mod:`renquant_orchestrator.native_live_run`
    stamps into the run bundle's ``persistence_audit`` — the audit thereby
    binds to identities that were actually VERIFIED, not merely asserted.
    """
    now = now if now is not None else _utc_now()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    failures: list[dict[str, str]] = []

    # -- guard inputs themselves: wiring problems are never overridable ----------
    try:
        manifest = load_run_manifest(run_manifest_json)
    except ShadowABContractError as exc:
        raise PersistenceGuardError(
            f"run manifest invalid (not token-overridable): {exc}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise PersistenceGuardError(
            f"run manifest unreadable (not token-overridable): {exc}"
        ) from exc

    try:
        config = json.loads(Path(strategy_config_json).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("strategy config must be a JSON object")
    except (OSError, ValueError) as exc:
        raise PersistenceGuardError(
            f"strategy config unreadable (not token-overridable): {exc}"
        ) from exc

    # -- check 1: run-manifest pin verification (#460 primitive, fail-closed) ----
    resolved_repos: dict[str, str] | None = None
    try:
        resolved_repos = verify_run_manifest(manifest, git_probe=git_probe)
    except ShadowABContractError as exc:
        failures.append({"check": CHECK_RUN_MANIFEST, "message": str(exc)})

    # -- check 2: model/calibrator artifact shas (#456 primitive, unified hash) --
    artifacts_verified = False
    try:
        verify_config_artifact_shas(
            strategy_config_json=strategy_config_json,
            config=config,
            model_content_sha256=model_content_sha256,
            calibrator_content_sha256=calibrator_content_sha256,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            fingerprint_from_path=fingerprint_from_path,
        )
        artifacts_verified = True
    except DecisionSnapshotMismatchError as exc:
        failures.append({"check": CHECK_ARTIFACT_SHA, "message": str(exc)})

    # -- check 3 (optional): bind the inference payload to the frozen digest -----
    if decision_snapshot_digest is not None:
        meta = dict(inference_metadata or {})
        stamped = meta.get("decision_snapshot_digest")
        verified_flag = meta.get("decision_snapshot_verified")
        if stamped != decision_snapshot_digest or verified_flag is not True:
            failures.append(
                {
                    "check": CHECK_DECISION_SNAPSHOT,
                    "message": (
                        "inference payload metadata does not carry a VERIFIED "
                        "decision-snapshot digest matching the frozen value "
                        f"{decision_snapshot_digest!r}: stamped={stamped!r}, "
                        f"decision_snapshot_verified={verified_flag!r} (the "
                        "digest-verified native-live-context step stamps both)"
                    ),
                }
            )

    result: dict[str, Any] = {
        "schema_version": GUARD_SCHEMA_VERSION,
        "armed": True,
        "enforced": bool(enforce),
        "verified": not failures,
        "checked_at": _iso(now),
        "run_id": run_id,
        "run_manifest": {
            "path": str(run_manifest_json),
            "schema_version": manifest.get("schema_version"),
            "data_revision": manifest.get("data_revision"),
            "resolved_repos": resolved_repos,
        },
        "strategy_config_json": str(strategy_config_json),
        "strategy_config_sha256": canonical_json_sha256(config),
        "artifacts": {
            "model_content_sha256": model_content_sha256,
            "calibrator_content_sha256": calibrator_content_sha256,
            "verified": artifacts_verified,
        },
        "decision_snapshot_digest": decision_snapshot_digest,
        "failures": failures,
        "override": None,
    }

    if not failures:
        if incident_token_json is not None:
            result["incident_token_unused"] = str(incident_token_json)
        return result

    if not enforce:
        result["would_have_blocked"] = True
        return result

    summary = "; ".join(f"[{f['check']}] {f['message']}" for f in failures)
    if incident_token_json is None:
        raise PersistenceGuardError(
            "persistence guard FAILED CLOSED (no incident token): " + summary
        )

    token_payload = load_incident_token(incident_token_json)
    operator = token_payload.get("operator")
    if not isinstance(operator, str) or not operator.strip():
        raise IncidentTokenError(
            "incident token has no operator principal; signature cannot be "
            "verified and the token never unblocks"
        )
    # Signature FIRST: only an authenticated payload's claims are examined.
    signature_info = verify_incident_token_signature(
        incident_token_json,
        operator=operator.strip(),
        signature_path=incident_token_signature,
        allowed_signers=allowed_signers,
    )
    token_record = validate_incident_token(
        token_payload,
        run_id=run_id,
        model_content_sha256=model_content_sha256,
        strategy_config_sha256=result["strategy_config_sha256"],
        now=now,
    )
    _assert_scope_covers(token_record, failures)
    result["override"] = {
        "token_path": str(incident_token_json),
        **token_record,
        "signature": signature_info,
        "overridden_checks": sorted({f["check"] for f in failures}),
    }
    return result


__all__ = [
    "ALLOWED_SIGNERS_RELPATH",
    "CHECK_ARTIFACT_SHA",
    "CHECK_DECISION_SNAPSHOT",
    "CHECK_RUN_MANIFEST",
    "GUARD_SCHEMA_VERSION",
    "INCIDENT_TOKEN_KIND",
    "INCIDENT_TOKEN_SCHEMA_VERSION",
    "IncidentTokenError",
    "MAX_INCIDENT_TOKEN_TTL",
    "OVERRIDABLE_CHECKS",
    "PersistenceGuardError",
    "SIGNATURE_NAMESPACE",
    "default_allowed_signers_path",
    "load_incident_token",
    "validate_incident_token",
    "verify_incident_token_signature",
    "verify_persistence_guard",
]
