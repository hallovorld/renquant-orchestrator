"""Model-identity regression tripwire — the #484 §7.2a consumer.

WHY THIS EXISTS. Between the 2026-06-25 and 06-26 sessions the production
panel artifact silently REGRESSED from the 06-21 model to the 05-18 model and
stayed regressed for FIVE sessions (06-26..07-02), unalerted — a 39-45-day-old
model held primary in direct conflict with the 28d freshness policy, and by
07-03 the tree flipped back, again without any promotion event (orchestrator
PR #484 §7.2a, byte-verified against run-bundle ``artifact_hashes.panel``).
Nothing in the stack noticed that a DIFFERENT MODEL was serving. This module
is the tripwire the incident was missing.

WHAT IT CHECKS. The latest run bundle's serving identity
(``artifact_hashes.panel`` — the exact field #484 used to byte-verify the
regression) is compared against:

  (a) the PREVIOUS session's bundle (did the serving model change?), and
  (b) the AUTHORIZED identity binding — the ``expected-model-identity.json``
      record in the neutral R-PIN deployed-state root (§5.2 layout, sibling
      of ``expected-generation.json``; FORWARD-ONLY, atomic). A deployment /
      promotion is authorized only when it RECORDS the panel sha it deploys;
      an identity change is explained only by a binding (or a promotions-
      ledger entry) that names the NEW sha.

Per Codex review on PR #485: manifest timestamps (``deployment.deployed_at``)
prove only that a manifest was captured, not that the serving artifact is the
one a pin transition authorized — they are DIAGNOSTIC metadata here, never an
explanation. The v1 deployment manifest carries no model-artifact mapping, so
it can never explain a model change by itself.

VERDICTS:

  ``identity_unchanged``           — same panel sha as the previous session
                                     (and not contradicting the binding).
                                     INFO line, no page.
  ``explained_pin_advance``        — identity changed AND the new sha IS the
                                     recorded authorized binding (a recorded
                                     pin advance/deploy). INFO line, no page.
  ``explained_promotion``          — identity changed AND the new sha appears
                                     in the promotions ledger. INFO, no page.
  ``identity_binding_mismatch``    — the SERVING identity contradicts the
                                     recorded authorized binding (changed or
                                     not). OUTAGE page.
  ``unexplained_identity_change``  — identity changed with NO binding and NO
                                     promotion naming the new sha. The 06-25
                                     regression shape. OUTAGE page (reuses
                                     the #480 headline vocabulary).
  ``coverage_lost``                — the comparison could not be made (no
                                     latest identity / no previous session
                                     bundle). For a scheduled monitor this is
                                     lost monitoring coverage: DEGRADED page
                                     by default; ``--offline`` (local
                                     forensics) downgrades it to a quiet
                                     recorded note.

An unreadable/absent deployment manifest or identity-binding record likewise
contributes a DEGRADED line by default (coverage lost), quiet under
``--offline``. The worst tag wins; a DEGRADED contribution never downgrades
an OUTAGE.

ROUND 2 (Codex #485 follow-up — "prove the chain, not just the endpoint").
The ``expected-model-identity.json`` binding above is a single, forward-only
SLOT: it proves the LATEST identity is authorized NOW, but — having no
history — it cannot say whether the PRIOR identity was itself authorized at
an earlier generation (a chain that only ever checks its own endpoint could
still explain a "jump" from an unauthorized past state). ``build_tripwire_
report`` adds a SUPPORTING check (same pattern as the manifest
``generation_status`` check below: contributes a note + tag, never
overrides ``classify_transition``'s verdict) using the generation-bound
promotions ledger (``load_promotion_ledger`` — ``{sha: generation}``,
round-2 format) as the historical record: when a change is explained
(``explained_pin_advance`` / ``explained_promotion``), the PRIOR identity's
own ledger-recorded generation must be found and must be STRICTLY OLDER
than the active generation, or the chain is a coverage gap (DEGRADED,
quiet under ``--offline``) or, if it is NOT older (a non-monotonic/rollback
shape), a proven contradiction (OUTAGE — never suppressed). Generation 1
is the epoch floor: there is no older generation to chain to.

ROUND 3 (Codex #485 follow-up — "make the binding a derived consequence of
immutable deployment/promotion evidence, not a generic maintenance
operation"). Rounds 1-2 hardened the READ side (what the tripwire trusts);
this hardens the WRITE side (what ``--record-expected`` is allowed to
author). Previously ``record_expected_identity`` trusted whatever
``(generation, panel_sha)`` pair its caller supplied — extracted straight
from whatever bundle file ``--latest-bundle``/``--bundle-dir`` pointed at —
which meant a post-incident operator could run the maintenance command
against an UNEXPECTED serving bundle and thereby author exactly the
regression this monitor exists to report. Forward-only generation
semantics (round 1) prevent a later REBIND, but do not authenticate the
FIRST bind.

The fix (reusing the orchestrator#483 evidence-pin PATTERN — never a
second hand-rolled sibling-checkout resolver or ``store://`` convention):
``record_expected_identity`` now REQUIRES an ``evidence_ref`` naming a
sealed ``store://<record>`` promotion-evidence bundle (the same
sibling-checkout convention against ``renquant-artifacts``, tamper-checked
against that store's own ``STORE-MANIFEST.json`` when present —
:func:`resolve_promotion_evidence_bundle`). The bundle's OWN JSON payload
must be a ``kind: "model-identity-promotion"`` record naming, under the
``generation``/``panel_sha`` keys, EXACTLY the ``(generation, panel_sha)``
pair this call is trying to bind
(:func:`_verify_promotion_evidence_payload`) — an evidence bundle that
merely EXISTS, or that names a DIFFERENT pair, is refused
(``ExpectedIdentityError``) and NOTHING is written. The evidence's own
``store://`` reference and a content sha256 of the resolved bytes are
persisted alongside the binding (``evidence_ref`` / ``evidence_sha256`` in
``expected-model-identity.json``) so a future auditor can see exactly
which evidence record authorized a binding without re-resolving a possibly
-moved sibling checkout. This is additive to, never a replacement of, the
round-1 forward-only epoch discipline.

Unlike the deployment manifest's own ``evidence_ref``/``evidence_repo_
commit`` pair (#483), this write path has no earlier-stamped commit to
re-check a sibling checkout against — this call IS the first read of the
evidence. ``resolve_promotion_evidence_bundle`` therefore derives the
sibling checkout's own current HEAD and reuses
``deployment_manifest.check_checkout_state`` purely for its existence
/clean-checkout verification (never trust a dirty or non-git directory),
not to detect drift since a prior read.

Scope note: this round hardens WHO may author a binding; it does not touch
``build_tripwire_report``'s READ-side chain-adjacency logic (round 2,
already verified and merged), and it does not arm this monitor in any
scheduled job — see "DARK by default" below, unchanged.

Properties (house monitor conventions, same as ``outage_monitor``):

  * **read-only in check mode** — consumes run-bundle JSONs + state-root
    records; never touches broker, live state, or production paths. The ONLY
    write path is the explicit ``--record-expected`` maintenance mode (the
    deploy-flow hook that records the authorized binding after a verified
    deployment), which writes solely inside the neutral state root.
  * **fail-soft** — no input can make the tripwire raise; missing inputs
    page DEGRADED (default) or record notes (``--offline``). The monitor's
    own crash must not dark the session it audits.
  * **DARK by default** — wire-ready for the daily flow but invoked by NO
    scheduled job yet; wiring into daily automation is a separate landing
    (machine-landing, ask-first).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .deploy_pin import DEFAULT_ARTIFACT_STORE_PATH, DEFAULT_ARTIFACT_STORE_REPO
from .deployment_manifest import (
    EVIDENCE_REF_PREFIX,
    DeploymentManifestError,
    GENERATION_OK,
    GitProbe,
    MACHINE_MANIFEST_FILENAME,
    check_checkout_state,
    classify_generation,
    default_git_probe,
    deploy_state_root,
    load_deployment_manifest,
    read_expected_generation,
    resolve_contained_subdir,
    sha256_of_bytes,
    write_json_canonical,
)
from .outage_monitor import (
    TAG_DEGRADED,
    TAG_OUTAGE,
    emit_alert,
    worst_tag,
)
from .runtime_paths import default_github_root

SCHEMA_VERSION = 2
OWNER_REPO = "renquant-orchestrator"

#: The headline component after the #480 tag — sibling of SESSION-INTEGRITY.
HEADLINE_COMPONENT = "MODEL-IDENTITY"

#: The authorized-identity binding record in the neutral R-PIN state root
#: (§5.2 layout; sibling of ``expected-generation.json``). FORWARD-ONLY,
#: written atomically; the deploy/promote flow records the panel sha it
#: deploys, bound to the manifest generation it deployed under.
EXPECTED_IDENTITY_FILENAME = "expected-model-identity.json"
EXPECTED_IDENTITY_KIND = "expected-model-identity"
#: Bumped 1 -> 2 for round 3 (Codex #485 follow-up): every record WRITTEN
#: going forward carries ``evidence_ref``/``evidence_sha256`` naming the
#: sealed promotion evidence that authorized it. ``read_expected_identity``
#: does NOT enforce this constant (see its docstring) — the two new fields
#: are validated when present but not required, so a pre-round-3-shape
#: record (none exist in production; this monitor has never been armed)
#: would still be accepted rather than crash the reader.
EXPECTED_IDENTITY_SCHEMA_VERSION = 2

#: The evidence bundle's own JSON payload must self-identify as this kind
#: for ``record_expected_identity`` to trust it (round 3, Codex #485
#: follow-up "make the binding a derived consequence of immutable
#: deployment/promotion evidence, not a generic maintenance operation").
PROMOTION_EVIDENCE_KIND = "model-identity-promotion"
#: The keys a sealed promotion-evidence bundle must carry, naming the
#: EXACT ``(generation, panel_sha)`` pair it authorizes. Chosen to match
#: the ``expected-model-identity.json`` field names 1:1 (no translation
#: layer between "what the evidence claims" and "what gets written").
PROMOTION_EVIDENCE_GENERATION_KEY = "generation"
PROMOTION_EVIDENCE_PANEL_SHA_KEY = "panel_sha"

#: Default sibling-checkout convention for resolving a sealed promotion-
#: evidence ``store://`` reference — the SAME artifact-store binding
#: ``deploy_pin`` uses (never a second hardcode of "renquant-artifacts").
DEFAULT_PROMOTION_EVIDENCE_STORE_REPO = DEFAULT_ARTIFACT_STORE_REPO
DEFAULT_PROMOTION_EVIDENCE_STORE_PATH = DEFAULT_ARTIFACT_STORE_PATH

# --- verdict vocabulary -------------------------------------------------------
VERDICT_UNCHANGED = "identity_unchanged"
VERDICT_PIN_ADVANCE = "explained_pin_advance"
VERDICT_PROMOTION = "explained_promotion"
VERDICT_BINDING_MISMATCH = "identity_binding_mismatch"
VERDICT_UNEXPLAINED = "unexplained_identity_change"
VERDICT_COVERAGE_LOST = "coverage_lost"

_VERDICT_TO_TAG: dict[str, str | None] = {
    VERDICT_UNCHANGED: None,
    VERDICT_PIN_ADVANCE: None,
    VERDICT_PROMOTION: None,
    VERDICT_BINDING_MISMATCH: TAG_OUTAGE,
    VERDICT_UNEXPLAINED: TAG_OUTAGE,
    # coverage_lost maps to DEGRADED by default and None in offline mode —
    # resolved in build_tripwire_report, not here.
}

_TAG_PRIORITY = {TAG_OUTAGE: 5, TAG_DEGRADED: 4}

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_PREFIX = "sha256:"

#: Promotion-ledger entries may carry the promoted artifact sha under any of
#: these keys (JSON array or JSONL of objects). Matching is sha-based only —
#: a promotion "explains" a change iff it names the NEW identity.
_PROMOTION_SHA_KEYS = (
    "panel_sha",
    "sha",
    "sha256",
    "artifact_sha256",
    "model_content_sha256",
)


class ExpectedIdentityError(RuntimeError):
    """The expected-model-identity record contract was violated (fail-closed
    on WRITE; reads in the tripwire itself degrade fail-soft)."""


@dataclass
class ModelIdentity:
    """One session's serving-model identity, extracted from a run bundle."""

    panel_sha: str | None
    run_id: str | None
    session_date: str | None
    source_path: str | None = None
    artifact_hashes: dict[str, Any] = field(default_factory=dict)

    @property
    def short_sha(self) -> str:
        return (self.panel_sha or "?")[:12]


@dataclass
class TripwireReport:
    """The structured result of one identity comparison.

    Duck-type compatible with :func:`outage_monitor.emit_alert` (title_tag /
    title / body / priority)."""

    as_of: str
    run_id: str
    verdict: str = VERDICT_COVERAGE_LOST
    title_tag: str | None = None
    title: str | None = None
    body_lines: list[str] = field(default_factory=list)
    latest: dict[str, Any] = field(default_factory=dict)
    previous: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    expected_identity: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.body_lines)

    @property
    def priority(self) -> int:
        return _TAG_PRIORITY.get(self.title_tag or "", 3)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "owner_repo": OWNER_REPO,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "verdict": self.verdict,
            "title_tag": self.title_tag,
            "title": self.title,
            "body": self.body,
            "priority": self.priority,
            "latest": self.latest,
            "previous": self.previous,
            "manifest": self.manifest,
            "expected_identity": self.expected_identity,
            "missing": self.missing,
        }


# --- low-level helpers ----------------------------------------------------------

def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: str | Path | None) -> Any | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def normalize_sha(value: Any) -> str | None:
    """``'sha256:ABCD…'`` / ``'abcd…'`` -> lowercase bare hex, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    if text.startswith(_SHA_PREFIX):
        text = text[len(_SHA_PREFIX):]
    return text or None


def session_date_of(bundle: Mapping[str, Any]) -> str | None:
    """YYYY-MM-DD of the session, from run_id prefix or date-ish fields.

    Run bundles carry no dedicated date field; the daily flow's run ids are
    ``YYYY-MM-DD-<run_type>-<hex>`` (e.g. ``2026-06-26-live-5ce63326``)."""
    for key in ("run_id", "as_of", "date", "run_date"):
        value = bundle.get(key)
        if isinstance(value, str):
            match = _DATE_RE.match(value.strip())
            if match:
                return match.group(1)
    return None


def extract_model_identity(
    bundle: Mapping[str, Any] | None,
    *,
    source_path: str | Path | None = None,
) -> ModelIdentity:
    """The serving-model identity of one run bundle (fail-soft on gaps).

    ``artifact_hashes.panel`` is the primary identity (the resolved alias for
    whichever config variant carries the panel artifact — see
    ``intraday_session_inputs._REQUIRED_ARTIFACT_KEYS``); the raw
    ``ranking.panel_scoring.artifact_path`` hash is the fallback."""
    bundle = bundle if isinstance(bundle, Mapping) else {}
    hashes = bundle.get("artifact_hashes")
    hashes = dict(hashes) if isinstance(hashes, Mapping) else {}
    panel = normalize_sha(hashes.get("panel")) or normalize_sha(
        hashes.get("ranking.panel_scoring.artifact_path")
    )
    run_id = bundle.get("run_id")
    return ModelIdentity(
        panel_sha=panel,
        run_id=str(run_id) if run_id else None,
        session_date=session_date_of(bundle),
        source_path=str(source_path) if source_path else None,
        artifact_hashes={
            k: normalize_sha(v) for k, v in hashes.items() if normalize_sha(v)
        },
    )


def find_session_bundles(root: str | Path) -> tuple[Path | None, Path | None]:
    """(latest, previous-session) ``run_bundle*.json`` under ``root``.

    Latest = newest by mtime (matches ``outage_monitor.find_latest_bundle``).
    Previous = the newest bundle whose SESSION DATE strictly predates the
    latest's — same-day re-runs are not a "previous session". When session
    dates cannot be parsed, falls back to the next-newest file. Either slot
    degrades to ``None`` (fail-soft)."""
    rootp = Path(root)
    if not rootp.exists():
        return None, None
    candidates = [p for p in rootp.rglob("run_bundle*.json") if p.is_file()]
    if not candidates:
        return None, None
    ordered = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    latest = ordered[0]
    latest_bundle = _load_json(latest)
    latest_date = session_date_of(latest_bundle) if isinstance(
        latest_bundle, Mapping
    ) else None
    previous: Path | None = None
    for candidate in ordered[1:]:
        bundle = _load_json(candidate)
        if not isinstance(bundle, Mapping):
            continue
        date = session_date_of(bundle)
        if latest_date is None or date is None or date < latest_date:
            previous = candidate
            break
    return latest, previous


def load_promotion_ledger(path: str | Path | None) -> dict[str, int]:
    """``{sha: generation}`` for an optional promotions ledger (JSON/JSONL).

    Round-2 hardening (Codex #485 follow-up — "prove the chain, not just the
    endpoint"): each entry must carry BOTH an artifact sha (any of
    ``_PROMOTION_SHA_KEYS``) AND an integer ``generation`` naming the
    manifest generation the promotion was made FOR. This lets
    ``build_tripwire_report``'s chain-adjacency check answer a question the
    single-slot ``expected-model-identity.json`` binding cannot: did the
    PRIOR identity itself belong to an earlier authorized generation (not
    just "is the NEW identity authorized now")?

    Format note (NOT silently backward compatible for EXPLAINING purposes):
    a legacy bare-sha entry (no ``generation`` key — the pre-round-2 format,
    matched on sha alone) is still PARSED without crashing (fail-soft) but
    is EXCLUDED from the returned map — it can no longer bind a chain
    position until migrated to add ``generation``. It can still explain a
    LATEST identity change via the (unchanged) presence-only promotion
    check in ``classify_transition``; it simply cannot anchor the
    chain-adjacency supporting check, which degrades to a coverage-gap
    note rather than silently assuming the chain holds."""
    if path is None:
        return {}
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {}
    entries: list[Any] = []
    try:
        payload = json.loads(text)
        entries = payload if isinstance(payload, list) else [payload]
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    ledger: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        sha: str | None = None
        for key in _PROMOTION_SHA_KEYS:
            sha = normalize_sha(entry.get(key))
            if sha:
                break
        if not sha:
            continue
        generation = entry.get("generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            continue  # no (valid) generation binding — see docstring
        ledger[sha] = generation
    return ledger


# --- the authorized-identity binding record (neutral R-PIN state root) -------------

def read_expected_identity(
    state_root: str | Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """``(record, problem)`` — the authorized-identity binding, fail-soft.

    Returns ``(None, None)`` when the record simply does not exist yet, and
    ``(None, problem_text)`` when it exists but is malformed (that is a lost-
    coverage condition the caller reports, never an exception).

    ``evidence_ref``/``evidence_sha256`` (round 3, Codex #485 follow-up) are
    validated WHEN PRESENT but are not required here: every record
    ``record_expected_identity`` writes going forward carries them, but this
    reader must not crash on an already-existing pre-round-3-shape record
    (there are none in production, since this monitor has never been armed
    — but degrade gracefully rather than assume that stays true forever)."""
    root = deploy_state_root(state_root)
    record_path = root / EXPECTED_IDENTITY_FILENAME
    if not record_path.exists():
        return None, None
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"expected-identity record {record_path}: unreadable ({exc})"
    problems: list[str] = []
    if not isinstance(payload, dict):
        problems.append("must be a JSON object")
    else:
        if payload.get("kind") != EXPECTED_IDENTITY_KIND:
            problems.append(f"kind must be {EXPECTED_IDENTITY_KIND!r}")
        generation = payload.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
            problems.append("generation must be an integer >= 1")
        sha = payload.get("panel_sha")
        if not isinstance(sha, str) or not _SHA256_RE.match(sha):
            problems.append("panel_sha must be a 64-hex sha256")
        evidence_ref = payload.get("evidence_ref")
        if evidence_ref is not None and (
            not isinstance(evidence_ref, str)
            or not evidence_ref.startswith(EVIDENCE_REF_PREFIX)
        ):
            problems.append(
                f"evidence_ref must be a {EVIDENCE_REF_PREFIX!r} record when "
                "present"
            )
        evidence_sha256 = payload.get("evidence_sha256")
        if evidence_sha256 is not None and (
            not isinstance(evidence_sha256, str)
            or not _SHA256_RE.match(evidence_sha256)
        ):
            problems.append(
                "evidence_sha256 must be a 64-hex sha256 when present"
            )
    if problems:
        return None, (
            f"expected-identity record {record_path}: malformed: "
            + "; ".join(problems)
        )
    return payload, None


def resolve_promotion_evidence_bundle(
    evidence_ref: str,
    *,
    github_root: str | Path | None = None,
    git_probe: GitProbe | None = None,
    artifact_store_repo: str = DEFAULT_PROMOTION_EVIDENCE_STORE_REPO,
    artifact_store_path: str = DEFAULT_PROMOTION_EVIDENCE_STORE_PATH,
) -> tuple[Path, bytes, Any]:
    """Resolve + tamper-check a sealed ``store://<record>`` promotion-
    evidence bundle — the ``record_expected_identity`` authority gate
    (round 3, Codex #485 follow-up).

    Returns ``(path, raw_bytes, json_payload)`` on success. Raises
    ``ExpectedIdentityError`` fail-closed on ANY resolution problem: this is
    the WRITE path's authority gate, never fail-soft like the rest of this
    module's read side.

    Reuses the orchestrator#483 evidence-pin PATTERN and its shared
    primitives (``runtime_paths.default_github_root`` sibling-checkout
    convention, ``deployment_manifest.resolve_contained_subdir``,
    ``deployment_manifest.check_checkout_state``,
    ``deployment_manifest.sha256_of_bytes``) rather than reimplementing
    sibling-checkout resolution or the ``store://`` convention a second
    time. Unlike ``deploy_pin.resolve_evidence_bundle_path`` — which
    rejects a sibling checkout whose HEAD differs from a PRE-STAMPED
    ``deployment.verify.evidence_repo_commit`` recorded at an earlier
    capture — this call IS the first read of the evidence (there is no
    earlier stamp to check against), so it derives the sibling checkout's
    own current HEAD and reuses ``check_checkout_state`` purely for its
    existence/clean-checkout verification (never trust a dirty or non-git
    directory), not to detect drift since a prior read.
    """
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith(
        EVIDENCE_REF_PREFIX
    ):
        raise ExpectedIdentityError(
            f"expected-identity: evidence_ref must be a content-addressed "
            f"{EVIDENCE_REF_PREFIX!r} record, got {evidence_ref!r}"
        )
    remainder = evidence_ref[len(EVIDENCE_REF_PREFIX):]
    if not remainder or remainder.startswith("/") or ".." in Path(remainder).parts:
        raise ExpectedIdentityError(
            f"expected-identity: evidence_ref {evidence_ref!r} has an empty "
            "or non-relative store record reference"
        )
    root = Path(github_root) if github_root is not None else default_github_root()
    repo_path = root / artifact_store_repo
    probe = git_probe or default_git_probe
    if not repo_path.is_dir():
        raise ExpectedIdentityError(
            f"expected-identity: evidence_ref {evidence_ref!r} cannot be "
            f"resolved — artifact_store.repo {artifact_store_repo!r} sibling "
            f"checkout not found at {repo_path} (sibling root {root})"
        )
    head_probe = probe(["-C", str(repo_path), "rev-parse", "HEAD"])
    head = (head_probe.stdout or "").strip()
    if head_probe.returncode != 0 or not head:
        raise ExpectedIdentityError(
            f"expected-identity: {artifact_store_repo!r} sibling checkout at "
            f"{repo_path} is not a readable git checkout "
            f"({(head_probe.stderr or '').strip()})"
        )
    _, checkout_problem = check_checkout_state(
        artifact_store_repo, repo_path, head, git_probe=probe,
        require_clean=True, expected_label="sibling checkout HEAD",
    )
    if checkout_problem is not None:
        raise ExpectedIdentityError(
            "expected-identity: evidence sibling checkout not verifiable: "
            f"{checkout_problem}"
        )
    store_root = resolve_contained_subdir(
        repo_path, artifact_store_path, error_cls=ExpectedIdentityError,
        store_repr=f"{artifact_store_repo}:{artifact_store_path!r}",
    )
    evidence_path = store_root / remainder
    if not evidence_path.is_file():
        raise ExpectedIdentityError(
            f"expected-identity: evidence bundle not found at {evidence_path} "
            f"(from evidence_ref {evidence_ref!r})"
        )
    raw_bytes = evidence_path.read_bytes()
    store_manifest_path = store_root / "STORE-MANIFEST.json"
    if store_manifest_path.is_file():
        try:
            store_manifest = json.loads(
                store_manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ExpectedIdentityError(
                f"expected-identity: {store_manifest_path} unreadable ({exc})"
            ) from exc
        expected_hash = store_manifest.get(remainder)
        if expected_hash is not None:
            actual_hash = sha256_of_bytes(raw_bytes)
            if actual_hash != expected_hash:
                raise ExpectedIdentityError(
                    f"expected-identity: evidence bundle {evidence_path} "
                    f"content sha256 {actual_hash[:12]} != STORE-MANIFEST.json "
                    f"entry {str(expected_hash)[:12]} (possible tamper)"
                )
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExpectedIdentityError(
            f"expected-identity: evidence bundle {evidence_path} is not "
            f"valid JSON ({exc})"
        ) from exc
    return evidence_path, raw_bytes, payload


def _verify_promotion_evidence_payload(
    payload: Any, *, generation: int, panel_sha: str,
) -> None:
    """Reject (fail-closed) unless the evidence's OWN payload names EXACTLY
    the ``(generation, panel_sha)`` pair being bound — the crux of round 3:
    an evidence bundle that merely EXISTS is not enough, it must claim the
    specific authorization this call is trying to write. ``panel_sha`` is
    expected already-normalized (lowercase bare hex)."""
    if not isinstance(payload, Mapping):
        raise ExpectedIdentityError(
            "expected-identity: evidence bundle payload must be a JSON object"
        )
    if payload.get("kind") != PROMOTION_EVIDENCE_KIND:
        raise ExpectedIdentityError(
            f"expected-identity: evidence bundle kind must be "
            f"{PROMOTION_EVIDENCE_KIND!r}, got {payload.get('kind')!r}"
        )
    evidence_generation = payload.get(PROMOTION_EVIDENCE_GENERATION_KEY)
    if (
        not isinstance(evidence_generation, int)
        or isinstance(evidence_generation, bool)
        or evidence_generation != generation
    ):
        raise ExpectedIdentityError(
            "expected-identity: evidence bundle "
            f"{PROMOTION_EVIDENCE_GENERATION_KEY} {evidence_generation!r} "
            f"does not match the generation being bound ({generation!r}) — "
            "the evidence's OWN payload must name the exact authorization, "
            "not just exist"
        )
    evidence_sha = normalize_sha(payload.get(PROMOTION_EVIDENCE_PANEL_SHA_KEY))
    if evidence_sha is None or evidence_sha != panel_sha:
        raise ExpectedIdentityError(
            "expected-identity: evidence bundle "
            f"{PROMOTION_EVIDENCE_PANEL_SHA_KEY} "
            f"{payload.get(PROMOTION_EVIDENCE_PANEL_SHA_KEY)!r} does not "
            f"match the panel_sha being bound ({panel_sha!r}) — the "
            "evidence's OWN payload must name the exact authorization, not "
            "just exist"
        )


def record_expected_identity(
    state_root: str | Path | None = None,
    *,
    generation: int,
    panel_sha: str,
    evidence_ref: str,
    github_root: str | Path | None = None,
    git_probe: GitProbe | None = None,
) -> Path:
    """FORWARD-ONLY writer for the authorized-identity binding.

    ROUND 3 (Codex #485 follow-up — "make the binding a derived consequence
    of immutable deployment/promotion evidence, not a generic maintenance
    operation"): ``evidence_ref`` is now MANDATORY. It must resolve (via
    :func:`resolve_promotion_evidence_bundle` — the shared sibling-checkout
    convention, tamper-checked against ``STORE-MANIFEST.json`` when
    present) to a sealed ``kind: "model-identity-promotion"`` bundle whose
    OWN payload names EXACTLY the ``(generation, panel_sha)`` pair this
    call is trying to bind (:func:`_verify_promotion_evidence_payload`).
    ANY mismatch, unresolvable reference, or missing/malformed evidence
    payload raises ``ExpectedIdentityError`` and writes NOTHING — a caller
    can no longer author a binding purely from a self-supplied bundle file
    with no matching evidence. The evidence's reference and a content
    sha256 of the resolved bytes are persisted into the written record
    (``evidence_ref`` / ``evidence_sha256``) so a future auditor can see
    exactly which evidence authorized this binding without re-resolving a
    possibly-moved sibling checkout.

    Same epoch discipline as ``deployment_manifest.record_expected_generation``
    (atomic temp+``os.replace`` write via ``write_json_canonical``) as
    before — UNCHANGED, additive precondition only: REFUSES a generation
    decrease (a rollback is a NEW, higher generation that re-binds the
    older sha — history is never rewound); REFUSES re-binding the SAME
    generation to a different sha (a torn/duplicate apply, never
    legitimate); re-recording the identical ``(generation, panel_sha)``
    pair — e.g. a same-day re-run of the deploy flow — is an idempotent
    no-op (still requires currently-valid evidence: there is no "free
    pass" out of verification just because the write would be a no-op).

    This is the deploy/promote flow's post-verification hook: record the sha
    you just deployed, under the manifest generation you deployed it with,
    naming the sealed promotion evidence that authorized it.
    """
    normalized = normalize_sha(panel_sha)
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ExpectedIdentityError(
            f"expected-identity: generation must be an integer >= 1, got "
            f"{generation!r}"
        )
    if normalized is None or not _SHA256_RE.match(normalized):
        raise ExpectedIdentityError(
            f"expected-identity: panel_sha must be a 64-hex sha256, got "
            f"{panel_sha!r}"
        )
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith(
        EVIDENCE_REF_PREFIX
    ):
        raise ExpectedIdentityError(
            f"expected-identity: evidence_ref must be a content-addressed "
            f"{EVIDENCE_REF_PREFIX!r} record, got {evidence_ref!r}"
        )
    root = deploy_state_root(state_root)
    existing, problem = read_expected_identity(root)
    if problem is not None:
        raise ExpectedIdentityError(
            f"refusing to overwrite a malformed record: {problem}"
        )

    # The authority gate: resolve + verify the sealed evidence BEFORE any
    # forward-only bookkeeping or write — an evidence mismatch must refuse
    # regardless of whether the (generation, panel_sha) pair would
    # otherwise be a clean advance or a no-op re-record.
    _, evidence_bytes, evidence_payload = resolve_promotion_evidence_bundle(
        evidence_ref, github_root=github_root, git_probe=git_probe,
    )
    _verify_promotion_evidence_payload(
        evidence_payload, generation=generation, panel_sha=normalized,
    )
    evidence_sha256 = sha256_of_bytes(evidence_bytes)

    record_path = root / EXPECTED_IDENTITY_FILENAME
    if existing is not None:
        prior_generation = existing["generation"]
        prior_sha = existing["panel_sha"]
        if generation < prior_generation:
            raise ExpectedIdentityError(
                f"expected-identity is FORWARD-ONLY: refusing decrease "
                f"{prior_generation} -> {generation} (rollbacks re-bind under "
                "a NEW generation, never rewind the record)"
            )
        if generation == prior_generation:
            if normalized == prior_sha:
                return record_path  # idempotent re-record (same-day re-run)
            raise ExpectedIdentityError(
                f"expected-identity: refusing to re-bind generation "
                f"{generation} to a different sha ({prior_sha[:12]} -> "
                f"{normalized[:12]}) — an epoch is never reused"
            )
    payload = {
        "schema_version": EXPECTED_IDENTITY_SCHEMA_VERSION,
        "kind": EXPECTED_IDENTITY_KIND,
        "generation": generation,
        "panel_sha": normalized,
        "recorded_at": _utc_now_iso(),
        "evidence_ref": evidence_ref,
        "evidence_sha256": evidence_sha256,
    }
    write_json_canonical(record_path, payload)
    return record_path


# --- deployment-manifest side (the #477 reader; DIAGNOSTIC metadata only) ----------

def load_manifest_info(
    *,
    manifest_path: str | Path | None = None,
    state_root: str | Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """``(manifest_info, problem)`` from the #477 deployment-manifest reader.

    The v1 manifest carries NO model-artifact mapping, so nothing here can
    EXPLAIN an identity change — generation / deployed_at are diagnostic
    context, plus ``generation_status`` against the durable expected-
    generation record (``classify_generation`` — a stale/replayed or
    torn-apply manifest is itself reportable). Fail-soft: any contract
    violation returns ``(None, problem_text)`` instead of raising."""
    root = deploy_state_root(state_root)
    path = Path(manifest_path) if manifest_path else root / MACHINE_MANIFEST_FILENAME
    try:
        manifest = load_deployment_manifest(path)
    except DeploymentManifestError as exc:
        return None, str(exc)
    deployment = manifest.get("deployment") or {}
    deployed_at = str(deployment.get("deployed_at") or "")
    info: dict[str, Any] = {
        "path": str(path),
        "generation": manifest.get("generation"),
        "deployed_at": deployed_at or None,
        "state": deployment.get("state"),
        "generation_status": None,
    }
    try:
        record = read_expected_generation(root)
    except DeploymentManifestError:
        record = None
    if record is not None and isinstance(info["generation"], int):
        info["generation_status"] = classify_generation(
            info["generation"], int(record["generation"])
        )
    return info, None


# --- the classification core (pure; the unit under test) ---------------------------

def classify_transition(
    latest: ModelIdentity,
    previous: ModelIdentity | None,
    *,
    expected_identity: Mapping[str, Any] | None,
    promotion_ledger: Mapping[str, int] | None = None,
) -> tuple[str, list[str], list[str]]:
    """``(verdict, lines, missing)`` for one session-over-session transition.

    The ONLY things that can explain an identity change are (i) the recorded
    authorized binding naming the new sha (``explained_pin_advance``) or
    (ii) a promotions-ledger entry naming it (``explained_promotion``) — this
    gate is presence-only (any generation ever recorded for the sha), same
    as before round 2. A serving identity that CONTRADICTS an existing
    binding is an OUTAGE even when it did not change session-over-session
    (both sessions can be wrong).

    A SEPARATE, additional proof — that the PRIOR identity itself belonged
    to an authorized generation strictly OLDER than the one active now — is
    NOT decided here; see ``build_tripwire_report``'s chain-adjacency
    supporting check (round 2, using ``load_promotion_ledger``'s
    sha->generation map), which contributes a note/tag WITHOUT overriding
    the verdict returned by this function (the same pattern the manifest
    ``generation_status`` supporting check already uses).
    """
    promotion_ledger = promotion_ledger or {}
    lines: list[str] = []
    missing: list[str] = []

    if latest.panel_sha is None:
        missing.append("latest_panel_identity")
        lines.append(
            "monitoring coverage LOST: latest run bundle carries no panel "
            "artifact hash — serving identity cannot be established "
            "(fingerprint gap, see intraday_session_inputs)"
        )
        return VERDICT_COVERAGE_LOST, lines, missing

    binding_sha = (
        normalize_sha(expected_identity.get("panel_sha"))
        if isinstance(expected_identity, Mapping) else None
    )
    binding_desc = (
        f"binding {str(binding_sha)[:12]}… (generation "
        f"{expected_identity.get('generation')}, recorded_at "
        f"{expected_identity.get('recorded_at')})"
        if binding_sha and isinstance(expected_identity, Mapping) else None
    )

    # The binding check stands on its own: serving something the deploy flow
    # never recorded is an outage whether or not it changed overnight.
    if binding_sha is not None and latest.panel_sha != binding_sha:
        lines.append(
            f"serving identity {latest.short_sha}… CONTRADICTS the recorded "
            f"authorized {binding_desc} — an unauthorized model is serving"
        )
        if previous is not None and previous.panel_sha is not None:
            changed = previous.panel_sha != latest.panel_sha
            lines.append(
                f"session-over-session: {previous.short_sha}… -> "
                f"{latest.short_sha}… ({'changed' if changed else 'unchanged'};"
                f" prev session {previous.session_date or '?'})"
            )
        return VERDICT_BINDING_MISMATCH, lines, missing

    if previous is None or previous.panel_sha is None:
        missing.append("previous_session_identity")
        note = (
            f"monitoring coverage LOST: no previous-session identity to "
            f"compare against; latest panel {latest.short_sha}… "
            f"(session {latest.session_date or '?'})"
        )
        if binding_sha is not None:
            note += " — matches the recorded authorized binding"
        lines.append(note)
        return VERDICT_COVERAGE_LOST, lines, missing

    if latest.panel_sha == previous.panel_sha:
        line = (
            f"INFO panel identity unchanged: {latest.short_sha}… "
            f"({previous.session_date or '?'} -> {latest.session_date or '?'})"
        )
        if binding_sha is not None:
            line += " — matches the recorded authorized binding"
        else:
            line += " (no authorized-identity binding recorded; diagnostic)"
        lines.append(line)
        return VERDICT_UNCHANGED, lines, missing

    # Identity CHANGED — lead with the change so ntfy truncation can never
    # hide it (same discipline as the #480 collapse line).
    lines.append(
        f"panel identity changed: {previous.short_sha}… -> "
        f"{latest.short_sha}… (prev session {previous.session_date or '?'}, "
        f"latest {latest.session_date or '?'})"
    )

    if binding_sha is not None and latest.panel_sha == binding_sha:
        lines.append(
            f"INFO explained: the new identity IS the recorded authorized "
            f"{binding_desc} — a recorded pin advance"
        )
        return VERDICT_PIN_ADVANCE, lines, missing

    if latest.panel_sha in promotion_ledger:
        lines.append(
            "INFO explained: the new identity is a recorded promotion "
            f"(promotions ledger names {latest.short_sha}…)"
        )
        return VERDICT_PROMOTION, lines, missing

    lines.append(
        "UNEXPLAINED: no authorized-identity binding and no recorded "
        "promotion names the new sha — a DIFFERENT MODEL is serving without "
        "any deployment event (the 2026-06-25 silent-regression shape, "
        "#484 §7.2a)"
    )
    return VERDICT_UNEXPLAINED, lines, missing


# --- top-level builder --------------------------------------------------------------

def _identity_summary(identity: ModelIdentity | None) -> dict[str, Any]:
    if identity is None:
        return {}
    return {
        "panel_sha": identity.panel_sha,
        "run_id": identity.run_id,
        "session_date": identity.session_date,
        "source_path": identity.source_path,
    }


def build_tripwire_report(
    latest_bundle: Mapping[str, Any] | None,
    previous_bundle: Mapping[str, Any] | None,
    *,
    expected_identity: Mapping[str, Any] | None = None,
    expected_identity_problem: str | None = None,
    manifest_info: Mapping[str, Any] | None = None,
    manifest_problem: str | None = None,
    promotion_ledger: Mapping[str, int] | None = None,
    latest_path: str | Path | None = None,
    previous_path: str | Path | None = None,
    as_of: str | None = None,
    offline: bool = False,
    now: datetime | None = None,
) -> TripwireReport:
    """Render one identity comparison into a :class:`TripwireReport`.

    Default (scheduled-monitor) posture: lost coverage — missing latest /
    previous identity, unreadable manifest, malformed binding record — pages
    DEGRADED, because a monitor that dies quiet is the #484 failure mode
    repeated. ``offline=True`` (local forensics) records the same facts as
    quiet notes instead. Never raises either way.
    """
    latest = extract_model_identity(latest_bundle, source_path=latest_path)
    previous = (
        extract_model_identity(previous_bundle, source_path=previous_path)
        if isinstance(previous_bundle, Mapping)
        else None
    )
    promotion_ledger = promotion_ledger or {}

    verdict, lines, missing = classify_transition(
        latest,
        previous,
        expected_identity=expected_identity,
        promotion_ledger=promotion_ledger,
    )
    tag = _VERDICT_TO_TAG.get(verdict)
    if verdict == VERDICT_COVERAGE_LOST and not offline:
        tag = TAG_DEGRADED

    # Chain-adjacency supporting check (round 2 — Codex #485 follow-up:
    # "prove the chain, not just the endpoint"). The binding record above
    # only proves the LATEST identity is authorized NOW; it is a single,
    # forward-only slot with no history, so it cannot say whether the PRIOR
    # identity was itself authorized at an earlier generation. The
    # generation-bound promotions ledger (load_promotion_ledger) is used
    # here purely as that history. Scoped to a proven "explained" CHANGE
    # (PIN_ADVANCE / PROMOTION) — identity_unchanged has no chain to prove,
    # and the OUTAGE/mismatch verdicts already carry the worst tag.
    if verdict in (VERDICT_PIN_ADVANCE, VERDICT_PROMOTION) and previous is not None:
        current_generation = None
        if isinstance(expected_identity, Mapping):
            current_generation = expected_identity.get("generation")
        if not isinstance(current_generation, int) and manifest_info is not None:
            current_generation = manifest_info.get("generation")
        if not isinstance(current_generation, int):
            lines.append(
                "chain coverage gap: no active generation resolvable from "
                "the binding record or manifest — cannot certify the prior "
                "identity belonged to an earlier authorized generation"
            )
            if not offline:
                tag = worst_tag(tag, TAG_DEGRADED)
        elif current_generation == 1:
            lines.append(
                "chain: generation 1 is the epoch floor — no prior "
                "generation exists to chain the previous identity to"
            )
        else:
            previous_generation = promotion_ledger.get(previous.panel_sha) if previous.panel_sha else None
            if previous_generation is None:
                lines.append(
                    f"chain coverage gap: the promotions ledger carries no "
                    f"generation binding for the PRIOR identity "
                    f"{previous.short_sha}… — cannot certify it belonged to "
                    "an earlier authorized generation"
                )
                if not offline:
                    tag = worst_tag(tag, TAG_DEGRADED)
            elif previous_generation >= current_generation:
                lines.append(
                    f"chain BROKEN: the prior identity's ledger binding "
                    f"(generation {previous_generation}) is not OLDER than "
                    f"the active generation {current_generation} — a "
                    "non-monotonic/rollback shape; a forward chain cannot "
                    "be certified"
                )
                tag = worst_tag(tag, TAG_OUTAGE)  # a proven contradiction, never suppressed
            else:
                lines.append(
                    f"chain verified: prior identity bound to generation "
                    f"{previous_generation}, strictly older than the active "
                    f"generation {current_generation}"
                )

    # Coverage-plane notes: an absent binding record or unreadable manifest
    # is lost verification coverage — DEGRADED by default, quiet offline.
    if expected_identity is None:
        missing.append("expected_identity_binding")
        lines.append(
            "no authorized-identity binding record"
            + (f" ({expected_identity_problem})" if expected_identity_problem
               else " (deploy flow has not recorded one yet)")
            + " — identity changes cannot be verified as authorized"
        )
        if not offline and verdict not in (VERDICT_UNEXPLAINED, VERDICT_BINDING_MISMATCH):
            tag = worst_tag(tag, TAG_DEGRADED)
    if manifest_info is None:
        missing.append("deployment_manifest")
        lines.append(
            "deployment manifest unavailable"
            + (f" ({manifest_problem})" if manifest_problem else "")
        )
        if not offline:
            tag = worst_tag(tag, TAG_DEGRADED)
    else:
        lines.append(
            "manifest (diagnostic): generation "
            f"{manifest_info.get('generation')}, deployed_at "
            f"{manifest_info.get('deployed_at')}"
        )
        status = manifest_info.get("generation_status")
        if status is not None and status != GENERATION_OK:
            lines.append(
                f"manifest generation check: {status} (manifest generation "
                f"{manifest_info.get('generation')} vs the durable "
                "expected-generation record)"
            )
            tag = worst_tag(tag, TAG_DEGRADED)

    resolved_as_of = (
        as_of
        or latest.session_date
        or (previous.session_date if previous else None)
        or _today_iso(now)
    )
    report = TripwireReport(
        as_of=str(resolved_as_of),
        run_id=str(latest.run_id or f"{resolved_as_of}-identity-tripwire"),
        verdict=verdict,
        title_tag=tag,
        body_lines=lines,
        latest=_identity_summary(latest),
        previous=_identity_summary(previous),
        manifest=dict(manifest_info) if manifest_info else {},
        expected_identity=(
            dict(expected_identity) if isinstance(expected_identity, Mapping)
            else {}
        ),
        missing=missing,
    )
    if tag is not None:
        report.title = f"RENQUANT-104 {tag} {HEADLINE_COMPONENT} {report.as_of}"
    return report


# --- CLI -------------------------------------------------------------------------

def _validate_evidence_ref_arg(value: str) -> str:
    """Mirrors ``deploy_pin._validate_evidence_ref_arg`` exactly (same
    shape, same error message convention) — never a diverging second
    ``store://`` validator."""
    if not value.startswith(EVIDENCE_REF_PREFIX) or len(value) <= len(
        EVIDENCE_REF_PREFIX
    ):
        raise argparse.ArgumentTypeError(
            f"--evidence-ref must be a content-addressed "
            f"{EVIDENCE_REF_PREFIX}<record> reference, got {value!r}"
        )
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="model-identity-tripwire", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "--bundle-dir", default=None,
        help="directory searched (recursively) for the latest + previous-"
             "session run_bundle*.json",
    )
    src.add_argument(
        "--latest-bundle", default=None, help="path to the latest run_bundle.json",
    )
    parser.add_argument(
        "--previous-bundle", default=None,
        help="path to the previous session's run_bundle.json "
             "(with --latest-bundle)",
    )
    parser.add_argument(
        "--manifest", default=None,
        help="deployment-manifest path (default: <state-root>/"
             f"{MACHINE_MANIFEST_FILENAME}); diagnostic metadata only",
    )
    parser.add_argument(
        "--state-root", default=None,
        help="deployed-state root (default: $RENQUANT_DEPLOY_STATE_ROOT or "
             "~/.renquant/deploy); holds the authorized-identity binding "
             f"record {EXPECTED_IDENTITY_FILENAME}",
    )
    parser.add_argument(
        "--promotions-ledger", default=None,
        help="optional JSON/JSONL ledger of {sha, generation} promotion "
             "events; an identity change matching a recorded promotion sha "
             "passes with INFO, and (round 2) the generation binding also "
             "anchors the chain-adjacency check for the PRIOR identity — a "
             "legacy bare-sha entry (no generation) is parsed fail-soft but "
             "cannot anchor that check, see load_promotion_ledger",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="local-forensics posture: missing inputs (coverage loss) are "
             "recorded as quiet notes instead of paging DEGRADED",
    )
    parser.add_argument(
        "--record-expected", action="store_true",
        help="maintenance mode (the deploy-flow hook): record the latest "
             "bundle's panel sha as the authorized binding under the current "
             "manifest generation, then exit. FORWARD-ONLY / atomic; refuses "
             "generation decreases and same-generation re-binds. REQUIRES "
             "--evidence-ref (round 3, Codex #485): the binding must be a "
             "derived consequence of sealed promotion evidence, never a "
             "caller-supplied bundle alone.",
    )
    parser.add_argument(
        "--evidence-ref",
        type=_validate_evidence_ref_arg,
        default=None,
        help="REQUIRED with --record-expected: sealed store://<record> "
             "promotion-evidence reference (renquant-artifacts sibling-"
             "checkout convention, same as deploy-pin) whose payload names "
             "a kind: 'model-identity-promotion' record with the EXACT "
             "generation/panel_sha being bound; the binding is refused "
             "(no write) if it doesn't resolve or doesn't match.",
    )
    parser.add_argument(
        "--github-root", default=None,
        help="checkout parent containing renquant-* sibling repos, used to "
             "resolve --evidence-ref (default: $RENQUANT_GITHUB_ROOT or "
             "this repo's sibling root); only meaningful with "
             "--record-expected",
    )
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD override")
    parser.add_argument("--topic", default=os.environ.get("NTFY_TOPIC", "renquant"))
    parser.add_argument("--quiet", action="store_true", help="never send the ntfy page")
    return parser.parse_args(argv)


def _resolve_bundles(args: argparse.Namespace) -> tuple[Path | None, Path | None, int]:
    latest_path: Path | None = None
    previous_path: Path | None = None
    if args.latest_bundle:
        latest_path = Path(args.latest_bundle)
        if args.previous_bundle:
            previous_path = Path(args.previous_bundle)
    elif args.bundle_dir:
        latest_path, previous_path = find_session_bundles(args.bundle_dir)
        if latest_path is None:
            print(
                f"identity-tripwire: no run_bundle*.json under {args.bundle_dir}",
                file=sys.stderr,
            )
            return None, None, 3
    return latest_path, previous_path, 0


def _run_record_expected(args: argparse.Namespace, latest_bundle: Any) -> int:
    identity = extract_model_identity(
        latest_bundle if isinstance(latest_bundle, Mapping) else None
    )
    if identity.panel_sha is None:
        print(
            "identity-tripwire: --record-expected needs a bundle with a "
            "panel artifact hash",
            file=sys.stderr,
        )
        return 3
    manifest_info, manifest_problem = load_manifest_info(
        manifest_path=args.manifest, state_root=args.state_root,
    )
    generation = manifest_info.get("generation") if manifest_info else None
    if not isinstance(generation, int):
        print(
            "identity-tripwire: --record-expected needs a readable "
            f"deployment manifest for the generation ({manifest_problem})",
            file=sys.stderr,
        )
        return 3
    if not args.evidence_ref:
        print(
            "identity-tripwire: --record-expected requires --evidence-ref "
            "(round 3, Codex #485 follow-up) — a sealed store://<record> "
            "promotion-evidence reference whose payload names this exact "
            "generation/panel_sha; a caller-supplied bundle file alone can "
            "no longer authorize a binding",
            file=sys.stderr,
        )
        return 3
    try:
        path = record_expected_identity(
            args.state_root, generation=generation, panel_sha=identity.panel_sha,
            evidence_ref=args.evidence_ref,
            github_root=args.github_root,
        )
    except ExpectedIdentityError as exc:
        print(f"identity-tripwire: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "recorded": str(path),
        "generation": generation,
        "panel_sha": identity.panel_sha,
        "evidence_ref": args.evidence_ref,
    }, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    latest_path, previous_path, rc = _resolve_bundles(args)
    if rc:
        return rc

    latest_bundle = _load_json(latest_path)
    if latest_path is not None and latest_bundle is None:
        print(
            f"identity-tripwire: could not read bundle at {latest_path}",
            file=sys.stderr,
        )
        return 3
    if args.record_expected:
        return _run_record_expected(args, latest_bundle)
    previous_bundle = _load_json(previous_path)

    expected_identity, expected_problem = read_expected_identity(args.state_root)
    manifest_info, manifest_problem = load_manifest_info(
        manifest_path=args.manifest, state_root=args.state_root,
    )

    report = build_tripwire_report(
        latest_bundle if isinstance(latest_bundle, Mapping) else None,
        previous_bundle if isinstance(previous_bundle, Mapping) else None,
        expected_identity=expected_identity,
        expected_identity_problem=expected_problem,
        manifest_info=manifest_info,
        manifest_problem=manifest_problem,
        promotion_ledger=load_promotion_ledger(args.promotions_ledger),
        latest_path=latest_path,
        previous_path=previous_path,
        as_of=args.as_of,
        offline=args.offline,
    )
    emit_alert(report, topic=args.topic, quiet=args.quiet, only_alerts=True)
    print(json.dumps(report.to_payload(), indent=2, sort_keys=True))

    if report.title_tag == TAG_OUTAGE:
        return 2
    if report.title_tag == TAG_DEGRADED:
        return 1
    return 0


__all__ = [
    "EXPECTED_IDENTITY_FILENAME",
    "EXPECTED_IDENTITY_KIND",
    "EXPECTED_IDENTITY_SCHEMA_VERSION",
    "HEADLINE_COMPONENT",
    "OWNER_REPO",
    "PROMOTION_EVIDENCE_GENERATION_KEY",
    "PROMOTION_EVIDENCE_KIND",
    "PROMOTION_EVIDENCE_PANEL_SHA_KEY",
    "SCHEMA_VERSION",
    "VERDICT_BINDING_MISMATCH",
    "VERDICT_COVERAGE_LOST",
    "VERDICT_PIN_ADVANCE",
    "VERDICT_PROMOTION",
    "VERDICT_UNCHANGED",
    "VERDICT_UNEXPLAINED",
    "ExpectedIdentityError",
    "ModelIdentity",
    "TripwireReport",
    "build_tripwire_report",
    "classify_transition",
    "extract_model_identity",
    "find_session_bundles",
    "load_manifest_info",
    "load_promotion_ledger",
    "main",
    "normalize_sha",
    "read_expected_identity",
    "record_expected_identity",
    "resolve_promotion_evidence_bundle",
    "session_date_of",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
