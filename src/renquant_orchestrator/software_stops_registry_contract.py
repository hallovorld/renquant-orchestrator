"""Software-stop registry-file contract — the READ / validation half only.

Context: the software-stop registry file — the heartbeat/state file the
LIVE sell-only loop stamps and ``renquant_execution.software_stops_liveness``
(renquant-execution#29) reads via ``--data-root`` — is configured in
``deploy/com.renquant.stops-liveness.plist`` at the neutral runtime-state
root (``~/.renquant/runtime/software-stops``). The sell-only loop writer
must be migrated to stamp there (a separate R-PIN landing change) before
the pager can be armed.

The canonical registry DATA schema (``software_stops.py``) belongs to
renquant-pipeline; the checker belongs to renquant-execution. This repo
owns LOCATION only — the neutral path convention and classifier below.

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
2. A **data-root classifier** (:func:`classify_data_root`) the pager
   wrapper uses to observe — not silently accept — whether its configured
   data root is the neutral root or a legacy/umbrella-anchored path,
   producing a clearly labeled message for the latter (today's honest,
   actual production configuration).

Content correction (Codex CHANGES_REQUESTED on PR #481, 2026-07-12T04:32:57Z):
an earlier revision of this module also invented a versioned "envelope"
content schema (``schema_version`` / ``kind`` keys, ``classify_registry_file``)
that this repo does not own and that never corresponded to anything the real
writer (``renquant_pipeline.software_stops``) actually produces. Codex
correctly held that the canonical registry CONTENT contract belongs to the
producing/liveness-owning subsystem — ``renquant-pipeline`` (the schema,
``software_stops.py``) and ``renquant-execution`` (the liveness checker,
``software_stops_liveness.py``) — not orchestrator, which should schedule and
consume a versioned execution CLI/record rather than define a parallel
read-side schema. That envelope machinery has been removed. Registry CONTENT
validity is now delegated entirely to
``renquant_execution.software_stops_liveness.check()`` (and, at a lower
level, ``renquant_pipeline.software_stops._validate_snapshot`` — the real,
already-existing schema owned by the producing repo). This module owns
LOCATION only (the neutral runtime-state-root convention and the
NEUTRAL-vs-LEGACY path classifier below) — it never owns or re-derives
content schema. See ``scripts/install_stops_pager.sh`` for where that real
validator is now invoked as a fail-closed pre-install guard.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- neutral runtime-state root (mirrors deployment_manifest.deploy_state_root) ------

#: Override env var — same naming/resolution convention as
#: ``deployment_manifest.DEPLOY_STATE_ROOT_ENV``.
RUNTIME_STATE_ROOT_ENV = "RENQUANT_RUNTIME_STATE_ROOT"
#: Sibling of R-PIN's ``~/.renquant/deploy/`` (design doc §5.2).
DEFAULT_RUNTIME_STATE_ROOT = Path("~/.renquant/runtime")

SOFTWARE_STOPS_REGISTRY_DIRNAME = "software-stops"


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
