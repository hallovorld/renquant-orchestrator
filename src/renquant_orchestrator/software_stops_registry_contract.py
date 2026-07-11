"""Software-stop registry-file contract — the READ / validation half only.

Context (Codex CHANGES_REQUESTED on PR #481, round 3, 2026-07-11): the
software-stop registry file — the heartbeat/state file the LIVE sell-only
loop stamps and ``renquant_execution.software_stops_liveness``
(renquant-execution#29) reads via ``--data-root`` — is configured TODAY at
an explicit, umbrella-anchored path
(``RENQUANT_STOPS_PAGER_DATA_ROOT=/Users/renhao/git/github/RenQuant`` in
``deploy/com.renquant.stops-liveness.plist``, the deprecated umbrella).
Round 2 of this PR moved CODE resolution (which checkouts run the checker)
onto the R-PIN Stage-1 runtime inventory, but Codex correctly held that an
explicit umbrella DATA root is still a production dependency on the
umbrella even when code imports resolve through pins. The required fix is
an execution-owned, versioned registry-file contract at a neutral runtime
path, with the writer migrated/bridged under a SEPARATE, audited R-PIN
landing change.

THIS repo does not own that writer. The live sell-only loop that stamps the
registry file lives in the umbrella; the registry's DATA schema
(``software_stops.py`` — per-ticker fields, heartbeat semantics) lives in
renquant-pipeline; the checker lives in renquant-execution. Per CLAUDE.md's
hard boundary (no signal/decision-tree or broker internals in this repo)
and the operator's live-tree ask-first policy, migrating the actual writer
is OUT OF SCOPE here — see
``doc/progress/2026-07-11-stops-liveness-pager-package.md`` ("BLOCKING
FOLLOW-UP") for the tracked follow-up. The canonical definition of the
registry's business schema belongs in renquant-execution/renquant-pipeline,
not here.

What THIS module defines, so "consume the neutral contract" is concrete and
testable even before that follow-up lands:

1. The **neutral runtime-state root** convention — an EXACT mirror of
   :func:`renquant_orchestrator.deployment_manifest.deploy_state_root`
   (design doc's §5.2): a host-scoped root that is never inside any repo,
   resolved override-then-env-then-default, sibling to R-PIN's own
   ``~/.renquant/deploy/``. This module does not create or write to it —
   it only names the convention a migrated writer should land under
   (``~/.renquant/runtime/software-stops/<broker>.json``) and reads
   against it.
2. A **versioned envelope contract** (``schema_version`` +
   ``kind: "software-stops-registry"``) a migrated writer would stamp into
   the registry file, plus a fail-closed reader
   (:func:`classify_registry_file`) that returns an explicit
   ``unversioned``/``invalid`` verdict — never a silent pass — for a file
   lacking that envelope. Every registry file written before the writer
   migration lands is, correctly and by design, ``unversioned``.
3. A **data-root classifier** (:func:`classify_data_root`) the pager
   wrapper uses to observe — not silently accept — whether its configured
   data root is the neutral root or a legacy/umbrella-anchored path,
   producing a clearly labeled message for the latter (today's honest,
   actual production configuration).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- neutral runtime-state root (mirrors deployment_manifest.deploy_state_root) ------

#: Override env var — same naming/resolution convention as
#: ``deployment_manifest.DEPLOY_STATE_ROOT_ENV``.
RUNTIME_STATE_ROOT_ENV = "RENQUANT_RUNTIME_STATE_ROOT"
#: Sibling of R-PIN's ``~/.renquant/deploy/`` (design doc §5.2).
DEFAULT_RUNTIME_STATE_ROOT = Path("~/.renquant/runtime")

SOFTWARE_STOPS_REGISTRY_DIRNAME = "software-stops"

#: The versioned envelope a migrated writer would stamp into the registry
#: file. NOT the registry's business schema (per-ticker fields, heartbeat
#: semantics) — that stays renquant-pipeline/renquant-execution's; this is
#: only the location/versioning wrapper this repo can own.
REGISTRY_ENVELOPE_SCHEMA_VERSION = 1
REGISTRY_ENVELOPE_KIND = "software-stops-registry"

VERDICT_MISSING = "missing"
VERDICT_UNVERSIONED = "unversioned"
VERDICT_INVALID = "invalid"
VERDICT_VALID = "valid"


def runtime_state_root(override: str | Path | None = None) -> Path:
    """The neutral, host-scoped runtime-state root (never inside any repo).

    Exact mirror of ``deployment_manifest.deploy_state_root``: override,
    then ``RENQUANT_RUNTIME_STATE_ROOT``, then the default
    ``~/.renquant/runtime`` — sibling to R-PIN's own
    ``~/.renquant/deploy/``, but for state WRITTEN BY LIVE PRODUCTION
    LOOPS rather than R-PIN's own deploy/pin state.
    """
    if override is not None:
        return Path(override).expanduser()
    env = os.environ.get(RUNTIME_STATE_ROOT_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_RUNTIME_STATE_ROOT.expanduser()


def software_stops_registry_root(state_root: Path) -> Path:
    """Where a migrated writer should land registry files, one per broker."""
    return state_root / SOFTWARE_STOPS_REGISTRY_DIRNAME


def software_stops_registry_path(state_root: Path, *, broker: str) -> Path:
    return software_stops_registry_root(state_root) / f"{broker}.json"


# --- data-root classifier (path-level; no dependency on the writer's internal ------
#     relative-path layout, which belongs to another repo) --------------------------


@dataclass(frozen=True)
class DataRootVerdict:
    neutral: bool
    data_root: str
    message: str


def classify_data_root(
    data_root: str | Path, *, runtime_root: str | Path | None = None
) -> DataRootVerdict:
    """Classify a configured registry data root as NEUTRAL or LEGACY.

    NEUTRAL: the data root IS (or is inside) the neutral runtime-state
    root — i.e. the writer migration described in this module's docstring
    has landed.

    LEGACY: anything else, INCLUDING today's actual production
    configuration (the deprecated umbrella checkout). This is a fact
    observation, not a hard gate — the writer migration is a separately
    authorized change (out of scope here), so callers (the pager wrapper)
    should WARN, never abort, on a LEGACY verdict.
    """
    root = (
        Path(runtime_root).expanduser() if runtime_root is not None else runtime_state_root()
    ).resolve()
    candidate = Path(data_root).expanduser().resolve()
    is_neutral = candidate == root or candidate.is_relative_to(root)
    if is_neutral:
        return DataRootVerdict(
            neutral=True,
            data_root=str(candidate),
            message=f"NEUTRAL: {candidate} is under the neutral runtime-state root ({root})",
        )
    return DataRootVerdict(
        neutral=False,
        data_root=str(candidate),
        message=(
            f"LEGACY/UNVERSIONED registry root: {candidate} is NOT under the "
            f"neutral runtime-state root ({root}) — registry file is "
            "unversioned / at the legacy umbrella-anchored path — R-PIN "
            "writer migration not yet landed"
        ),
    )


def describe_data_root(
    data_root: str | Path, *, runtime_root: str | Path | None = None
) -> str:
    """One-line status string — lets a caller (the bash wrapper) do a
    single function call instead of unpacking the dataclass itself."""
    return classify_data_root(data_root, runtime_root=runtime_root).message


# --- registry-file ENVELOPE contract (versioning marker only) ----------------------


def registry_envelope_problems(payload: Any) -> list[str]:
    """Schema problems for the versioned envelope a migrated writer would
    stamp. Mirrors ``deployment_manifest.runtime_inventory_problems``'s
    fail-closed style. This is for a payload that CLAIMS an envelope
    (has a ``schema_version`` key at all) — a legacy file with none is
    "unversioned", not "invalid"; see :func:`classify_registry_file`."""
    if not isinstance(payload, dict):
        return ["registry file must be a JSON object"]
    problems: list[str] = []
    if payload.get("schema_version") != REGISTRY_ENVELOPE_SCHEMA_VERSION:
        problems.append(f"schema_version must be {REGISTRY_ENVELOPE_SCHEMA_VERSION}")
    if payload.get("kind") != REGISTRY_ENVELOPE_KIND:
        problems.append(f"kind must be {REGISTRY_ENVELOPE_KIND!r}")
    return problems


@dataclass(frozen=True)
class RegistryFileVerdict:
    status: str  # one of VERDICT_MISSING / VERDICT_UNVERSIONED / VERDICT_INVALID / VERDICT_VALID
    detail: str


def classify_registry_file(path: str | Path) -> RegistryFileVerdict:
    """Fail-closed read-side validator for the registry file's envelope.

    Never raises: a missing, unreadable, malformed, or unversioned file is
    an EXPLICIT verdict, never a silent pass — the "read-side validator
    that fails closed... on an unversioned or wrong-schema file" Codex
    asked for. Returns ``VERDICT_VALID`` only for a file carrying BOTH the
    correct ``schema_version`` and ``kind`` — the shape a migrated writer
    would produce. No registry file written before that migration can pass
    (by design: today's real files carry neither key).
    """
    registry_path = Path(path)
    if not registry_path.is_file():
        return RegistryFileVerdict(VERDICT_MISSING, f"no registry file at {registry_path}")
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return RegistryFileVerdict(
            VERDICT_INVALID, f"{registry_path} unreadable or not JSON: {exc}"
        )
    if not isinstance(payload, dict) or "schema_version" not in payload:
        return RegistryFileVerdict(
            VERDICT_UNVERSIONED,
            f"{registry_path} carries no versioned envelope "
            "(schema_version/kind) — legacy/pre-migration registry file",
        )
    problems = registry_envelope_problems(payload)
    if problems:
        return RegistryFileVerdict(VERDICT_INVALID, f"{registry_path}: " + "; ".join(problems))
    return RegistryFileVerdict(
        VERDICT_VALID, f"{registry_path}: valid v{REGISTRY_ENVELOPE_SCHEMA_VERSION} envelope"
    )
