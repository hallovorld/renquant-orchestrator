"""Canonical G4 shadow decision job + immutable evidence store — step 2.

Implements the orchestrator's share of the merged G4 re-registration v4
amendment (renquant-model#61, ``experiments/ensemble_phase0/
DESIGN_AMENDMENT_v4_executable_next_open_evaluation.md`` §5 step 2:
"Implement the orchestrator's canonical job, immutable decision/fill
records, and run-bundle fields; prove duplicate/watermark/fill failure
behavior"), consuming the merged step-1 public contract
``renquant_pipeline.decision_schedule`` (renquant-pipeline#209).

SHADOW ONLY — THIS MODULE NEVER PLACES AN ORDER ANYWHERE. The v4 §2
"declared order set scheduled for the first regular-session open of T+1"
is a *declared intent record* persisted for evidence; there is no broker
import, no execution-context wiring, and no side effect beyond writing
JSON files under the caller-chosen evidence root. The job is NOT
scheduled: no launchd entry, no ``ops/launchd_manifest.json`` change —
scheduling/activation is a later governed step (Phase 0 stays BLOCKED
per the amendment; this builds the machinery only).

What lives here (write side):

* :func:`resolve_session_window` — the orchestrator-owned resolution the
  step-1 contract delegates to the caller (pipeline#209 module docstring:
  "Resolving the frozen, versioned calendar … is the caller's job via
  ``renquant_common.market_calendar``"). It resolves decision session
  T's official close (early-close aware: half days close at 13:00 ET,
  not 16:00) and the first regular-session open after T into the
  contract's :class:`~renquant_pipeline.decision_schedule.SessionWindow`.
  The step-1 approval requires an early-close adversarial test of exactly
  this seam (reviewer requirement (b)); ``tests/test_g4_shadow_job.py``
  carries it against both a deterministic fake calendar and the real
  NYSE calendar.
* :func:`equal_weight_scores` — the L1 arm's frozen equal-weight
  combination (v4 §3: "L1 is the single frozen equal-weight
  combination"). Pure, deterministic arithmetic over caller-supplied
  per-expert score maps; fail-closed on mismatched universes or
  non-finite scores. No model internals live here (the experts' scores
  are produced by their owning repos).
* :func:`build_arm_record` / :func:`run_g4_shadow_session` — one
  immutable decision record per arm per session with every v4 §2 field:
  immutable ``decision_session=T``; declared input watermark computed
  from the manifested input snapshots (never hand-declared); a complete
  input/artifact/universe manifest (the universe rides as a REQUIRED
  manifested input named ``"universe"``, so its digest is pinned in
  ``input_manifest`` — reported interpretation, see the progress doc);
  frozen ``calendar_id`` / ``price_source_id``; the declared order set
  pinned to open(T+1); a deterministic job identity minted via the
  contract's :func:`~renquant_pipeline.decision_schedule.job_identity`
  (NEVER via ``hash_jsonable`` directly — its ``_strip_volatile`` would
  silently drop keys; step-1 approval, non-blocking observation 1).
* :func:`decision_digest_of` — the decision digest is RECOMPUTED over
  the FULL decision content (scores, orders, manifests, frozen ids), so
  a divergent duplicate cannot carry an identical ``decision_digest``
  (step-1 approval, non-blocking observation 2). No volatile-key
  stripping, by design.
* :class:`G4EvidenceStore` — append-only, digest-named persistence:
  write-once files (0o444, exclusive create via hard-link), re-run with
  identical inputs is byte-identical and lands as an admissible retry
  no-op; a retry differing ONLY in the volatile ``run_bundle_timestamp``
  keeps the FIRST record untouched (v4 §2: the timestamp is evidence
  only) and logs the attempt; any other overwrite attempt raises
  :class:`G4EvidenceIntegrityError` and the original bytes survive.
  A divergent duplicate (same job identity, different decision content)
  lands SIDE-BY-SIDE under its own digest-name — never resolved by
  latest-commit; the admission ledger (:mod:`g4_admission`) flags it.

The read side — session admission, failure classification with the
documented-outage qualifier, budget attribution, and the run-bundle
block — lives in :mod:`renquant_orchestrator.g4_admission`.

Evidence layout (all paths under a caller-chosen root; NEVER a
production path — LONG ledger #2):

.. code-block:: text

    <root>/
      inputs/<sha256hex>.json                    content-addressed input snapshots
      sessions/<T>/
        records/<arm>-<job12>-<dec12>.json       qualifying decision records
        records/<arm>-failure-<hex12>.json       declared-failure records
        attempts.jsonl                           append-only attempt log (evidence)
        admission/admission-<hex12>.json         admission ledger entries
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from renquant_pipeline.decision_schedule import (
    EXPECTED_ARMS,
    KNOWN_FAILURE_KINDS,
    RECORD_SCHEMA_VERSION,
    SessionWindow,
    job_identity,
    validate_arm_record,
)

#: Version of the orchestrator-side G4 evidence schema (records + store
#: layout). Independent of the pipeline contract version, which every
#: verdict already carries.
G4_EVIDENCE_SCHEMA_VERSION = 1

#: Canonical schema tag hashed into every decision digest.
DECISION_DIGEST_SCHEMA = "g4_shadow/decision_digest/v1"

#: The record's execution-mode marker. This job is SHADOW ONLY; the
#: constant is written into every record and verified on persist so a
#: record claiming live execution can never enter the evidence store.
EXECUTION_MODE_SHADOW = "shadow"

#: The REQUIRED name of the universe input snapshot (v4 §2 "complete
#: input/artifact/universe manifest": the universe is manifested as a
#: digest-bearing input, so the record's ``input_manifest`` pins it).
UNIVERSE_INPUT_NAME = "universe"

#: Closed vocabulary for structured outage-evidence references (P0-3 of
#: the 2026-07-18 review: a free-form non-empty string is self-declarable
#: and can buy a ``B_shared`` charge; a structured reference at least
#: forces the claimant to commit to a checkable category, a concrete
#: incident/task/URL pointer, and an observation time).
OUTAGE_EVIDENCE_KINDS = frozenset(
    {
        "venue_halt",
        "calendar_anomaly",
        "data_vendor_outage",
        "infra_shared",
    }
)

#: The three REQUIRED fields of one structured outage-evidence reference.
OUTAGE_EVIDENCE_FIELDS = ("kind", "ref", "observed_at")

_DIGEST_PREFIX = "sha256:"


class G4EvidenceIntegrityError(RuntimeError):
    """An append-only invariant was violated (overwrite attempt, in-place
    divergence, or a record failing its own declared digests). The store
    never repairs, replaces, or deletes — the conflicting artifacts stay
    side-by-side for forensics and the error is raised loudly."""


def _canonical_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, compact separators, UTF-8.

    Matches the canonicalization ``renquant_pipeline.decision_schedule.
    job_identity`` uses, WITHOUT any volatile-key stripping — decision
    content must never be silently dropped from a digest (step-1
    approval, non-blocking observation 1: mint identities via
    ``job_identity``, never ``hash_jsonable``)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def _digest_hex(value: str) -> str:
    return value[len(_DIGEST_PREFIX):]


def _require_aware(value: dt.datetime, name: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")
    return value


def outage_reference_error(reference: Any) -> "str | None":
    """Shape-validate ONE structured outage-evidence reference.

    The required shape (all three fields, no substitutes — 2026-07-18
    review P0-3):

    .. code-block:: python

        {
            "kind": <one of OUTAGE_EVIDENCE_KINDS>,
            "ref": <non-empty incident/task/URL string>,
            "observed_at": <ISO-8601 UTC timestamp string>,
        }

    Returns ``None`` when well-formed, otherwise a stable human-readable
    error string. This is deliberately SHAPE validation only: it does not
    resolve or verify the referenced incident — content-addressed /
    operator-verified evidence is the pinned pre-pilot follow-up (see the
    progress doc's pre-pilot hardening requirements)."""
    if not isinstance(reference, Mapping):
        return "reference is not a structured mapping"
    kind = reference.get("kind")
    if kind not in OUTAGE_EVIDENCE_KINDS:
        return (
            f"kind {kind!r} is not one of {sorted(OUTAGE_EVIDENCE_KINDS)}"
        )
    ref = reference.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        return "ref must be a non-empty incident/task/URL string"
    observed_at = reference.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.strip():
        return "observed_at must be an ISO-8601 UTC timestamp string"
    try:
        parsed = dt.datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return f"observed_at {observed_at!r} is not an ISO-8601 timestamp"
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return (
            f"observed_at {observed_at!r} must be UTC "
            "(timezone-aware with a +00:00 offset)"
        )
    return None


def normalized_outage_reference(reference: Mapping[str, Any]) -> "dict[str, str]":
    """The canonical persisted form of one VALIDATED reference: exactly
    the three required fields, stringified, extra keys dropped."""
    return {name: str(reference[name]) for name in OUTAGE_EVIDENCE_FIELDS}


# ---------------------------------------------------------------------------
# Session-window resolution (orchestrator-owned; step-1 pinned semantics 5)
# ---------------------------------------------------------------------------

def resolve_session_window(
    decision_session: str,
    *,
    calendar: Any | None = None,
    max_lookahead_days: int = 15,
) -> SessionWindow:
    """Resolve decision session T against the frozen exchange calendar.

    Returns the step-1 contract's :class:`SessionWindow` — ``close`` is
    T's OFFICIAL close (an early-close half day yields its real 13:00 ET
    close, not a hardcoded 16:00 — reviewer requirement (b) pins this
    with an adversarial test), ``next_open``/``next_open_session`` are
    the first regular session strictly after T.

    ``calendar`` is any ``renquant_common.market_calendar.SessionCalendar``
    (``session_bounds(day) -> SessionBounds | None``); ``None`` selects
    the real NYSE calendar. Fail-closed (house rule): T not being a
    session, or no session inside ``max_lookahead_days`` after T, raises
    ``ValueError`` — caller input errors are never validation outcomes.
    """
    day = dt.date.fromisoformat(decision_session)
    if calendar is None:
        from renquant_common.market_calendar import (  # noqa: PLC0415 — deferred, heavy backend
            default_session_calendar,
        )

        calendar = default_session_calendar()
    bounds = calendar.session_bounds(day)
    if bounds is None:
        raise ValueError(
            f"decision session {decision_session!r} is not a "
            f"{getattr(calendar, 'name', '?')} session (fail-closed)"
        )
    for offset in range(1, max_lookahead_days + 1):
        candidate = day + dt.timedelta(days=offset)
        nxt = calendar.session_bounds(candidate)
        if nxt is not None:
            return SessionWindow(
                close=bounds.close,
                next_open=nxt.open,
                next_open_session=candidate.isoformat(),
            )
    raise ValueError(
        f"no {getattr(calendar, 'name', '?')} session found in the "
        f"{max_lookahead_days}-day window after {decision_session!r} (fail-closed)"
    )


# ---------------------------------------------------------------------------
# L1 equal-weight combination (v4 §3 — frozen arithmetic, no model internals)
# ---------------------------------------------------------------------------

def equal_weight_scores(
    expert_scores: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """The L1 arm's single frozen equal-weight combination (v4 §3).

    ``expert_scores`` maps expert name -> per-ticker score map. Every
    expert must cover the IDENTICAL ticker set (a missing score would
    silently reweight the combination — fail-closed ``ValueError``
    instead), and every score must be finite. Deterministic: output keys
    sorted, plain arithmetic mean."""
    if not expert_scores:
        raise ValueError("equal_weight_scores requires at least one expert")
    tickers: set[str] | None = None
    for expert, scores in expert_scores.items():
        keys = set(scores)
        if not keys:
            raise ValueError(f"expert {expert!r} has an empty score map")
        if tickers is None:
            tickers = keys
        elif keys != tickers:
            raise ValueError(
                "expert score maps must cover the identical ticker set "
                f"(fail-closed): {expert!r} differs by "
                f"{sorted(keys ^ tickers)!r}"
            )
        for ticker, value in scores.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(
                    f"expert {expert!r} score for {ticker!r} is not a finite "
                    f"number: {value!r}"
                )
    assert tickers is not None
    n = len(expert_scores)
    return {
        ticker: sum(float(scores[ticker]) for scores in expert_scores.values()) / n
        for ticker in sorted(tickers)
    }


# ---------------------------------------------------------------------------
# Input snapshots (content-addressed; watermark recomputable from bytes)
# ---------------------------------------------------------------------------

def input_snapshot_bytes(
    name: str,
    *,
    event_times: Sequence[dt.datetime],
    payload: Any,
) -> bytes:
    """Canonical bytes of one manifested input snapshot.

    The snapshot carries its own per-row/per-source ``event_times`` so
    the admission-side watermark recomputation can re-derive the maximum
    event-time FROM BYTES resolved by digest (v4 §2 r2: the declared
    watermark is not self-certifying; the step-1 default hook only reads
    the record's own manifest — production admission must inject the
    byte-level hook, which :func:`g4_admission.recompute_watermark_from_store`
    provides)."""
    if not name:
        raise ValueError("input snapshot name must be non-empty")
    if not event_times:
        raise ValueError(f"input snapshot {name!r} must declare at least one event time")
    times = sorted(
        _require_aware(t, f"input snapshot {name!r} event time").isoformat()
        for t in event_times
    )
    return _canonical_bytes(
        {
            "kind": "g4_input_snapshot",
            "schema_version": G4_EVIDENCE_SCHEMA_VERSION,
            "name": str(name),
            "event_times": times,
            "payload": payload,
        }
    )


def max_event_time_from_bytes(data: bytes) -> "dt.datetime | None":
    """Recompute the maximum event-time from a snapshot's BYTES.

    Fail-closed: anything unparseable / naive / empty returns ``None``,
    which the step-1 validator treats as a watermark recompute mismatch."""
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping) or payload.get("kind") != "g4_input_snapshot":
        return None
    times: list[dt.datetime] = []
    raw = payload.get("event_times")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        return None
    for value in raw:
        if not isinstance(value, str):
            return None
        try:
            parsed = dt.datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        times.append(parsed)
    return max(times)


# ---------------------------------------------------------------------------
# Decision records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class G4ArmSpec:
    """One arm's decision content for session T (caller-supplied).

    ``scores`` for the L1 arm come from :func:`equal_weight_scores`;
    the champion's from its single frozen artifact. ``orders`` is the
    DECLARED intent set for open(T+1) — plain JSON mappings, never sent
    to any broker (an empty list is a declared no-trade, admissible per
    the step-1 contract)."""

    arm: str
    artifact_digests: Mapping[str, str]
    config_digest: str
    scores: Mapping[str, float]
    orders: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


def decision_digest_of(record: Mapping[str, Any]) -> str:
    """Recompute the decision digest over the FULL decision content.

    Covers everything deterministic about the decision — scores, orders,
    schedule target, the complete input manifest (digests AND event
    times), artifact/config digests, and the frozen identifiers. Only
    the volatile ``run_bundle_timestamp`` (evidence, not content), the
    derived ``job_id``/``decision_digest``, and fixed constants are
    outside it, so a divergent duplicate can NEVER carry an identical
    ``decision_digest`` (step-1 approval, non-blocking observation 2)."""
    manifest = record.get("input_manifest")
    payload = {
        "schema": DECISION_DIGEST_SCHEMA,
        "arm": record.get("arm"),
        "decision_session": record.get("decision_session"),
        "declared_input_watermark": record.get("declared_input_watermark"),
        "input_manifest": {
            str(name): {
                "digest": (entry or {}).get("digest"),
                "max_event_time": (entry or {}).get("max_event_time"),
            }
            for name, entry in (
                manifest.items() if isinstance(manifest, Mapping) else ()
            )
        },
        "artifact_digests": {
            str(k): str(v)
            for k, v in sorted(dict(record.get("artifact_digests") or {}).items())
        },
        "config_digest": record.get("config_digest"),
        "calendar_id": record.get("calendar_id"),
        "price_source_id": record.get("price_source_id"),
        "scores": {
            str(k): float(v)
            for k, v in sorted(dict(record.get("scores") or {}).items())
        },
        "orders": [dict(o) for o in record.get("orders") or ()],
        "orders_scheduled_for": record.get("orders_scheduled_for"),
    }
    return _digest(_canonical_bytes(payload))


def build_arm_record(
    spec: G4ArmSpec,
    *,
    decision_session: str,
    session_window: SessionWindow,
    input_manifest: Mapping[str, Mapping[str, str]],
    calendar_id: str,
    price_source_id: str,
    produced_at: dt.datetime,
) -> dict[str, Any]:
    """Build one arm's immutable v4 §2 decision record.

    The declared input watermark is COMPUTED as the maximum
    ``max_event_time`` across the manifest — declaration by
    construction, so the record can only disagree with its inputs if the
    inputs themselves are tampered with (which the admission-side
    byte-level recomputation then catches). ``produced_at`` is the
    run-bundle timestamp (v4 §2: evidence only) and is the ONLY
    non-deterministic field — inject a fixed value to prove byte-identical
    re-runs."""
    _require_aware(produced_at, "produced_at")
    if not input_manifest:
        raise ValueError("input_manifest must be non-empty (v4 §2 complete manifest)")
    if UNIVERSE_INPUT_NAME not in input_manifest:
        raise ValueError(
            f"input_manifest must include the {UNIVERSE_INPUT_NAME!r} snapshot "
            "(v4 §2: complete input/artifact/universe manifest)"
        )
    # Instant-max, not string-max: mixed UTC offsets are legal in ISO-8601
    # and would not sort chronologically as strings.
    watermark = max(
        dt.datetime.fromisoformat(str(entry["max_event_time"]))
        for entry in input_manifest.values()
    ).isoformat()
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "execution_mode": EXECUTION_MODE_SHADOW,
        "arm": spec.arm,
        "decision_session": decision_session,
        "declared_input_watermark": watermark,
        "input_manifest": {
            str(name): dict(entry) for name, entry in sorted(input_manifest.items())
        },
        "artifact_digests": {
            str(k): str(v) for k, v in sorted(spec.artifact_digests.items())
        },
        "config_digest": spec.config_digest,
        "calendar_id": calendar_id,
        "price_source_id": price_source_id,
        "scores": {str(k): float(v) for k, v in sorted(spec.scores.items())},
        "orders": [dict(o) for o in spec.orders],
        "orders_scheduled_for": session_window.next_open_session,
        "run_bundle_timestamp": produced_at.isoformat(),
    }
    record["job_id"] = job_identity(
        arm=spec.arm,
        decision_session=decision_session,
        artifact_digests=record["artifact_digests"],
        config_digest=spec.config_digest,
    )
    record["decision_digest"] = decision_digest_of(record)
    return record


def build_failure_record(
    *,
    arm: str,
    decision_session: str,
    kind: str,
    detail: str,
    outage_evidence: Sequence[Mapping[str, Any]] = (),
    recorded_at: dt.datetime,
) -> dict[str, Any]:
    """A declared-failure record (v4 §2 failure classes).

    ``outage_evidence`` is the documented-outage qualifier's carrier
    (step-1 approval, reviewer requirement (a); v4 §2 ``B_shared`` names
    "DOCUMENTED shared venue/calendar outages"): STRUCTURED references
    proving the outage was external and shared. Each reference MUST be a
    mapping with all three required fields (2026-07-18 review P0-3 — a
    free-form string is self-declarable and buys nothing):
    ``kind`` (one of :data:`OUTAGE_EVIDENCE_KINDS`), ``ref`` (non-empty
    incident/task/URL string) and ``observed_at`` (ISO-8601 UTC).
    Malformed references are a caller error HERE (fail-fast — omit
    evidence entirely rather than submit garbage); whatever bytes land on
    disk are independently re-validated at admission, where a shape
    violation degrades the ``B_shared`` charge to ``B_idio`` with reason
    ``shared_outage_evidence_malformed``. WITHOUT at least one
    well-formed reference per failed arm a symmetric shared-kind failure
    DEGRADES to idiosyncratic at admission; the declaration alone is
    unfalsifiable from records."""
    if kind not in KNOWN_FAILURE_KINDS:
        raise ValueError(
            f"failure kind {kind!r} is not one of {sorted(KNOWN_FAILURE_KINDS)}"
        )
    _require_aware(recorded_at, "recorded_at")
    refs: list[dict[str, str]] = []
    for index, reference in enumerate(tuple(outage_evidence)):
        error = outage_reference_error(reference)
        if error is not None:
            raise ValueError(f"outage_evidence[{index}]: {error}")
        refs.append(normalized_outage_reference(reference))
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "execution_mode": EXECUTION_MODE_SHADOW,
        "arm": arm,
        "decision_session": decision_session,
        "failure": {
            "kind": kind,
            "detail": str(detail),
            "outage_evidence": refs,
        },
        "recorded_at": recorded_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Immutable evidence store (append-only, digest-named, write-once)
# ---------------------------------------------------------------------------

#: Fields excluded when deciding whether a same-name rewrite is a benign
#: retry: per record kind, the single volatile evidence timestamp.
_VOLATILE_BY_KIND = {
    "record": ("run_bundle_timestamp",),
    "failure": ("recorded_at",),
    "admission": ("evaluated_at",),
    "input": (),
}


class G4EvidenceStore:
    """Append-only, digest-named G4 evidence persistence.

    Immutability contract (task §2): files are created exclusively
    (hard-link publish, so a concurrent duplicate writer cannot clobber)
    and chmod'd read-only; a re-run with identical inputs produces
    byte-identical content and is a no-op admissible retry; a rewrite
    differing ONLY in the volatile evidence timestamp keeps the FIRST
    file untouched and logs the attempt; ANY other rewrite of an
    existing path raises :class:`G4EvidenceIntegrityError` with the
    original bytes intact. Divergent decision content never collides —
    its digest-name differs — so it lands side-by-side and is flagged at
    admission, never overwritten and never resolved by latest-commit.
    """

    def __init__(self, root: "Path | str") -> None:
        self.root = Path(root)

    # -- paths ------------------------------------------------------------

    @property
    def inputs_dir(self) -> Path:
        return self.root / "inputs"

    def session_dir(self, decision_session: str) -> Path:
        dt.date.fromisoformat(decision_session)  # raises on bad input
        return self.root / "sessions" / decision_session

    def records_dir(self, decision_session: str) -> Path:
        return self.session_dir(decision_session) / "records"

    def admission_dir(self, decision_session: str) -> Path:
        return self.session_dir(decision_session) / "admission"

    def attempts_path(self, decision_session: str) -> Path:
        return self.session_dir(decision_session) / "attempts.jsonl"

    # -- write-once primitive ---------------------------------------------

    def _write_once(self, path: Path, data: bytes, *, volatile: Sequence[str]) -> str:
        """Publish ``data`` at ``path`` append-only. Returns the outcome:
        ``"created"`` | ``"identical"`` (byte-identical retry no-op) |
        ``"retry"`` (differs only in the volatile timestamp; FIRST write
        wins, nothing touched). Anything else raises."""
        if path.exists():
            existing = path.read_bytes()
            if existing == data:
                return "identical"
            if volatile and self._equal_minus_volatile(existing, data, volatile):
                return "retry"
            raise G4EvidenceIntegrityError(
                f"refusing to overwrite immutable evidence file {path} — "
                "existing content differs beyond the volatile timestamp; "
                "divergent evidence must land side-by-side under its own "
                "digest-name, never in place"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
        tmp.write_bytes(data)
        try:
            os.link(tmp, path)  # atomic exclusive publish
        except FileExistsError:
            tmp.unlink(missing_ok=True)
            return self._write_once(path, data, volatile=volatile)
        finally:
            tmp.unlink(missing_ok=True)
        os.chmod(path, 0o444)
        return "created"

    @staticmethod
    def _equal_minus_volatile(
        existing: bytes, incoming: bytes, volatile: Sequence[str]
    ) -> bool:
        try:
            a, b = json.loads(existing), json.loads(incoming)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        for key in volatile:
            a.pop(key, None)
            b.pop(key, None)
        return a == b

    def _log_attempt(self, decision_session: str, entry: Mapping[str, Any]) -> None:
        path = self.attempts_path(decision_session)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")

    # -- inputs -----------------------------------------------------------

    def store_input(self, data: bytes) -> str:
        """Persist one input snapshot content-addressed; returns its digest."""
        digest = _digest(data)
        self._write_once(
            self.inputs_dir / f"{_digest_hex(digest)}.json", data, volatile=()
        )
        return digest

    def read_input(self, digest: Any) -> "bytes | None":
        """Resolve snapshot bytes BY DIGEST, verifying the hash. ``None``
        (fail-closed) on a malformed digest, a missing file, or bytes
        that no longer hash to their name (tampering)."""
        if not isinstance(digest, str) or not digest.startswith(_DIGEST_PREFIX):
            return None
        path = self.inputs_dir / f"{_digest_hex(digest)}.json"
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return data if _digest(data) == digest else None

    # -- records ----------------------------------------------------------

    def write_record(self, record: Mapping[str, Any]) -> "tuple[Path, str]":
        """Persist one qualifying decision record immutably.

        Verifies the record's declared digests BEFORE writing (fail-closed:
        a record whose ``decision_digest``/``job_id`` does not match its
        own content, or that claims any execution mode but shadow, can
        never enter the store), names the file by both digests, and logs
        the attempt. Returns ``(path, outcome)``."""
        if record.get("execution_mode") != EXECUTION_MODE_SHADOW:
            raise G4EvidenceIntegrityError(
                "G4 evidence store only accepts SHADOW records; got "
                f"execution_mode={record.get('execution_mode')!r}"
            )
        declared = record.get("decision_digest")
        recomputed = decision_digest_of(record)
        if declared != recomputed:
            raise G4EvidenceIntegrityError(
                f"record decision_digest {declared!r} does not match its own "
                f"content ({recomputed}); refusing to persist a record that "
                "fails its declared digest"
            )
        declared_job = record.get("job_id")
        recomputed_job = job_identity(
            arm=str(record.get("arm")),
            decision_session=str(record.get("decision_session")),
            artifact_digests=dict(record.get("artifact_digests") or {}),
            config_digest=str(record.get("config_digest")),
        )
        if declared_job != recomputed_job:
            raise G4EvidenceIntegrityError(
                f"record job_id {declared_job!r} does not match the deterministic "
                f"identity {recomputed_job}; refusing to persist"
            )
        session = str(record.get("decision_session"))
        name = (
            f"{record.get('arm')}-{_digest_hex(str(declared_job))[:12]}"
            f"-{_digest_hex(str(declared))[:12]}.json"
        )
        path = self.records_dir(session) / name
        outcome = self._write_once(
            path, _canonical_bytes(record), volatile=_VOLATILE_BY_KIND["record"]
        )
        self._log_attempt(
            session,
            {
                "kind": "record",
                "arm": record.get("arm"),
                "job_id": declared_job,
                "decision_digest": declared,
                "run_bundle_timestamp": record.get("run_bundle_timestamp"),
                "outcome": outcome,
                "path": str(path),
            },
        )
        return path, outcome

    def write_failure_record(self, record: Mapping[str, Any]) -> "tuple[Path, str]":
        """Persist one declared-failure record immutably (content-digest named)."""
        failure = record.get("failure")
        if not isinstance(failure, Mapping) or failure.get("kind") not in KNOWN_FAILURE_KINDS:
            raise G4EvidenceIntegrityError(
                "failure record must carry failure.kind in "
                f"{sorted(KNOWN_FAILURE_KINDS)}; got {record!r}"
            )
        data = _canonical_bytes(record)
        session = str(record.get("decision_session"))
        name = f"{record.get('arm')}-failure-{_digest_hex(_digest(data))[:12]}.json"
        path = self.records_dir(session) / name
        outcome = self._write_once(path, data, volatile=_VOLATILE_BY_KIND["failure"])
        self._log_attempt(
            session,
            {
                "kind": "failure",
                "arm": record.get("arm"),
                "failure_kind": failure.get("kind"),
                "recorded_at": record.get("recorded_at"),
                "outcome": outcome,
                "path": str(path),
            },
        )
        return path, outcome

    def write_admission_entry(
        self, entry: Mapping[str, Any]
    ) -> "tuple[Path, str]":
        """Persist one admission-ledger entry append-only.

        Digest-named over the entry's NON-volatile content, so an
        identical re-admission collapses onto the existing file (bytes
        differing only in ``evaluated_at`` keep the first write) while a
        CHANGED verdict lands side-by-side — a verdict is never
        rewritten."""
        session = str(entry.get("expected_session"))
        naming = {k: v for k, v in entry.items() if k != "evaluated_at"}
        hex12 = hashlib.sha256(_canonical_bytes(naming)).hexdigest()[:12]
        path = self.admission_dir(session) / f"admission-{hex12}.json"
        outcome = self._write_once(
            path, _canonical_bytes(entry), volatile=_VOLATILE_BY_KIND["admission"]
        )
        self._log_attempt(
            session,
            {
                "kind": "admission",
                "ok": entry.get("ok"),
                "budget": entry.get("budget"),
                "evaluated_at": entry.get("evaluated_at"),
                "outcome": outcome,
                "path": str(path),
            },
        )
        return path, outcome

    def load_session_records(
        self, decision_session: str
    ) -> "list[tuple[Path, dict[str, Any]]]":
        """All persisted records of one session, sorted by file name.

        Unparseable files are returned as ``(path, {"__unreadable__": ...})``
        markers rather than skipped — a corrupt evidence file must surface
        at admission, not vanish."""
        records_dir = self.records_dir(decision_session)
        out: "list[tuple[Path, dict[str, Any]]]" = []
        if not records_dir.is_dir():
            return out
        for path in sorted(records_dir.iterdir()):
            if path.name.startswith(".") or path.suffix != ".json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                out.append((path, {"__unreadable__": str(exc)}))
                continue
            out.append((path, payload if isinstance(payload, dict) else {"__unreadable__": "not a JSON object"}))
        return out


# ---------------------------------------------------------------------------
# The canonical shadow job
# ---------------------------------------------------------------------------

def run_g4_shadow_session(
    store: G4EvidenceStore,
    *,
    decision_session: str,
    session_window: SessionWindow,
    inputs: Mapping[str, Mapping[str, Any]],
    arms: Sequence[G4ArmSpec],
    calendar_id: str,
    price_source_id: str,
    produced_at: dt.datetime,
) -> dict[str, Any]:
    """Produce + persist both arms' immutable decision records for T.

    SHADOW ONLY — no broker interaction of any kind; the declared order
    sets are intent records for evidence. ``inputs`` maps snapshot name
    -> ``{"event_times": [aware datetimes], "payload": jsonable}`` and
    MUST include ``"universe"`` (v4 §2 complete input/artifact/universe
    manifest). Both arms share the identical manifested information set
    (v4's paired design). ``arms`` must be exactly the frozen registered
    pair (v4 §3) — this is the canonical job, not a generic harness.
    ``produced_at`` is injectable so a re-run with identical inputs is
    byte-identical (proved by test).

    Every record is validated against the step-1 contract
    (:func:`validate_arm_record`, with the byte-level watermark hook
    against this store) BEFORE returning; a canonical job that produced
    an invalid record is a bug and raises rather than silently leaving
    bad evidence unflagged (the record is still on disk for forensics).
    """
    if {spec.arm for spec in arms} != set(EXPECTED_ARMS) or len(arms) != len(
        EXPECTED_ARMS
    ):
        raise ValueError(
            f"the canonical G4 job runs exactly the frozen registered pair "
            f"{EXPECTED_ARMS!r}; got {[spec.arm for spec in arms]!r}"
        )
    if UNIVERSE_INPUT_NAME not in inputs:
        raise ValueError(
            f"inputs must include the {UNIVERSE_INPUT_NAME!r} snapshot "
            "(v4 §2: complete input/artifact/universe manifest)"
        )

    input_manifest: dict[str, dict[str, str]] = {}
    for name in sorted(inputs):
        entry = inputs[name]
        data = input_snapshot_bytes(
            name,
            event_times=tuple(entry["event_times"]),
            payload=entry.get("payload"),
        )
        digest = store.store_input(data)
        recomputed = max_event_time_from_bytes(data)
        assert recomputed is not None  # by construction of input_snapshot_bytes
        input_manifest[name] = {
            "digest": digest,
            "max_event_time": recomputed.isoformat(),
        }

    from renquant_orchestrator.g4_admission import (  # noqa: PLC0415 — avoid import cycle
        recompute_watermark_from_store,
    )

    hook = recompute_watermark_from_store(store)
    results: dict[str, Any] = {
        "decision_session": decision_session,
        "records": {},
        "paths": {},
        "outcomes": {},
    }
    for spec in sorted(arms, key=lambda s: s.arm):
        record = build_arm_record(
            spec,
            decision_session=decision_session,
            session_window=session_window,
            input_manifest=input_manifest,
            calendar_id=calendar_id,
            price_source_id=price_source_id,
            produced_at=produced_at,
        )
        path, outcome = store.write_record(record)
        verdict = validate_arm_record(
            record,
            session_window=session_window,
            recompute_max_event_time=hook,
            expected_calendar_id=calendar_id,
            expected_price_source_id=price_source_id,
        )
        if not verdict.ok:
            raise G4EvidenceIntegrityError(
                f"canonical job produced an INVALID record for arm "
                f"{spec.arm!r} (bug — record kept at {path} for forensics): "
                f"{verdict.reason_codes!r}: {verdict.detail}"
            )
        results["records"][spec.arm] = record
        results["paths"][spec.arm] = str(path)
        results["outcomes"][spec.arm] = outcome
    return results


__all__ = [
    "DECISION_DIGEST_SCHEMA",
    "EXECUTION_MODE_SHADOW",
    "G4ArmSpec",
    "G4EvidenceIntegrityError",
    "G4EvidenceStore",
    "G4_EVIDENCE_SCHEMA_VERSION",
    "OUTAGE_EVIDENCE_FIELDS",
    "OUTAGE_EVIDENCE_KINDS",
    "UNIVERSE_INPUT_NAME",
    "build_arm_record",
    "build_failure_record",
    "decision_digest_of",
    "equal_weight_scores",
    "input_snapshot_bytes",
    "max_event_time_from_bytes",
    "normalized_outage_reference",
    "outage_reference_error",
    "resolve_session_window",
    "run_g4_shadow_session",
]
