"""G4 session admission ledger — step 2 read side (model#61 v4 §2/§5).

Executes admission for one decision session over the immutable evidence
written by :mod:`renquant_orchestrator.g4_shadow_job`, on top of the
step-1 public contract ``renquant_pipeline.decision_schedule``
(renquant-pipeline#209). v4 §5 assigns "admission ledger execution" to
the orchestrator; the pipeline contract stays classification OUTPUT
only, and THIS module adds the three runner-side obligations the step-1
approval pinned:

(a) **Documented-outage qualifier** (approval, adjudication 2 residual;
    tightened per the 2026-07-18 review P0-3): v4 §2 charges
    ``B_shared`` only for "DOCUMENTED shared venue/calendar outages".
    A declaration alone is unfalsifiable from records, and a free-form
    non-empty string is itself self-declarable — so every
    ``failure.outage_evidence`` reference must be the STRUCTURED shape
    ``{kind, ref, observed_at}`` (``kind`` in
    :data:`~renquant_orchestrator.g4_shadow_job.OUTAGE_EVIDENCE_KINDS`,
    ``ref`` a non-empty incident/task/URL string, ``observed_at``
    ISO-8601 UTC; all three required). A session the contract classifies
    ``shared`` is charged to ``B_shared`` ONLY when every failed arm's
    declared-failure record carries at least one WELL-FORMED reference
    and NO reference anywhere in the session violates the shape.
    Otherwise the charge DEGRADES to ``B_idio``: reason
    ``shared_outage_evidence_malformed`` when any reference fails shape
    validation, ``shared_outage_undocumented`` when an arm simply has
    none. The contract's own classification is preserved verbatim in
    ``pipeline_failure_class`` — nothing is hidden, the budget
    attribution just refuses an unevidenced or malformed shared charge.
    (Shape validation only — resolving/hashing the referenced incident
    is the pinned pre-pilot follow-up; see the progress doc.)
(b) The **early-close adversarial test** for SessionWindow resolution
    lives with :func:`g4_shadow_job.resolve_session_window`'s tests.
(c) **Expected-session parameter** (approval, non-blocking observation
    3: the contract "takes no expected-session parameter; binding
    records → T → window is the caller's job"): :func:`admit_g4_session`
    REQUIRES ``expected_session`` and evaluates THAT session's evidence
    directory — a session with no records at all is therefore
    detectable and inadmissible (``missing_session``, charged
    ``B_idio``: both arms silently absent is a job failure, and per the
    contract's pinned semantics a symmetric ADMISSION failure is never a
    documented shared outage). Any record inside the directory claiming
    a different ``decision_session`` is a binding integrity failure.

Additional evidence-integrity checks (beyond the step-1 contract, both
recomputed from bytes — approval, non-blocking observation 2):

* every qualifying record's ``decision_digest`` is recomputed over its
  FULL decision content (``decision_digest_mismatch`` on divergence, so
  a tampered-in-place record can never pass);
* the watermark hook injected into the contract is the BYTE-LEVEL one —
  :func:`recompute_watermark_from_store` resolves every manifested input
  by digest from the store, verifies its hash, and recomputes the max
  event-time from bytes (v4 §2 r2: the declared watermark is not
  self-certifying; the step-1 default manifest-echo hook is explicitly
  NOT production admission).

Budget ATTRIBUTION here is per-session labelling only (``B_idio`` /
``B_shared`` / ``None``); budget SIZES, cumulative counting, and the
terminal ``NO-GO (integrity)`` consequence belong to the future pilot
runner (v4 §2 r2) — this job is not scheduled and Phase 0 stays BLOCKED.

**Registration binding (2026-07-18 review P0-1/P0-2/P1-4).** v4 §4's
two-stage start freezes the registration-bound identifiers — calendar
id, price-source id, the universe/required-input set, cost model, and
both failure budgets — ONLY at the pilot-registration commit, which is
explicitly out of step-2 scope (§5 step 2 is machinery; §5 step 4 is the
pilot). The step-1 contract mirrors this: ``validate_session_records``
checks the frozen ``calendar_id``/``price_source_id`` against the
``expected_*`` values ONLY when those are supplied, and pipeline#209's
approving review accepted that optionality together with the
caller-resolves-``SessionWindow`` seam. So a step-2 admission call with
no frozen identifiers CANNOT be a series-admission verdict — the values
to bind against do not exist yet. This ledger therefore returns an
EXPLICIT ``registration_bound`` flag (True iff BOTH
``expected_calendar_id`` and ``expected_price_source_id`` were supplied)
and a derived ``series_eligible`` (``ok and registration_bound``).
``admissible`` means ONLY "the records pass step-2 machinery integrity";
``series_eligible`` is the single boolean a future
pilot-registration/enrollment caller MUST consult, and it is FALSE for
every unregistered (current) session — so a later caller cannot mistake
machinery integrity for series-eligibility without a code change (the
review's "admissible verdict with unbound IDs" fail-open is closed by an
explicit unbound return, codex option (a)). When the frozen identifiers
ARE supplied (the pilot runner's job) the contract binds them in-record
(``frozen_identifier_mismatch``) and ``series_eligible`` follows
``admissible``. Final enrollment stays subject to the §4 activation gates
and the PP-1..PP-4 pre-registration hardening items (content-addressed
outage evidence, keyless-store boundary, digest-bound calendar
resolution, required-input-set spec) tracked in the progress doc.

The ledger entry is persisted append-only under the session's
``admission/`` directory (digest-named; re-admission with an identical
verdict is a no-op; a changed verdict lands side-by-side — verdicts are
never rewritten). :func:`g4_session_bundle_block` exposes the summary
for the daily run bundle the same additive/absent-tolerant way #547/#549
attached their blocks.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Mapping, Sequence

from renquant_pipeline.decision_schedule import (
    DECISION_SCHEDULE_CONTRACT_VERSION,
    EXPECTED_ARMS,
    FAILURE_CLASS_IDIOSYNCRATIC,
    FAILURE_CLASS_SHARED,
    SessionWindow,
    validate_session_records,
)

from renquant_orchestrator.g4_shadow_job import (
    G4EvidenceStore,
    G4_EVIDENCE_SCHEMA_VERSION,
    decision_digest_of,
    max_event_time_from_bytes,
    normalized_outage_reference,
    outage_reference_error,
)

#: Budget labels (v4 §2 r2 — two separately pre-registered budgets).
BUDGET_IDIOSYNCRATIC = "B_idio"
BUDGET_SHARED = "B_shared"

#: Ledger-level reason codes (stable strings, additive to the pipeline
#: contract's codes — namespaced by intent, reported side by side).
REASON_MISSING_SESSION = "missing_session"
REASON_SESSION_BINDING_MISMATCH = "session_binding_mismatch"
REASON_DECISION_DIGEST_MISMATCH = "decision_digest_mismatch"
REASON_EVIDENCE_UNREADABLE = "evidence_unreadable"
REASON_SHARED_OUTAGE_UNDOCUMENTED = "shared_outage_undocumented"
REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED = "shared_outage_evidence_malformed"


def recompute_watermark_from_store(
    store: G4EvidenceStore,
) -> "Callable[[Mapping[str, Mapping[str, Any]]], dt.datetime | None]":
    """The production ``recompute_max_event_time`` hook (v4 §2 r2).

    Resolves every manifested input BY DIGEST from the store (hash
    verified), recomputes each snapshot's max event-time FROM BYTES, and
    returns the overall maximum. ``None`` — which the step-1 validator
    treats as a watermark recompute mismatch, fail-closed — on any
    missing input, hash mismatch, or unparseable snapshot."""

    def hook(manifest: Mapping[str, Mapping[str, Any]]) -> "dt.datetime | None":
        if not isinstance(manifest, Mapping) or not manifest:
            return None
        times: list[dt.datetime] = []
        for entry in manifest.values():
            digest = entry.get("digest") if isinstance(entry, Mapping) else None
            data = store.read_input(digest)
            if data is None:
                return None
            ts = max_event_time_from_bytes(data)
            if ts is None:
                return None
            times.append(ts)
        return max(times)

    return hook


def _failed_arm_outage_evidence(
    records: Sequence[Mapping[str, Any]], expected_arms: Sequence[str]
) -> "tuple[bool, list[str], dict[str, list[dict[str, str]]]]":
    """(documented, malformed-details, per-arm references) for the
    declared-failure records.

    Every ``failure.outage_evidence`` reference is shape-validated
    against the structured contract (2026-07-18 review P0-3): a mapping
    with ``kind`` in ``OUTAGE_EVIDENCE_KINDS``, a non-empty ``ref``
    string, and an ISO-8601 UTC ``observed_at`` — all three required.
    Any shape violation ANYWHERE in the session is recorded in
    ``malformed`` (fail-closed: one bad reference poisons the whole
    ``B_shared`` charge). ``documented`` requires zero malformed
    references AND at least one well-formed reference on EVERY expected
    arm. (Only consulted when the contract classified the session
    ``shared`` — which already implies every arm's governing records are
    declared failures of the same shared kind.)"""
    refs: dict[str, list[dict[str, str]]] = {arm: [] for arm in expected_arms}
    malformed: list[str] = []
    for record in records:
        failure = record.get("failure")
        arm = str(record.get("arm"))
        if not isinstance(failure, Mapping) or arm not in refs:
            continue
        evidence = failure.get("outage_evidence")
        if evidence is None:
            continue
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
            malformed.append(
                f"arm {arm!r}: outage_evidence must be a list of structured "
                f"references, got {type(evidence).__name__}"
            )
            continue
        for index, reference in enumerate(evidence):
            error = outage_reference_error(reference)
            if error is not None:
                malformed.append(f"arm {arm!r} reference [{index}]: {error}")
            else:
                refs[arm].append(normalized_outage_reference(reference))
    documented = not malformed and all(refs[arm] for arm in expected_arms)
    return documented, malformed, refs


def admit_g4_session(
    store: G4EvidenceStore,
    *,
    expected_session: str,
    session_window: "SessionWindow | None" = None,
    calendar: Any | None = None,
    expected_arms: Sequence[str] = EXPECTED_ARMS,
    expected_calendar_id: "str | None" = None,
    expected_price_source_id: "str | None" = None,
    evaluated_at: "dt.datetime | None" = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Admission verdict + budget attribution for ONE expected session.

    ``expected_session`` is REQUIRED (reviewer requirement (c)): the
    ledger evaluates that session's evidence whether or not the job ran,
    so a missing session is a detected failure, never a silent gap.
    ``session_window`` may be given directly (tests, replays) or is
    resolved via :func:`g4_shadow_job.resolve_session_window` against
    ``calendar`` (``None`` = real NYSE).

    Returns the ledger entry (JSON-safe dict); with ``persist=True``
    (default) it is also written append-only to the session's
    ``admission/`` directory. Never raises on an admission outcome —
    only on caller errors (bad expected_session, unresolvable window).
    """
    dt.date.fromisoformat(expected_session)  # caller error if malformed
    if session_window is None:
        from renquant_orchestrator.g4_shadow_job import (  # noqa: PLC0415 — cycle guard
            resolve_session_window,
        )

        session_window = resolve_session_window(expected_session, calendar=calendar)
    if evaluated_at is not None and evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")

    # Registration binding (review P0-1/P0-2/P1-4): the frozen registration
    # identifiers only exist at the pilot-registration commit (v4 §4), which
    # is out of step-2 scope. Absent BOTH, no admission verdict can be a
    # series-admission verdict; ``series_eligible`` is derived from this and
    # is False for every unregistered (current) session.
    registration_bound = (
        expected_calendar_id is not None and expected_price_source_id is not None
    )

    ledger_codes: list[str] = []
    details: list[str] = []
    loaded = store.load_session_records(expected_session)
    records: list[dict[str, Any]] = []
    for path, record in loaded:
        if "__unreadable__" in record:
            if REASON_EVIDENCE_UNREADABLE not in ledger_codes:
                ledger_codes.append(REASON_EVIDENCE_UNREADABLE)
            details.append(f"unreadable evidence file {path.name}: {record['__unreadable__']}")
            continue
        records.append(record)

    if not loaded:
        # (c): the expected session produced NO evidence at all. Both arms
        # silently absent = job failure; per the contract's pinned
        # semantics a symmetric ADMISSION failure is not a documented
        # shared outage -> idiosyncratic, charged B_idio.
        entry = _entry(
            expected_session=expected_session,
            ok=False,
            admissible=False,
            registration_bound=registration_bound,
            series_eligible=False,
            reason_codes=[REASON_MISSING_SESSION],
            failure_class=FAILURE_CLASS_IDIOSYNCRATIC,
            pipeline_failure_class=None,
            budget=BUDGET_IDIOSYNCRATIC,
            outage_documented=None,
            outage_evidence={},
            degraded=False,
            arm_verdicts=[],
            evidence_flags=[],
            detail=(
                f"expected session {expected_session} has no evidence records "
                "under the G4 evidence store (missing session — the canonical "
                "job never persisted anything)"
            ),
            evaluated_at=evaluated_at,
        )
        return _persist(store, entry) if persist else entry

    # Binding (c): every record inside sessions/<T>/ must claim T.
    for record in records:
        claimed = str(record.get("decision_session"))
        if claimed != expected_session:
            if REASON_SESSION_BINDING_MISMATCH not in ledger_codes:
                ledger_codes.append(REASON_SESSION_BINDING_MISMATCH)
            details.append(
                f"record for arm {record.get('arm')!r} claims decision_session "
                f"{claimed!r} inside the {expected_session} evidence directory"
            )

    # Evidence integrity: recompute every qualifying record's decision
    # digest over its full content (observation 2 — a divergent duplicate
    # or tampered-in-place record cannot ride a stale digest).
    for record in records:
        if isinstance(record.get("failure"), Mapping):
            continue
        declared = record.get("decision_digest")
        recomputed = decision_digest_of(record)
        if declared != recomputed:
            if REASON_DECISION_DIGEST_MISMATCH not in ledger_codes:
                ledger_codes.append(REASON_DECISION_DIGEST_MISMATCH)
            details.append(
                f"arm {record.get('arm')!r} record decision_digest {declared!r} "
                f"!= recomputed full-content digest {recomputed}"
            )

    verdict = validate_session_records(
        records,
        session_window=session_window,
        expected_arms=tuple(expected_arms),
        recompute_max_event_time=recompute_watermark_from_store(store),
        expected_calendar_id=expected_calendar_id,
        expected_price_source_id=expected_price_source_id,
    )

    ok = verdict.ok and not ledger_codes
    pipeline_class = verdict.failure_class
    failure_class = pipeline_class
    budget: "str | None" = None
    outage_documented: "bool | None" = None
    outage_evidence: dict[str, list[dict[str, str]]] = {}
    degraded = False

    if not ok:
        if pipeline_class == FAILURE_CLASS_SHARED:
            # (a): a B_shared charge REQUIRES documented outage evidence,
            # structured and shape-valid (2026-07-18 review P0-3).
            outage_documented, malformed, outage_evidence = (
                _failed_arm_outage_evidence(records, expected_arms)
            )
            if outage_documented:
                budget = BUDGET_SHARED
            elif malformed:
                degraded = True
                failure_class = FAILURE_CLASS_IDIOSYNCRATIC
                budget = BUDGET_IDIOSYNCRATIC
                ledger_codes.append(REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED)
                details.append(
                    "symmetric shared-kind failure carries MALFORMED "
                    "outage-evidence — every reference must be the "
                    "structured {kind, ref, observed_at} shape (kind in "
                    "the closed vocabulary, non-empty ref, ISO-8601 UTC "
                    "observed_at), so the charge degrades to B_idio "
                    "(pipeline classification preserved in "
                    "pipeline_failure_class): " + "; ".join(malformed)
                )
            else:
                degraded = True
                failure_class = FAILURE_CLASS_IDIOSYNCRATIC
                budget = BUDGET_IDIOSYNCRATIC
                ledger_codes.append(REASON_SHARED_OUTAGE_UNDOCUMENTED)
                details.append(
                    "symmetric shared-kind failure carries NO outage-evidence "
                    "reference on at least one arm — v4 §2 charges B_shared "
                    "only for DOCUMENTED shared outages, so the charge "
                    "degrades to B_idio (pipeline classification preserved "
                    "in pipeline_failure_class)"
                )
        else:
            failure_class = FAILURE_CLASS_IDIOSYNCRATIC
            budget = BUDGET_IDIOSYNCRATIC

    if not registration_bound:
        details.append(
            "registration_bound=False: no frozen registration identifiers "
            "were supplied (expected_calendar_id / expected_price_source_id), "
            "so this is a step-2 machinery-integrity verdict ONLY, not a "
            "series-admission verdict — series_eligible is False until the "
            "pilot-registration commit supplies the frozen identity (v4 §4)"
        )

    entry = _entry(
        expected_session=expected_session,
        ok=ok,
        admissible=ok,
        registration_bound=registration_bound,
        series_eligible=bool(ok) and registration_bound,
        reason_codes=list(ledger_codes) + list(verdict.reason_codes),
        failure_class=None if ok else failure_class,
        pipeline_failure_class=pipeline_class,
        budget=budget,
        outage_documented=outage_documented,
        outage_evidence=outage_evidence,
        degraded=degraded,
        arm_verdicts=[
            {
                "arm": arm,
                "ok": arm_verdict.ok,
                "reason_codes": list(arm_verdict.reason_codes),
                "failure_class": arm_verdict.failure_class,
                "evidence_flags": list(arm_verdict.evidence_flags),
            }
            for arm, arm_verdict in verdict.arm_verdicts
        ],
        evidence_flags=list(verdict.evidence_flags),
        detail="; ".join(details + ([verdict.detail] if verdict.detail else [])),
        evaluated_at=evaluated_at,
    )
    return _persist(store, entry) if persist else entry


def _entry(**kwargs: Any) -> dict[str, Any]:
    entry = {
        "kind": "g4_session_admission",
        "schema_version": G4_EVIDENCE_SCHEMA_VERSION,
        "contract_version": DECISION_SCHEDULE_CONTRACT_VERSION,
        **kwargs,
    }
    evaluated_at = entry.pop("evaluated_at", None)
    entry["evaluated_at"] = (
        evaluated_at.isoformat() if isinstance(evaluated_at, dt.datetime) else None
    )
    return entry


def _persist(store: G4EvidenceStore, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Append the ledger entry via the store's write-once surface."""
    path, outcome = store.write_admission_entry(entry)
    result = dict(entry)
    result["ledger_path"] = str(path)
    result["ledger_outcome"] = outcome
    return result


# ---------------------------------------------------------------------------
# Run-bundle surface (additive/absent-tolerant, the #547/#549 pattern)
# ---------------------------------------------------------------------------

#: Keys forwarded into the daily run bundle's ``g4_session`` block.
G4_BUNDLE_SUMMARY_KEYS = (
    "kind",
    "schema_version",
    "contract_version",
    "expected_session",
    "ok",
    "admissible",
    "registration_bound",
    "series_eligible",
    "reason_codes",
    "failure_class",
    "pipeline_failure_class",
    "budget",
    "outage_documented",
    "degraded",
    "evidence_flags",
    "evaluated_at",
    "ledger_path",
)


def g4_session_bundle_block(entry: Any = None) -> "dict[str, Any] | str":
    """The daily run bundle's ``g4_session`` block.

    ABSENT-TOLERANT the same way #549's ``smalln_ledger`` block is: while
    the G4 shadow job is not scheduled (Phase 0 BLOCKED — the current
    reality for every daily run), the block is the literal string
    ``"absent"``, never a KeyError and never a validation failure. A
    malformed entry (partial writes, mocks) also degrades to the explicit
    absent state rather than corrupting the bundle. With a real admission
    entry, the summary keys are forwarded verbatim (JSON-safe)."""
    if not isinstance(entry, Mapping) or entry.get("kind") != "g4_session_admission":
        return "absent"
    return {
        key: entry.get(key) for key in G4_BUNDLE_SUMMARY_KEYS if key in entry
    }


__all__ = [
    "BUDGET_IDIOSYNCRATIC",
    "BUDGET_SHARED",
    "G4_BUNDLE_SUMMARY_KEYS",
    "REASON_DECISION_DIGEST_MISMATCH",
    "REASON_EVIDENCE_UNREADABLE",
    "REASON_MISSING_SESSION",
    "REASON_SESSION_BINDING_MISMATCH",
    "REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED",
    "REASON_SHARED_OUTAGE_UNDOCUMENTED",
    "admit_g4_session",
    "g4_session_bundle_block",
    "recompute_watermark_from_store",
]
