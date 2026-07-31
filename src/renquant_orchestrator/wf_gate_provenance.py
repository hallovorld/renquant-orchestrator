"""The daily run bundle's ``wf_gate_provenance`` block. (GOAL-5 AC6, R4)

WHY IT EXISTS. AC6's interim obligation (R3) is that every in-scope gate PR carries the
override's provenance **in the run bundle**. Measured 2026-07-31 across the seven
`run_type=daily_full` bundles on disk: **0 of 7 carry any override-provenance key, and 0
mention `wf_gate` at all.** The obligation could not be met, because the daily bundle had
no such field — `PersistDailyRunBundleTask` builds an ad hoc dict and, unlike the
native/bridge live-bundle path, it is not run through ``validate_live_run_bundle``.

So a run that served under an operator override recorded nothing about it. When the
override is later questioned, the run bundle — the artifact kept precisely to answer
"what was in force" — is silent.

ABSENT IS NOT CLEAN. This block is **tri-state and additive**, following the
``serving_bundle_provenance`` / ``g4_session_bundle_block`` idiom already used in this
bundle: it always writes a ``status``, and "no artifact" and "artifact with no gate
stamp" are DIFFERENT statuses. A block that simply omitted itself when it found nothing
would be indistinguishable from a clean gate.

WHICH KEY IT READS. The canonical location is ``metadata.wf_gate_metadata``; a legacy
top-level copy exists on some artifacts and the two are known to disagree (twin registry
R8). Presence of the canonical key decides — never truthiness, or an emptied stamp
resurrects the legacy value — and the key that answered is RECORDED, so the ambiguity is
visible in the bundle rather than resolved silently.

NEVER RAISES. A provenance recorder that can abort the daily run is a worse defect than
the gap it closes. Every failure path returns a status.
"""

from __future__ import annotations

from typing import Any

CANONICAL_KEY = "metadata.wf_gate_metadata"
LEGACY_KEY = "wf_gate_metadata (legacy top-level)"

#: The override fields AC6 requires a run to be able to answer for.
PROVENANCE_FIELDS = (
    "passed",
    "gate_verdict_before_override",
    "operator_authorized_override",
    "override_applied_at",
    "override_reason",
    "diagnostic_only",
    "gate_version",
)

STATUS_NO_ARTIFACT = "no_artifact_manifest"
STATUS_NO_GATE_BLOCK = "artifact_carries_no_gate_stamp"
STATUS_PRESENT = "present"


def _gate_block(manifest: Any) -> tuple[dict | None, str]:
    """The gate block and which key answered, or ``(None, "")``."""
    if not isinstance(manifest, dict):
        return None, ""
    meta = manifest.get("metadata")
    if isinstance(meta, dict) and "wf_gate_metadata" in meta:
        # PRESENCE of the canonical key ends the search -- we do NOT fall through to
        # the legacy copy. A present-but-empty (or malformed) canonical block means
        # "no usable stamp", not "look somewhere else": falling through would seal a
        # run with a dead value from a copy the gate stopped writing.
        #
        # Returning `{}` here instead of None was a real bug in this module's first
        # version -- the caller checks `block is None`, so an empty dict read as
        # PRESENT. Same presence-vs-truthiness confusion codex caught on orch#683,
        # reproduced in the module written to avoid it.
        block = meta["wf_gate_metadata"]
        return (block if isinstance(block, dict) and block else None), CANONICAL_KEY
    block = manifest.get("wf_gate_metadata")
    if isinstance(block, dict) and block:
        return block, LEGACY_KEY
    return None, ""


def wf_gate_provenance(artifact_manifest: Any | None = None) -> dict[str, Any]:
    """Build the block. Additive, absent-tolerant, and never raises."""
    if not isinstance(artifact_manifest, dict) or not artifact_manifest:
        return {
            "status": STATUS_NO_ARTIFACT,
            "note": ("no artifact manifest on this run — this is not evidence that the "
                     "gate passed, only that no artifact was resolved to read it from"),
        }

    block, source = _gate_block(artifact_manifest)
    if block is None:
        return {
            "status": STATUS_NO_GATE_BLOCK,
            "source_key_checked": [CANONICAL_KEY, LEGACY_KEY],
            "source_key": source or None,
            "note": ("the resolved artifact carries no usable gate stamp. An empty "
                     "canonical block counts as no stamp and is NOT backfilled from the "
                     "legacy copy — twin registry R8"),
        }

    out: dict[str, Any] = {
        "status": STATUS_PRESENT,
        "source_key": source,
        "fields_absent": [f for f in PROVENANCE_FIELDS if f not in block],
    }
    for field in PROVENANCE_FIELDS:
        value = block.get(field)
        if isinstance(value, (bool, int, float, str)):
            out[field] = value
    return out
