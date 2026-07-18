"""Run-bundle binding to the transactional serving-pair bundle (GOAL-5 AC4).

Phase 3 PR-C of the bundle-transactionality RFC (RenQuant#492,
``doc/design/2026-07-17-artifact-bundle-transactionality.md``). RFC §2.2:
"every daily run's persisted run bundle records ``{bundle_id,
manifest_digest, member digests, pointer_generation}`` so any historical
run can be replayed against the exact archived bundle"; §5 assigns that
recording to this repo (the existing run-bundle provenance surface —
``daily.PersistDailyRunBundleTask``).

NO production bundle store exists yet — migration is gated on the RFC §3
census, NOT on this phase. The binding is therefore an OPTIONAL
provenance block: while the store is not deployed the daily run records
an EXPLICIT ``{"bundle_store": "not_deployed"}`` marker (a stated fact,
distinguishable forever from "this run predates the field" — absence —
and from a resolution that silently went missing), and its behavior is
otherwise unchanged. Once a run resolves a registered bundle, the same
helper records the four §2.2 fields fail-closed: a partially-shaped
resolution raises rather than persisting incomplete provenance, because a
run bundle with a half-recorded binding cannot be replayed and is worse
than an honest marker.

``resolved`` is duck-typed against the renquant-artifacts resolution
results (``ResolvedBundle`` / ``PublishResult``: ``.bundle_id``,
``.generation``, ``.manifest`` with ``.manifest_digest`` + ``.members``
of per-member ``{sha256, bytes}``) so this module needs no store import
and the daily path stays inert until the census-gated migration wires a
real resolution in.
"""
from __future__ import annotations

from typing import Any, Mapping

#: ``bundle_store`` marker values (stable strings; part of the run-bundle
#: surface consumers like the GC reference query and replay tooling read).
BUNDLE_STORE_NOT_DEPLOYED = "not_deployed"
BUNDLE_STORE_RESOLVED = "resolved"

#: The §2.2 binding fields recorded for a resolved bundle.
BINDING_FIELDS = (
    "bundle_id",
    "manifest_digest",
    "member_digests",
    "pointer_generation",
)


def _member_digest_entry(name: str, digest: Any) -> dict[str, Any]:
    if isinstance(digest, Mapping):
        sha256, nbytes = digest.get("sha256"), digest.get("bytes")
    else:
        sha256 = getattr(digest, "sha256", None)
        nbytes = getattr(digest, "bytes", None)
    if not isinstance(sha256, str) or not sha256:
        raise ValueError(
            f"resolved bundle member {name!r} has no sha256 digest; refusing "
            "to record partial run-bundle binding provenance (RFC §2.2)"
        )
    if not isinstance(nbytes, int) or isinstance(nbytes, bool) or nbytes < 0:
        raise ValueError(
            f"resolved bundle member {name!r} has no byte size; refusing to "
            "record partial run-bundle binding provenance (RFC §2.2)"
        )
    return {"sha256": sha256, "bytes": nbytes}


def serving_bundle_provenance(resolved: Any | None = None) -> dict[str, Any]:
    """Build the run bundle's ``serving_bundle`` provenance block.

    ``resolved is None`` (the CURRENT daily reality — no production bundle
    store is deployed; RFC §3 census gates migration) returns the explicit
    marker ``{"bundle_store": "not_deployed"}``.

    Otherwise ``resolved`` must expose the full §2.2 identity —
    ``bundle_id``, ``manifest.manifest_digest``, ``manifest.members``
    (per-member ``{sha256, bytes}``), and an integer ``generation`` (the
    ACTIVE pointer generation at resolution; run bundles record it so
    pointer flips are totally ordered and stale-pointer rollback is
    detectable). Fail-closed: any missing/malformed piece raises
    ``ValueError`` — never persist a partial binding. A resolution with
    ``generation=None`` (an archive lookup that bypassed the pointer) is
    refused for the same reason: §2.2 binds runs to the pointer state they
    served from.
    """
    if resolved is None:
        return {"bundle_store": BUNDLE_STORE_NOT_DEPLOYED}

    bundle_id = getattr(resolved, "bundle_id", None)
    if not isinstance(bundle_id, str) or not bundle_id:
        raise ValueError(
            "resolved bundle has no bundle_id; refusing to record partial "
            "run-bundle binding provenance (RFC §2.2)"
        )

    manifest = getattr(resolved, "manifest", None)
    manifest_digest = getattr(manifest, "manifest_digest", None)
    if not isinstance(manifest_digest, str) or not manifest_digest:
        raise ValueError(
            f"resolved bundle {bundle_id} has no manifest_digest; refusing "
            "to record partial run-bundle binding provenance (RFC §2.2)"
        )

    members = getattr(manifest, "members", None)
    if not isinstance(members, Mapping) or not members:
        raise ValueError(
            f"resolved bundle {bundle_id} has no member digest map; refusing "
            "to record partial run-bundle binding provenance (RFC §2.2)"
        )
    member_digests = {
        str(name): _member_digest_entry(str(name), digest)
        for name, digest in sorted(members.items())
    }

    generation = getattr(resolved, "generation", None)
    if not isinstance(generation, int) or isinstance(generation, bool):
        raise ValueError(
            f"resolved bundle {bundle_id} has no integer pointer generation "
            "(generation=None means the resolution bypassed the ACTIVE "
            "pointer); a daily run must bind to the pointer state it served "
            "from (RFC §2.2/§2.3 pointer format)"
        )

    return {
        "bundle_store": BUNDLE_STORE_RESOLVED,
        "bundle_id": bundle_id,
        "manifest_digest": manifest_digest,
        "member_digests": member_digests,
        "pointer_generation": generation,
    }


__all__ = [
    "BINDING_FIELDS",
    "BUNDLE_STORE_NOT_DEPLOYED",
    "BUNDLE_STORE_RESOLVED",
    "serving_bundle_provenance",
]
