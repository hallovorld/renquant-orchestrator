"""Model-identity regression tripwire — the #484 §7.2a consumer.

WHY THIS EXISTS. Between the 2026-06-25 and 06-26 sessions the production
panel artifact silently REGRESSED from the 06-21 model to the 05-18 model and
stayed regressed for FIVE sessions (06-26..07-02), unalerted — a 39-45-day-old
model held primary in direct conflict with the 28d freshness policy, and by
07-03 the tree flipped back, again without any promotion event (orchestrator
PR #484 §7.2a, byte-verified against run-bundle ``artifact_hashes.panel``).
Nothing in the stack noticed that a DIFFERENT MODEL was serving. This module
is the tripwire the incident was missing: it compares the latest run bundle's
model identity against (a) the previous session's bundle and (b) the
deployment manifest (#477 reader — the pin authority that says which state
SHOULD be serving), and pages OUTAGE when the identity changed with no pin
change and no recorded promotion.

VERDICTS (the three-way contract):

  ``identity_unchanged``           — same panel sha as the previous session.
                                     INFO line, no alert.
  ``explained_pin_advance``        — identity changed AND the deployment
                                     manifest records a deployment at/after
                                     the previous session (a pin advance can
                                     legitimately swap the serving model).
                                     INFO line, no alert.
  ``explained_promotion``          — identity changed AND the new sha appears
                                     in the (optional) promotions ledger.
                                     INFO line, no alert.
  ``unexplained_identity_change``  — identity changed, manifest shows NO
                                     deployment since the previous session,
                                     no promotion recorded. The 06-25
                                     regression shape. OUTAGE page (reuses
                                     the #480 headline vocabulary).
  ``unverifiable_identity_change`` — identity changed but the manifest is
                                     missing/unreadable or the session dates
                                     cannot be resolved. DEGRADED page — the
                                     change is real, the explanation plane is
                                     dark.
  ``insufficient_evidence``        — no latest identity, or no previous
                                     session bundle to compare against.
                                     Fail-soft: recorded as missing notes,
                                     never an exception, never a page.

Properties (house monitor conventions, same as ``outage_monitor``):

  * **read-only** — consumes run-bundle JSONs + the deployment manifest;
    never touches broker, live state, or production paths.
  * **fail-soft** — every missing/malformed input degrades to a recorded
    note; the tripwire's own crash must not dark the session it audits.
  * **DARK by default** — wire-ready for the daily flow but invoked by NO
    scheduled job yet; wiring into daily automation is a separate landing
    (machine-landing, ask-first).

Identity source: ``run_bundle["artifact_hashes"]["panel"]`` — the exact field
the #484 forensics used to byte-verify the regression (sessions 06-22..25
stamped ``04d7a381…``; 06-26..07-02 stamped ``5ce63326…``).
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

from .deployment_manifest import (
    DeploymentManifestError,
    GENERATION_OK,
    MACHINE_MANIFEST_FILENAME,
    classify_generation,
    deploy_state_root,
    load_deployment_manifest,
    read_expected_generation,
)
from .outage_monitor import (
    TAG_DEGRADED,
    TAG_OUTAGE,
    emit_alert,
    worst_tag,
)

SCHEMA_VERSION = 1
OWNER_REPO = "renquant-orchestrator"

#: The headline component after the #480 tag — sibling of SESSION-INTEGRITY.
HEADLINE_COMPONENT = "MODEL-IDENTITY"

# --- verdict vocabulary -------------------------------------------------------
VERDICT_UNCHANGED = "identity_unchanged"
VERDICT_PIN_ADVANCE = "explained_pin_advance"
VERDICT_PROMOTION = "explained_promotion"
VERDICT_UNEXPLAINED = "unexplained_identity_change"
VERDICT_UNVERIFIABLE = "unverifiable_identity_change"
VERDICT_INSUFFICIENT = "insufficient_evidence"

_VERDICT_TO_TAG: dict[str, str | None] = {
    VERDICT_UNCHANGED: None,
    VERDICT_PIN_ADVANCE: None,
    VERDICT_PROMOTION: None,
    VERDICT_UNEXPLAINED: TAG_OUTAGE,
    VERDICT_UNVERIFIABLE: TAG_DEGRADED,
    VERDICT_INSUFFICIENT: None,
}

_TAG_PRIORITY = {TAG_OUTAGE: 5, TAG_DEGRADED: 4}

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
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
    verdict: str = VERDICT_INSUFFICIENT
    title_tag: str | None = None
    title: str | None = None
    body_lines: list[str] = field(default_factory=list)
    latest: dict[str, Any] = field(default_factory=dict)
    previous: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
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
            "missing": self.missing,
        }


# --- low-level helpers ----------------------------------------------------------

def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


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


def load_promotion_shas(path: str | Path | None) -> set[str]:
    """Normalized shas from an optional promotions ledger (JSON array or JSONL).

    Fail-soft: a missing/unreadable ledger is an empty set — absence of a
    ledger never crashes the tripwire (it just cannot explain changes via
    promotions)."""
    if path is None:
        return set()
    p = Path(path)
    if not p.exists() or not p.is_file():
        return set()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return set()
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
    shas: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        for key in _PROMOTION_SHA_KEYS:
            sha = normalize_sha(entry.get(key))
            if sha:
                shas.add(sha)
    return shas


# --- deployment-manifest side (the #477 reader) -----------------------------------

def load_manifest_info(
    *,
    manifest_path: str | Path | None = None,
    state_root: str | Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """``(manifest_info, problem)`` from the #477 deployment-manifest reader.

    ``manifest_info`` carries generation / deployed_at / deployed_date /
    state, plus ``generation_status`` when the durable expected-generation
    record exists (``classify_generation`` — a stale/replayed or torn-apply
    manifest is itself reportable). Fail-soft: any contract violation returns
    ``(None, problem_text)`` instead of raising."""
    root = deploy_state_root(state_root)
    path = Path(manifest_path) if manifest_path else root / MACHINE_MANIFEST_FILENAME
    try:
        manifest = load_deployment_manifest(path)
    except DeploymentManifestError as exc:
        return None, str(exc)
    deployment = manifest.get("deployment") or {}
    deployed_at = str(deployment.get("deployed_at") or "")
    match = _DATE_RE.match(deployed_at)
    info: dict[str, Any] = {
        "path": str(path),
        "generation": manifest.get("generation"),
        "deployed_at": deployed_at or None,
        "deployed_date": match.group(1) if match else None,
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
    manifest_info: Mapping[str, Any] | None,
    manifest_problem: str | None = None,
    promotion_shas: set[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """``(verdict, lines, missing)`` for one session-over-session transition."""
    promotion_shas = promotion_shas or set()
    lines: list[str] = []
    missing: list[str] = []

    if latest.panel_sha is None:
        missing.append("latest_panel_identity")
        lines.append(
            "latest run bundle carries no panel artifact hash — identity "
            "cannot be established (fingerprint gap, see "
            "intraday_session_inputs)"
        )
        return VERDICT_INSUFFICIENT, lines, missing

    if previous is None or previous.panel_sha is None:
        missing.append("previous_session_identity")
        lines.append(
            f"no previous-session identity to compare against; baseline "
            f"recorded: panel {latest.short_sha}… "
            f"(session {latest.session_date or '?'})"
        )
        return VERDICT_INSUFFICIENT, lines, missing

    if latest.panel_sha == previous.panel_sha:
        lines.append(
            f"INFO panel identity unchanged: {latest.short_sha}… "
            f"({previous.session_date or '?'} -> {latest.session_date or '?'})"
        )
        return VERDICT_UNCHANGED, lines, missing

    # Identity CHANGED — lead with the change so ntfy truncation can never
    # hide it (same discipline as the #480 collapse line).
    change_line = (
        f"panel identity changed: {previous.short_sha}… -> "
        f"{latest.short_sha}… (prev session {previous.session_date or '?'}, "
        f"latest {latest.session_date or '?'})"
    )
    lines.append(change_line)

    if latest.panel_sha in promotion_shas:
        lines.append(
            "INFO explained: the new identity is a recorded promotion "
            f"(promotions ledger names {latest.short_sha}…)"
        )
        return VERDICT_PROMOTION, lines, missing

    if manifest_info is None:
        missing.append("deployment_manifest")
        lines.append(
            "deployment manifest unavailable — cannot resolve which pin "
            "should serve"
            + (f" ({manifest_problem})" if manifest_problem else "")
        )
        return VERDICT_UNVERIFIABLE, lines, missing

    deployed_date = manifest_info.get("deployed_date")
    generation = manifest_info.get("generation")
    if deployed_date is None or previous.session_date is None:
        missing.append("comparable_dates")
        lines.append(
            "cannot temporally resolve the pin state (manifest deployed_at "
            f"{manifest_info.get('deployed_at') or '?'} vs prev session "
            f"{previous.session_date or '?'})"
        )
        return VERDICT_UNVERIFIABLE, lines, missing

    if deployed_date >= previous.session_date:
        lines.append(
            "INFO explained: pin advanced since the previous session "
            f"(manifest generation {generation}, deployed_at "
            f"{manifest_info.get('deployed_at')})"
        )
        return VERDICT_PIN_ADVANCE, lines, missing

    lines.append(
        "UNEXPLAINED: no pin change since "
        f"{manifest_info.get('deployed_at')} (manifest generation "
        f"{generation}) and no recorded promotion — a DIFFERENT MODEL is "
        "serving without any deployment event (the 2026-06-25 silent-"
        "regression shape, #484 §7.2a)"
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
    manifest_info: Mapping[str, Any] | None,
    manifest_problem: str | None = None,
    promotion_shas: set[str] | None = None,
    latest_path: str | Path | None = None,
    previous_path: str | Path | None = None,
    as_of: str | None = None,
    now: datetime | None = None,
) -> TripwireReport:
    """Render one identity comparison into a :class:`TripwireReport`.

    Fail-soft end to end: missing bundles/manifest produce recorded
    ``missing`` notes (and at worst a DEGRADED tag when a real change cannot
    be verified) — never an exception, never an invented verdict."""
    latest = extract_model_identity(latest_bundle, source_path=latest_path)
    previous = (
        extract_model_identity(previous_bundle, source_path=previous_path)
        if isinstance(previous_bundle, Mapping)
        else None
    )

    verdict, lines, missing = classify_transition(
        latest,
        previous,
        manifest_info=manifest_info,
        manifest_problem=manifest_problem,
        promotion_shas=promotion_shas,
    )
    tag = _VERDICT_TO_TAG.get(verdict)

    # Supporting check: a manifest whose generation disagrees with the durable
    # expected-generation record is itself a stale/replayed or torn state —
    # DEGRADED contribution, never downgrades an OUTAGE (worst wins).
    if manifest_info is not None:
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
        missing=missing,
    )
    if tag is not None:
        report.title = f"RENQUANT-104 {tag} {HEADLINE_COMPONENT} {report.as_of}"
    return report


# --- CLI -------------------------------------------------------------------------

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
             f"{MACHINE_MANIFEST_FILENAME})",
    )
    parser.add_argument(
        "--state-root", default=None,
        help="deployed-state root (default: $RENQUANT_DEPLOY_STATE_ROOT or "
             "~/.renquant/deploy)",
    )
    parser.add_argument(
        "--promotions-ledger", default=None,
        help="optional JSON/JSONL ledger of promotion events; an identity "
             "change matching a recorded promotion sha passes with INFO",
    )
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD override")
    parser.add_argument("--topic", default=os.environ.get("NTFY_TOPIC", "renquant"))
    parser.add_argument("--quiet", action="store_true", help="never send the ntfy page")
    parser.add_argument(
        "--require-inputs", action="store_true",
        help="exit 3 when no comparison was possible (insufficient evidence)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

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
            return 3

    latest_bundle = _load_json(latest_path)
    if latest_path is not None and latest_bundle is None:
        print(
            f"identity-tripwire: could not read bundle at {latest_path}",
            file=sys.stderr,
        )
        return 3
    previous_bundle = _load_json(previous_path)

    manifest_info, manifest_problem = load_manifest_info(
        manifest_path=args.manifest, state_root=args.state_root,
    )

    report = build_tripwire_report(
        latest_bundle if isinstance(latest_bundle, Mapping) else None,
        previous_bundle if isinstance(previous_bundle, Mapping) else None,
        manifest_info=manifest_info,
        manifest_problem=manifest_problem,
        promotion_shas=load_promotion_shas(args.promotions_ledger),
        latest_path=latest_path,
        previous_path=previous_path,
        as_of=args.as_of,
    )
    emit_alert(report, topic=args.topic, quiet=args.quiet, only_alerts=True)
    print(json.dumps(report.to_payload(), indent=2, sort_keys=True))

    if report.verdict == VERDICT_INSUFFICIENT:
        return 3 if args.require_inputs else 0
    if report.title_tag == TAG_OUTAGE:
        return 2
    if report.title_tag == TAG_DEGRADED:
        return 1
    return 0


__all__ = [
    "HEADLINE_COMPONENT",
    "OWNER_REPO",
    "SCHEMA_VERSION",
    "VERDICT_INSUFFICIENT",
    "VERDICT_PIN_ADVANCE",
    "VERDICT_PROMOTION",
    "VERDICT_UNCHANGED",
    "VERDICT_UNEXPLAINED",
    "VERDICT_UNVERIFIABLE",
    "ModelIdentity",
    "TripwireReport",
    "build_tripwire_report",
    "classify_transition",
    "extract_model_identity",
    "find_session_bundles",
    "load_manifest_info",
    "load_promotion_shas",
    "main",
    "normalize_sha",
    "session_date_of",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
