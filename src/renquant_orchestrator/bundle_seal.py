"""P1 seal: publish the CURRENT 104 serving pair as bundle generation 1.

GOAL-5 AC4 migration phase **P1** ("seal") of the transactional-bundle RFC
(RenQuant#492, ``doc/design/2026-07-17-artifact-bundle-transactionality.md``;
census ``doc/design/2026-07-18-ac4-migration-census.md`` §6). P0 built the
AUTHORITATIVE store (renquant-artifacts#25/#26/#27) + the pipeline
``bundle_contract`` validator (renquant-pipeline#206). **This module is the
first real publication THROUGH that store**: it takes the current live
serving pair —

* ``panel-ltr.alpha158_fund.json`` (panel scorer, with its embedded
  ``wf_gate_metadata``),
* ``panel-rank-calibration.json`` (its pooled calibrator),

reads them VERBATIM, and publishes them as **generation 1** (a genesis
bundle, ``parent_bundle=null``) via the RFC §2.3 PREPARE/ACTIVATE writer
protocol: validator-gated (step 6 runs the pipeline pair validator through
:func:`renquant_artifacts.bundle_contract_binding.create_default_store`),
operation-log recorded (PREPARE before the ACTIVE flip, ACTIVATE bound to
it), the ACTIVE pointer flipped to gen 1.

Two P1 obligations beyond the raw publish (RFC §2.7 / census §3.4 / §6):

1. **Run-bundle provenance** — :class:`RunBundleProvenance` records exactly
   ``{bundle_id, manifest_digest, member_digests, generation}`` (RFC §2.2
   "Run-bundle binding") so any historical run replays against the exact
   archived bundle. The orchestrator hydration surface starts stamping this
   into daily run bundles at P2; the record shape is pinned here.
2. **Flat-view regeneration** — :func:`regenerate_flat_views` writes each
   active-bundle member back to its flat path as a **READ-ONLY (mode 0444)
   view**, byte-identical to the bundle member, so every existing
   flat-path reader (census §3.2/§3.3 cohort, preflight) keeps working
   unchanged. Views are regenerated ON the pointer flip and are the
   publisher's ONLY writer of the flat location thereafter (census §6:
   "Views are read-only, regenerated on pointer flip"). The two flat
   members share the ``artifacts/prod`` directory and are read as fixed
   absolute paths, so this P1 publisher is **scoped to byte-identical
   content** (the genesis seal / no-op refresh) and REFUSES any changing
   pair — a mixed pair (new panel + old calibrator) is the 2026-07-16
   orphaned-binding class; the general changing-content pair-atomic
   publisher is deferred to AC4 P2/P3 (see :func:`regenerate_flat_views`).

RFC §2.7 semantics carried by the seal: the bundle's ``bindings`` are a
VERBATIM copy of the panel's stamped identity/WF-gate metadata — the seal
asserts "this is the pair the operator is knowingly serving today", it is
EXPLICITLY NOT a WF-gate buy-admissibility statement (admission stays the
preflight P-WF-GATE's job).

**Boundary (RFC §5):** renquant-artifacts OWNS the store; this orchestrator
tool is a *writer* that INVOKES the artifacts publication API (it does not
own the store) and owns the run-bundle provenance + the read-only local
materialization (views) of the resolved active bundle. The default store is
:func:`create_default_store`, so step-6 pair validation can never be
silently omitted; tests inject a :class:`~renquant_artifacts.bundle_store.BundleStore`
with a stub validator against a SANDBOX store.

**This code makes P1 EXECUTABLE; the actual live seal is operator-gated**
(the ask-first machine-landing "P1 execution" of the census): standing up
the real store + flipping the real ACTIVE. Until that cutover runs the flat
pair remains authoritative on the live machine — nothing here writes the
live production store.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from renquant_artifacts.bundle_schema import BUNDLE_MEMBER_NAMES, sha256_hex
from renquant_artifacts.bundle_store import (
    BundleStore,
    PublishResult,
    RECORD_PREPARE,
    ResolvedBundle,
)

#: Serving-pair member names (from the schema, never re-spelled here).
PANEL_MEMBER, CALIBRATOR_MEMBER = BUNDLE_MEMBER_NAMES

#: ``authorization.tool`` for the P1 seal. Deliberately NOT a restamp-class
#: name (no ``restamp`` marker, not the break-glass tool) — the seal of an
#: already-serving pair is a bootstrap publication, not incident response,
#: so RFC §2.4 does not require an incident_ref.
SEAL_TOOL = "p1_serving_pair_seal"
SEAL_TOOL_VERSION = "1.0.0"

#: 0444 — read-only for owner/group/other. The regenerated flat views are
#: never hand-editable; the publisher's view refresh is their only writer.
VIEW_MODE = 0o444


class SealError(RuntimeError):
    """The P1 seal cannot proceed (fail-closed)."""


# ---------------------------------------------------------------------------
# Run-bundle provenance (RFC §2.2 "Run-bundle binding")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunBundleProvenance:
    """The exact provenance a run bundle records to replay against the
    archived bundle: ``{bundle_id, manifest_digest, member_digests,
    generation}`` (RFC §2.2)."""

    bundle_id: str
    manifest_digest: str
    generation: int
    member_digests: dict[str, dict[str, Any]]

    @classmethod
    def from_publish(cls, result: PublishResult) -> "RunBundleProvenance":
        manifest = result.manifest
        return cls(
            bundle_id=result.bundle_id,
            manifest_digest=manifest.manifest_digest,
            generation=result.generation,
            member_digests={
                name: {"sha256": digest.sha256, "bytes": digest.bytes}
                for name, digest in sorted(manifest.members.items())
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "manifest_digest": self.manifest_digest,
            "generation": self.generation,
            "member_digests": self.member_digests,
        }


@dataclass(frozen=True)
class SealResult:
    """Outcome of a P1 seal: the provenance record + the regenerated views."""

    provenance: RunBundleProvenance
    view_paths: dict[str, Path]

    @property
    def bundle_id(self) -> str:
        return self.provenance.bundle_id

    @property
    def generation(self) -> int:
        return self.provenance.generation


# ---------------------------------------------------------------------------
# bindings + authorization construction (verbatim, RFC §2.4 / §2.7)
# ---------------------------------------------------------------------------


def _load_json_member(data: bytes, member: str) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealError(f"serving-pair member {member!r} is not readable JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SealError(f"serving-pair member {member!r} is not a JSON object")
    return payload


def _first_present_str(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def extract_bindings(panel_bytes: bytes, calibrator_bytes: bytes) -> dict[str, Any]:
    """Build the bundle ``bindings`` block as a VERBATIM copy of the pair's
    stamped identity/WF-gate metadata (RFC §2.7).

    The block is audit metadata only: the pipeline ``bundle_contract`` pair
    validator derives identity from MEMBER CONTENT, not from ``bindings``
    (pinning bindings-against-content is the phase-3 binding step). The
    schema requires a non-empty object; ``wf_gate_verdict`` is copied
    verbatim and is EXPLICITLY NOT a buy-admissibility assertion.
    """
    panel = _load_json_member(panel_bytes, PANEL_MEMBER)
    calibrator = _load_json_member(calibrator_bytes, CALIBRATOR_MEMBER)

    bindings: dict[str, Any] = {
        "seal_note": (
            "verbatim pair-consistency copy of the currently-served pair; "
            "NOT a WF-gate buy-admissibility assertion (RFC §2.7)"
        ),
    }

    wf_meta = panel.get("wf_gate_metadata")
    verdict: Any = None
    if isinstance(wf_meta, dict):
        verdict = wf_meta.get("verdict") or wf_meta.get("wf_gate_verdict")
        if verdict is None and isinstance(wf_meta.get("passed"), bool):
            # the live panel stamps the WF-gate outcome as a boolean `passed`
            # (+ override fields), not a `verdict` string — reflect it verbatim
            verdict = "PASS" if wf_meta["passed"] else "FAIL"
        # Carry the stamped WF-gate + operator-override provenance VERBATIM
        # (compact scalars) so the seal records the override state under which
        # the operator is knowingly serving this pair (§2.7; also closes the
        # GOAL-5 "override provenance not in the run bundle" gap).
        for key in (
            "passed",
            "gate_verdict_before_override",
            "operator_authorized_override",
            "override_applied_at",
            "override_reason",
            "diagnostic_only",
            "gate_version",
        ):
            value = wf_meta.get(key)
            if isinstance(value, (bool, int, float, str)):
                bindings[f"wf_{key}"] = value
    if verdict is None:
        verdict = panel.get("wf_gate_verdict")

    # verbatim copy; sentinel only when the panel carries no stamp
    bindings["wf_gate_verdict"] = verdict if verdict is not None else "UNSTAMPED"
    scorer_fp = _first_present_str(
        panel,
        (
            "model_content_fingerprint",
            "scorer_model_content_fingerprint",
            "config_fingerprint",
        ),
    )
    if scorer_fp:
        bindings["scorer_fingerprint"] = scorer_fp
    cal_meta = calibrator.get("metadata")
    cal_binding = None
    if isinstance(cal_meta, dict):
        cal_binding = _first_present_str(
            cal_meta, ("scorer_model_content_fingerprint", "scorer_config_fingerprint")
        )
    if cal_binding:
        bindings["calibrator_scorer_binding"] = cal_binding
    return bindings


def build_seal_authorization(
    panel_bytes: bytes,
    calibrator_bytes: bytes,
    *,
    operator: str,
    os_user: str | None = None,
    tool_version: str = SEAL_TOOL_VERSION,
) -> dict[str, Any]:
    """Assemble the RFC §2.4 ``authorization`` block for the P1 seal.

    ``inputs`` records the content digests of everything the writer
    consumed — here the two source member files (bare sha256 hex).
    """
    if not operator:
        raise SealError("seal requires a non-empty operator identity (authorization.actor.operator)")
    return {
        "tool": SEAL_TOOL,
        "tool_version": tool_version,
        "actor": {
            "os_user": os_user or getpass.getuser(),
            "operator": operator,
        },
        "source": {
            "rfc": "RenQuant#492",
            "phase": "P1",
            "census": "doc/design/2026-07-18-ac4-migration-census.md",
            "action": "seal the current serving pair as generation 1",
        },
        "inputs": {
            PANEL_MEMBER: sha256_hex(panel_bytes),
            CALIBRATOR_MEMBER: sha256_hex(calibrator_bytes),
        },
    }


# ---------------------------------------------------------------------------
# flat-view regeneration (census §6: read-only, regenerated on pointer flip)
# ---------------------------------------------------------------------------


def regenerate_flat_views(
    resolved: ResolvedBundle,
    flat_dir: str | Path,
    *,
    crash_hook: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """Regenerate the flat serving paths as READ-ONLY (0444) views of the
    active bundle's members — byte-identical to each bundle member.

    Called ON the pointer flip. Each view is written atomically: a private
    tmp file (fsync'd), chmod 0444, then ``os.replace`` over the flat path;
    the directory is fsync'd once at the end. ``resolved`` must be a
    digest-verified :class:`ResolvedBundle` (member bytes come straight from
    its held-open descriptors), so a view can never diverge from the sealed
    content. Existing flat-path readers keep working unchanged.

    **Pair-atomicity contract (AC4; the 2026-07-16 orphaned-binding class).**
    The two flat members share a directory and are read by legacy readers as
    fixed absolute paths (``artifacts/prod/{panel-ltr…, panel-rank-…}``), so
    the two ``os.replace`` calls below are each atomic per file but the PAIR
    is not: a crash between them, or a legacy reader loading both files mid
    loop, could otherwise observe a MIXED pair (new panel + old calibrator,
    or the reverse) — an orphaned calibrator↔scorer binding. A truly
    pair-atomic in-place cutover for CHANGED content would need a
    generation-directory reached by a single pointer flip (infeasible while
    the pair lives in the shared ``artifacts/prod`` dir alongside unrelated
    artifacts) or every legacy reader routed through the bundle pointer (a
    larger AC4 P2/P3 change). This P1 publisher is therefore SCOPED to the
    only case it needs and can make provably mixed-pair-safe: the genesis
    seal / no-op refresh, where each regenerated member is **byte-identical**
    to the flat file it overwrites. When content is byte-identical, no reader
    can ever observe a mixed pair (both files carry the same bytes before,
    during, and after either replace; a crash between the two replaces leaves
    a pair that is byte-identical to BOTH the old and the new content). Any
    member whose bytes would CHANGE an existing flat file is REFUSED
    (:class:`SealError`) BEFORE a single byte is written, so the flat pair is
    never left in a mixed state — the general changing-content flat publisher
    (promote/rollback that alters the served pair) is deferred to AC4 P2/P3
    with its own pair-atomic cutover.
    """
    target_dir = Path(flat_dir)
    if not target_dir.is_dir():
        raise SealError(f"flat view directory does not exist: {target_dir}")

    # Phase 1 — read every member and PRE-CHECK the pair-atomicity invariant
    # BEFORE writing anything: an existing flat file may only be overwritten
    # with byte-identical content. A single differing member refuses the whole
    # cutover with the flat dir untouched (no partial write => no mixed pair).
    staged: dict[str, bytes] = {}
    for name in sorted(resolved.manifest.members):
        data = resolved.read_member(name)
        target = target_dir / name
        if target.exists() and target.read_bytes() != data:
            raise SealError(
                f"flat view {name!r} would CHANGE the served content; the "
                "non-atomic in-place flat cutover is scoped to genesis / "
                "byte-identical refresh only (a changing-content pair cutover "
                "needs the pair-atomic generation-pointer publisher deferred "
                "to AC4 P2/P3). Refusing to publish a changed pair through the "
                "two-file replace path that could expose a mixed pair."
            )
        staged[name] = data

    # Phase 2 — all members are byte-identical to (or absent from) the flat
    # dir, so the two per-file replaces cannot expose a mixed pair. ``crash_hook``
    # (fault injection) fires after each replace to prove that invariant.
    views: dict[str, Path] = {}
    for name in sorted(staged):
        data = staged[name]
        target = target_dir / name
        tmp = target_dir / f".{name}.view.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp, VIEW_MODE)
        os.replace(tmp, target)  # atomic; final mode is 0444 (from tmp)
        views[name] = target
        if crash_hook is not None:
            crash_hook(f"after-view-replace:{name}")
    _fsync_dir(target_dir)
    return views


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# the P1 seal
# ---------------------------------------------------------------------------


def _has_prior_publication(store: BundleStore) -> bool:
    return any(rec.get("record") == RECORD_PREPARE for rec in store.read_operations())


def _refuse_if_flat_pair_would_change(
    members: Mapping[str, bytes], flat_dir: Path,
) -> None:
    """orch#558 preflight: refuse (:class:`SealError`) BEFORE any store publish
    or ACTIVE mutation if publishing ``members`` would CHANGE an existing flat
    file.

    ``regenerate_flat_views`` already refuses a changing flat member, but it
    runs AFTER ``store.publish`` (PREPARE + the ACTIVE flip). A refusal there
    leaves ACTIVE pointing at the NEW bundle while the fixed-path readers retain
    the OLD flat pair — the exact split orch#558 forbids. Running the same
    byte-identity check on the raw member bytes BEFORE publish makes the seal
    all-or-nothing across store state AND the flat compatibility views: a
    changed-content pair raises with the flat dir untouched and the store
    unmutated. Byte-identical (genesis / no-op refresh) and absent targets pass,
    exactly as :func:`regenerate_flat_views` allows.
    """
    if not flat_dir.is_dir():
        raise SealError(f"flat view directory does not exist: {flat_dir}")
    for name, data in members.items():
        target = flat_dir / name
        if target.exists() and target.read_bytes() != data:
            raise SealError(
                f"flat view {name!r} would CHANGE the served content; refusing "
                "BEFORE any store publish or ACTIVE mutation (orch#558: the P1 "
                "seal is all-or-nothing across store state and the flat compat "
                "views). The changing-content pair cutover is deferred to AC4 "
                "P2/P3's pair-atomic generation-pointer publisher."
            )


def seal_serving_pair(
    store: BundleStore,
    *,
    panel_path: str | Path,
    calibrator_path: str | Path,
    operator: str,
    flat_view_dir: str | Path | None = None,
    regenerate_views: bool = True,
    require_genesis: bool = True,
    os_user: str | None = None,
    tool_version: str = SEAL_TOOL_VERSION,
) -> SealResult:
    """Publish the current serving pair as generation 1 through ``store``.

    ``store`` is an AUTHORITATIVE :class:`BundleStore` (production callers
    build it via :func:`create_default_store`, wiring the pipeline pair
    validator into writer step 6; tests inject a store with a stub
    validator against a sandbox root). The two members are read VERBATIM
    from ``panel_path`` / ``calibrator_path`` and published together
    (PREPARE fsync'd before the ACTIVE flip, ACTIVATE bound to it).

    With ``regenerate_views`` (default), the active bundle is resolved and
    its members are written back to ``flat_view_dir`` (default: the panel's
    own directory) as 0444 views (:func:`regenerate_flat_views`). For the
    genesis seal the members are byte-identical to the flat pair being
    overwritten, so the view regeneration is a content no-op and cannot
    expose a mixed pair; a seal whose members would CHANGE an existing flat
    file is refused by :func:`regenerate_flat_views` (the pair-atomic
    changing-content publisher is deferred to AC4 P2/P3). Pass
    ``regenerate_views=False`` to publish a new generation through the store
    without touching the flat compat surface.

    ``require_genesis`` (default) refuses to run if the store already has a
    publication — P1 is the FIRST publication (generation 1); a store with
    prior PREPAREs has already been sealed.

    Returns a :class:`SealResult` (run-bundle provenance + the view paths).
    Never writes any path other than the store and the flat view directory.
    """
    if require_genesis and _has_prior_publication(store):
        raise SealError(
            "store already has a prior publication — P1 is the FIRST "
            "publication (generation 1); refusing to re-seal (pass "
            "require_genesis=False only for a deliberate republish)"
        )

    panel_path = Path(panel_path)
    calibrator_path = Path(calibrator_path)
    panel_bytes = panel_path.read_bytes()
    calibrator_bytes = calibrator_path.read_bytes()
    if not panel_bytes or not calibrator_bytes:
        raise SealError("serving-pair members must be non-empty")

    bindings = extract_bindings(panel_bytes, calibrator_bytes)
    authorization = build_seal_authorization(
        panel_bytes,
        calibrator_bytes,
        operator=operator,
        os_user=os_user,
        tool_version=tool_version,
    )

    members = {PANEL_MEMBER: panel_bytes, CALIBRATOR_MEMBER: calibrator_bytes}

    # orch#558: preflight the flat compat pair BEFORE any store mutation so a
    # changed-content seal is all-or-nothing — never ACTIVE=new bundle while the
    # fixed-path readers still hold the old flat pair. regenerate_flat_views
    # keeps its own post-publish byte-identity check as a final guard.
    target_dir: Path | None = None
    if regenerate_views:
        target_dir = Path(flat_view_dir) if flat_view_dir is not None else panel_path.parent
        _refuse_if_flat_pair_would_change(members, target_dir)

    result = store.publish(
        members,
        bindings=bindings,
        authorization=authorization,
    )
    provenance = RunBundleProvenance.from_publish(result)

    view_paths: dict[str, Path] = {}
    if regenerate_views:
        with store.resolve_active() as resolved:
            view_paths = regenerate_flat_views(resolved, target_dir)

    return SealResult(provenance=provenance, view_paths=view_paths)


# ---------------------------------------------------------------------------
# CLI — operator-gated live execution entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bundle_seal",
        description=(
            "Seal the current 104 serving pair as bundle generation 1 (AC4 "
            "migration P1). Publishes THROUGH the artifacts bundle store via "
            "create_default_store (validator-gated) and regenerates the flat "
            "paths as read-only 0444 views. Running this against the REAL "
            "store is the operator-gated machine landing; the flat pair stays "
            "authoritative until that cutover."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--store-root", required=True, help="bundle store root (…/artifacts/prod)")
    parser.add_argument("--panel", required=True, help=f"path to {PANEL_MEMBER}")
    parser.add_argument("--calibrator", required=True, help=f"path to {CALIBRATOR_MEMBER}")
    parser.add_argument(
        "--operator",
        default=os.environ.get("RQ_OPERATOR", ""),
        help="operator identity for authorization.actor.operator (or $RQ_OPERATOR)",
    )
    parser.add_argument(
        "--flat-view-dir",
        default=None,
        help="directory to regenerate 0444 views into (default: the panel's directory)",
    )
    parser.add_argument(
        "--no-views",
        action="store_true",
        help="publish gen 1 but do NOT regenerate the flat views",
    )
    parser.add_argument(
        "--accept-legacy-stamps",
        choices=("true", "false"),
        default=None,
        help="M6 migration-window flag for the pair validator (default: contract default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Imported here so the module stays importable without renquant-pipeline
    # (create_default_store lazily imports the pipeline validator).
    from renquant_artifacts.bundle_contract_binding import create_default_store

    if not args.operator:
        print("bundle_seal: --operator (or $RQ_OPERATOR) is required", file=sys.stderr)
        return 2
    accept_legacy = (
        None if args.accept_legacy_stamps is None else args.accept_legacy_stamps == "true"
    )
    try:
        store = create_default_store(args.store_root, accept_legacy_stamps=accept_legacy)
        result = seal_serving_pair(
            store,
            panel_path=args.panel,
            calibrator_path=args.calibrator,
            operator=args.operator,
            flat_view_dir=args.flat_view_dir,
            regenerate_views=not args.no_views,
        )
    except (SealError, OSError) as exc:
        print(f"bundle_seal: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "sealed": result.provenance.to_dict(),
                "views": {name: str(path) for name, path in result.view_paths.items()},
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "CALIBRATOR_MEMBER",
    "PANEL_MEMBER",
    "SEAL_TOOL",
    "SEAL_TOOL_VERSION",
    "VIEW_MODE",
    "RunBundleProvenance",
    "SealError",
    "SealResult",
    "build_seal_authorization",
    "extract_bindings",
    "main",
    "regenerate_flat_views",
    "seal_serving_pair",
]
