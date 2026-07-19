"""G4 session admission ledger (step 2 read side, model#61 v4 §2/§5).

Proves the three runner-side obligations the step-1 (pipeline#209)
approval pinned onto step 2:

(a) a ``B_shared`` charge requires DOCUMENTED outage evidence — every
    reference the STRUCTURED ``{kind, ref, observed_at}`` shape
    (2026-07-18 review P0-3); an undocumented symmetric shared failure
    DEGRADES to ``B_idio`` (``shared_outage_undocumented``), and ANY
    shape-violating reference degrades it too
    (``shared_outage_evidence_malformed``);
(b) early-close adversarial resolution (write-side tests in
    ``test_g4_shadow_job.py``; here: the early-close-violating record is
    inadmissible at admission too);
(c) the expected-session parameter makes a MISSING session detectable.

Plus the v4 §6(b) adversarial battery on the evidence surface: late
watermark (byte-level recompute mismatch), divergent retry, missing arm,
tampered-in-place record, unreadable evidence — every failure classified
with budget attribution, persisted append-only, and surfaced to the
daily run bundle additively/absent-tolerantly (the #547/#549 pattern).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_pipeline.decision_schedule import (
    ARM_CHAMPION,
    ARM_L1,
    FAILURE_CLASS_IDIOSYNCRATIC,
    FAILURE_CLASS_SHARED,
    FAILURE_KIND_FILL,
    FAILURE_KIND_JOB_CRASH,
    FAILURE_KIND_PRICE_SOURCE,
    FAILURE_KIND_VALUATION,
    FAILURE_KIND_VENUE_OUTAGE,
    REASON_ASYMMETRIC_ARM_FAILURE,
    REASON_DIVERGENT_RETRY,
    REASON_FROZEN_IDENTIFIER_MISMATCH,
    REASON_MISSING_ARM,
    REASON_SESSION_MISMATCH,
    REASON_SHARED_OUTAGE_FAILURE,
    REASON_SHARED_PRICE_SOURCE_FAILURE,
    REASON_WATERMARK_AFTER_CLOSE,
    REASON_WATERMARK_RECOMPUTE_MISMATCH,
)

from renquant_orchestrator.g4_admission import (
    BUDGET_IDIOSYNCRATIC,
    BUDGET_SHARED,
    REASON_DECISION_DIGEST_MISMATCH,
    REASON_EVIDENCE_UNREADABLE,
    REASON_MISSING_SESSION,
    REASON_SESSION_BINDING_MISMATCH,
    REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED,
    REASON_SHARED_OUTAGE_UNDOCUMENTED,
    admit_g4_session,
    g4_session_bundle_block,
    recompute_watermark_from_store,
)
from renquant_orchestrator.g4_shadow_job import (
    G4ArmSpec,
    G4EvidenceIntegrityError,
    G4EvidenceStore,
    build_arm_record,
    build_failure_record,
    decision_digest_of,
    run_g4_shadow_session,
)
from tests.test_g4_shadow_job import (
    CAL_ID,
    EARLY,
    PRICE_ID,
    PRODUCED_AT,
    T,
    _arms,
    _inputs,
    _run,
    _sha,
    _window,
)

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

EVALUATED_AT = dt.datetime(2026, 7, 17, 22, 0, tzinfo=UTC)


def _admit(store: G4EvidenceStore, *, session: str = T, **kwargs):
    kwargs.setdefault("session_window", _window(session))
    kwargs.setdefault("expected_calendar_id", CAL_ID)
    kwargs.setdefault("expected_price_source_id", PRICE_ID)
    kwargs.setdefault("evaluated_at", EVALUATED_AT)
    return admit_g4_session(store, expected_session=session, **kwargs)


def _write_both_failures(
    store: G4EvidenceStore,
    kind: str,
    *,
    l1_evidence=(),
    champion_evidence=(),
) -> None:
    ts = dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC)
    for arm, refs in ((ARM_L1, l1_evidence), (ARM_CHAMPION, champion_evidence)):
        store.write_failure_record(
            build_failure_record(
                arm=arm,
                decision_session=T,
                kind=kind,
                detail=f"{arm} affected",
                outage_evidence=refs,
                recorded_at=ts,
            )
        )


def _write_both_failures_raw(
    store: G4EvidenceStore,
    kind: str,
    *,
    l1_evidence,
    champion_evidence,
) -> None:
    """Write both arms' failure records with the evidence injected RAW —
    bypassing ``build_failure_record``'s fail-fast shape validation, so
    the admission-side degrade path is exercised on the bytes an
    adversarial / buggy writer could land on disk."""
    ts = dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC)
    for arm, refs in ((ARM_L1, l1_evidence), (ARM_CHAMPION, champion_evidence)):
        record = build_failure_record(
            arm=arm,
            decision_session=T,
            kind=kind,
            detail=f"{arm} affected",
            recorded_at=ts,
        )
        record["failure"]["outage_evidence"] = list(refs)
        store.write_failure_record(record)


# ---------------------------------------------------------------------------
# Happy path + ledger persistence
# ---------------------------------------------------------------------------

class TestAdmittedSession:
    def test_clean_session_admits_with_no_budget_charge(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = _admit(store)
        assert entry["ok"] is True and entry["admissible"] is True
        assert entry["reason_codes"] == []
        assert entry["failure_class"] is None
        assert entry["budget"] is None
        assert entry["ledger_outcome"] == "created"
        assert Path(entry["ledger_path"]).exists()
        persisted = json.loads(Path(entry["ledger_path"]).read_text())
        assert persisted["kind"] == "g4_session_admission"
        assert [v["arm"] for v in persisted["arm_verdicts"]] == [ARM_L1, ARM_CHAMPION]

    def test_readmission_is_append_only_no_rewrite(self, tmp_path: Path) -> None:
        """Identical verdict re-evaluated later: first write wins, one
        ledger file, nothing rewritten."""
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        first = _admit(store)
        original = Path(first["ledger_path"]).read_bytes()
        again = _admit(store, evaluated_at=EVALUATED_AT + dt.timedelta(hours=1))
        assert again["ledger_path"] == first["ledger_path"]
        assert again["ledger_outcome"] == "retry"
        assert Path(first["ledger_path"]).read_bytes() == original
        assert len(list(Path(first["ledger_path"]).parent.iterdir())) == 1

    def test_changed_verdict_lands_side_by_side(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        first = _admit(store)
        # New divergent evidence changes the verdict -> a NEW ledger file
        # next to the old one; the old verdict is never rewritten.
        diverged = G4ArmSpec(
            arm=ARM_CHAMPION,
            artifact_digests={"champion": _sha("champ-a")},
            config_digest=_sha("cfg"),
            scores={"AAPL": 9.9, "MSFT": 9.9},
        )
        _run(store, arms=[_arms()[0], diverged])
        second = _admit(store)
        assert second["ledger_path"] != first["ledger_path"]
        assert second["ok"] is False
        assert len(list(Path(first["ledger_path"]).parent.iterdir())) == 2


# ---------------------------------------------------------------------------
# (c) expected-session: a missing session is DETECTED
# ---------------------------------------------------------------------------

class TestMissingSession:
    def test_missing_session_is_detected_and_charged_idio(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")  # job never ran
        entry = _admit(store)
        assert entry["ok"] is False and entry["admissible"] is False
        assert entry["reason_codes"] == [REASON_MISSING_SESSION]
        assert entry["failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        assert entry["ledger_outcome"] == "created"  # the gap itself is on the ledger

    def test_record_claiming_another_session_is_binding_failure(
        self, tmp_path: Path
    ) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        # smuggle a T-claiming... a record claiming a DIFFERENT session
        # into T's evidence directory (raw write — the store would refuse)
        rogue = dict(_run(store)["records"][ARM_L1])
        rogue["decision_session"] = "2026-07-16"
        rogue["job_id"] = "sha256:" + "1" * 64
        rogue["decision_digest"] = decision_digest_of(rogue)
        target = store.records_dir(T) / "l1-rogue-session.json"
        target.write_text(json.dumps(rogue))
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_SESSION_BINDING_MISMATCH in entry["reason_codes"]
        assert REASON_SESSION_MISMATCH in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC

    def test_malformed_expected_session_is_caller_error(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        with pytest.raises(ValueError):
            admit_g4_session(store, expected_session="not-a-date")


# ---------------------------------------------------------------------------
# v4 §6(b) adversarial battery
# ---------------------------------------------------------------------------

class TestAdversarialFailures:
    def test_late_watermark_recompute_mismatch(self, tmp_path: Path) -> None:
        """The declared watermark is not self-certifying: a record
        declaring a LATER watermark than its manifested snapshot bytes
        support fails the byte-level recomputation AND the close bound."""
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)  # champion stays clean
        late = dict(results["records"][ARM_L1])
        late["declared_input_watermark"] = dt.datetime(
            2026, 7, 17, 16, 30, tzinfo=ET
        ).isoformat()  # after the 16:00 close AND unsupported by bytes
        late["decision_digest"] = decision_digest_of(late)
        store.write_record(late)  # divergent duplicate now also present
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_WATERMARK_AFTER_CLOSE in entry["reason_codes"]
        assert REASON_WATERMARK_RECOMPUTE_MISMATCH in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC

    def test_watermark_hook_fails_closed_on_unresolvable_digest(
        self, tmp_path: Path
    ) -> None:
        """Manifest references bytes the store never saw -> recomputation
        impossible -> watermark mismatch (fail-closed), never a pass."""
        store = G4EvidenceStore(tmp_path / "g4")
        record = build_arm_record(
            _arms()[0],
            decision_session=T,
            session_window=_window(),
            input_manifest={
                "universe": {
                    "digest": "sha256:" + "a" * 64,  # never stored
                    "max_event_time": "2026-07-17T13:00:00+00:00",
                }
            },
            calendar_id=CAL_ID,
            price_source_id=PRICE_ID,
            produced_at=PRODUCED_AT,
        )
        store.write_record(record)
        entry = _admit(store)
        assert REASON_WATERMARK_RECOMPUTE_MISMATCH in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        hook = recompute_watermark_from_store(store)
        assert hook(record["input_manifest"]) is None

    def test_divergent_retry_is_integrity_failure(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        diverged = G4ArmSpec(
            arm=ARM_CHAMPION,
            artifact_digests={"champion": _sha("champ-a")},
            config_digest=_sha("cfg"),
            scores={"AAPL": 9.9, "MSFT": 9.9},
        )
        _run(store, arms=[_arms()[0], diverged])
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_DIVERGENT_RETRY in entry["reason_codes"]
        assert entry["failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC

    def test_missing_arm_is_integrity_failure(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)
        os.chmod(results["paths"][ARM_CHAMPION], 0o644)
        Path(results["paths"][ARM_CHAMPION]).unlink()  # simulate the arm never landing
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_MISSING_ARM in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        champion = [v for v in entry["arm_verdicts"] if v["arm"] == ARM_CHAMPION]
        assert champion == []  # no record to attribute

    def test_tampered_in_place_record_fails_digest_recompute(
        self, tmp_path: Path
    ) -> None:
        """Observation 2: the admission recomputes the decision digest
        over full content, so an in-place mutation riding the old digest
        is caught even though every §2 field still validates."""
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)
        path = Path(results["paths"][ARM_L1])
        record = json.loads(path.read_text())
        record["orders"] = [{"ticker": "MSFT", "side": "buy", "weight": 1.0}]
        os.chmod(path, 0o644)
        path.write_text(json.dumps(record))
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_DECISION_DIGEST_MISMATCH in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC

    def test_unreadable_evidence_surfaces(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        (store.records_dir(T) / "zz-corrupt.json").write_bytes(b"\x00not json")
        entry = _admit(store)
        assert entry["ok"] is False
        assert REASON_EVIDENCE_UNREADABLE in entry["reason_codes"]

    def test_early_close_violation_inadmissible_at_admission(
        self, tmp_path: Path
    ) -> None:
        """(b) end to end: the record the early-close job run left behind
        for forensics is inadmissible — 14:30 ET is after the 13:00 ET
        half-day close."""
        store = G4EvidenceStore(tmp_path / "g4")
        inputs = {
            "universe": {
                "event_times": [dt.datetime(2026, 11, 27, 14, 30, tzinfo=ET)],
                "payload": {"tickers": ["AAPL", "MSFT"]},
            },
        }
        with pytest.raises(G4EvidenceIntegrityError):
            run_g4_shadow_session(
                store,
                decision_session=EARLY,
                session_window=_window(EARLY),
                inputs=inputs,
                arms=_arms(),
                calendar_id=CAL_ID,
                price_source_id=PRICE_ID,
                produced_at=dt.datetime(2026, 11, 27, 14, 45, tzinfo=ET),
            )
        entry = _admit(store, session=EARLY)
        assert entry["ok"] is False
        assert REASON_WATERMARK_AFTER_CLOSE in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC


# ---------------------------------------------------------------------------
# (a) documented-outage qualifier on B_shared
# ---------------------------------------------------------------------------

class TestSharedOutageQualifier:
    REFS = (
        {
            "kind": "venue_halt",
            "ref": "https://status.exchange.test/incident/2026-07-17-halt",
            "observed_at": "2026-07-17T18:41:00+00:00",
        },
    )

    def test_documented_shared_outage_charges_b_shared(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _write_both_failures(
            store,
            FAILURE_KIND_VENUE_OUTAGE,
            l1_evidence=self.REFS,
            champion_evidence=self.REFS,
        )
        entry = _admit(store)
        assert entry["ok"] is False and entry["admissible"] is False
        assert entry["failure_class"] == FAILURE_CLASS_SHARED
        assert entry["pipeline_failure_class"] == FAILURE_CLASS_SHARED
        assert entry["budget"] == BUDGET_SHARED
        assert entry["outage_documented"] is True
        assert entry["degraded"] is False
        assert REASON_SHARED_OUTAGE_FAILURE in entry["reason_codes"]
        assert entry["outage_evidence"][ARM_L1] == list(self.REFS)
        assert entry["outage_evidence"][ARM_CHAMPION] == list(self.REFS)

    def test_undocumented_shared_outage_degrades_to_b_idio(
        self, tmp_path: Path
    ) -> None:
        """(a): the SAME symmetric shared-kind failure WITHOUT evidence
        references cannot charge B_shared — v4 §2 names 'documented'
        outages; the declaration alone is unfalsifiable from records."""
        store = G4EvidenceStore(tmp_path / "g4")
        _write_both_failures(store, FAILURE_KIND_VENUE_OUTAGE)
        entry = _admit(store)
        assert entry["ok"] is False
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        assert entry["degraded"] is True
        assert entry["failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        # the contract's own classification is preserved, not hidden
        assert entry["pipeline_failure_class"] == FAILURE_CLASS_SHARED
        assert REASON_SHARED_OUTAGE_UNDOCUMENTED in entry["reason_codes"]
        assert entry["outage_documented"] is False

    def test_one_armed_documentation_still_degrades(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _write_both_failures(
            store, FAILURE_KIND_PRICE_SOURCE, l1_evidence=self.REFS
        )
        entry = _admit(store)
        assert REASON_SHARED_PRICE_SOURCE_FAILURE in entry["reason_codes"]
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        assert entry["degraded"] is True
        assert REASON_SHARED_OUTAGE_UNDOCUMENTED in entry["reason_codes"]

    @pytest.mark.parametrize(
        "kind",
        [FAILURE_KIND_JOB_CRASH, FAILURE_KIND_FILL, FAILURE_KIND_VALUATION],
    )
    def test_asymmetric_failure_never_consults_the_qualifier(
        self, tmp_path: Path, kind: str
    ) -> None:
        """One arm fails (crash / FILL / valuation — v4 §2's asymmetric
        classes, documented or not), the other qualifies: classification
        is idiosyncratic and B_idio — the qualifier only gates the
        B_shared charge, and an asymmetric fill failure follows §2."""
        store = G4EvidenceStore(tmp_path / "g4")
        results = _run(store)
        os.chmod(results["paths"][ARM_L1], 0o644)
        Path(results["paths"][ARM_L1]).unlink()
        store.write_failure_record(
            build_failure_record(
                arm=ARM_L1,
                decision_session=T,
                kind=kind,
                detail=f"asymmetric {kind} failure",
                outage_evidence=self.REFS,  # evidence cannot buy B_shared here
                recorded_at=dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC),
            )
        )
        entry = _admit(store)
        assert REASON_ASYMMETRIC_ARM_FAILURE in entry["reason_codes"]
        assert entry["failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        assert entry["pipeline_failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        assert entry["degraded"] is False


# ---------------------------------------------------------------------------
# (a) tightened: STRUCTURED outage-evidence shape (2026-07-18 review P0-3)
# ---------------------------------------------------------------------------

class TestSharedOutageEvidenceShape:
    """P0-3: `outage_evidence` must be a structured reference —
    {kind ∈ OUTAGE_EVIDENCE_KINDS, ref (non-empty), observed_at
    (ISO-8601 UTC)}, all three required. A shape violation ANYWHERE in
    the session degrades the B_shared charge to B_idio with reason
    ``shared_outage_evidence_malformed`` (fail-closed: evidence that
    cannot be shape-validated buys nothing). All malformed bytes are
    written RAW — the builder fail-fasts, but admission must hold on
    whatever lands on disk."""

    WELL_FORMED = {
        "kind": "venue_halt",
        "ref": "https://status.exchange.test/incident/2026-07-17-halt",
        "observed_at": "2026-07-17T18:41:00+00:00",
    }

    def _admit_with_evidence(self, tmp_path: Path, evidence) -> dict:
        store = G4EvidenceStore(tmp_path / "g4")
        _write_both_failures_raw(
            store,
            FAILURE_KIND_VENUE_OUTAGE,
            l1_evidence=evidence,
            champion_evidence=evidence,
        )
        return _admit(store)

    def _assert_degraded_malformed(self, entry: dict) -> None:
        assert entry["ok"] is False
        assert entry["budget"] == BUDGET_IDIOSYNCRATIC
        assert entry["degraded"] is True
        assert entry["failure_class"] == FAILURE_CLASS_IDIOSYNCRATIC
        # the contract's own classification is preserved, not hidden
        assert entry["pipeline_failure_class"] == FAILURE_CLASS_SHARED
        assert REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED in entry["reason_codes"]
        assert REASON_SHARED_OUTAGE_UNDOCUMENTED not in entry["reason_codes"]
        assert entry["outage_documented"] is False

    def test_well_formed_structured_evidence_charges_b_shared(
        self, tmp_path: Path
    ) -> None:
        """Direction 1: the fully well-formed structured reference —
        written RAW through the same path as every malformed case —
        still charges B_shared."""
        entry = self._admit_with_evidence(tmp_path, [dict(self.WELL_FORMED)])
        assert entry["budget"] == BUDGET_SHARED
        assert entry["outage_documented"] is True
        assert entry["degraded"] is False
        assert REASON_SHARED_OUTAGE_EVIDENCE_MALFORMED not in entry["reason_codes"]
        assert entry["outage_evidence"][ARM_L1] == [self.WELL_FORMED]

    @pytest.mark.parametrize("missing", ["kind", "ref", "observed_at"])
    def test_each_missing_field_degrades_to_b_idio(
        self, tmp_path: Path, missing: str
    ) -> None:
        """Direction 2, per missing field: dropping ANY of the three
        required fields is a shape violation -> degrade."""
        reference = {k: v for k, v in self.WELL_FORMED.items() if k != missing}
        entry = self._admit_with_evidence(tmp_path, [reference])
        self._assert_degraded_malformed(entry)

    def test_unknown_kind_degrades(self, tmp_path: Path) -> None:
        reference = dict(self.WELL_FORMED, kind="dog_ate_the_feed")
        entry = self._admit_with_evidence(tmp_path, [reference])
        self._assert_degraded_malformed(entry)

    def test_empty_ref_degrades(self, tmp_path: Path) -> None:
        reference = dict(self.WELL_FORMED, ref="   ")
        entry = self._admit_with_evidence(tmp_path, [reference])
        self._assert_degraded_malformed(entry)

    def test_non_iso_observed_at_degrades(self, tmp_path: Path) -> None:
        reference = dict(self.WELL_FORMED, observed_at="yesterday-ish")
        entry = self._admit_with_evidence(tmp_path, [reference])
        self._assert_degraded_malformed(entry)

    @pytest.mark.parametrize(
        "observed_at",
        [
            "2026-07-17T18:41:00",  # naive — no offset at all
            "2026-07-17T14:41:00-04:00",  # aware but NOT UTC
        ],
    )
    def test_non_utc_observed_at_degrades(
        self, tmp_path: Path, observed_at: str
    ) -> None:
        reference = dict(self.WELL_FORMED, observed_at=observed_at)
        entry = self._admit_with_evidence(tmp_path, [reference])
        self._assert_degraded_malformed(entry)

    def test_legacy_plain_string_reference_degrades(self, tmp_path: Path) -> None:
        """The pre-P0-3 format — a bare non-empty string — is exactly the
        self-declarable evidence the review rejected; it now degrades."""
        entry = self._admit_with_evidence(
            tmp_path, ["https://status.exchange.test/incident/2026-07-17-halt"]
        )
        self._assert_degraded_malformed(entry)

    def test_one_malformed_reference_poisons_the_charge(
        self, tmp_path: Path
    ) -> None:
        """Fail-closed: both arms carry a WELL-FORMED reference, one arm
        ALSO carries a malformed one -> the whole B_shared charge
        degrades (evidence sets containing garbage are not trusted)."""
        store = G4EvidenceStore(tmp_path / "g4")
        _write_both_failures_raw(
            store,
            FAILURE_KIND_VENUE_OUTAGE,
            l1_evidence=[dict(self.WELL_FORMED), {"kind": "venue_halt"}],
            champion_evidence=[dict(self.WELL_FORMED)],
        )
        entry = _admit(store)
        self._assert_degraded_malformed(entry)

    def test_evidence_not_a_list_degrades(self, tmp_path: Path) -> None:
        """A bare mapping (not a LIST of references) is a shape
        violation of the carrier itself."""
        store = G4EvidenceStore(tmp_path / "g4")
        ts = dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC)
        for arm in (ARM_L1, ARM_CHAMPION):
            record = build_failure_record(
                arm=arm,
                decision_session=T,
                kind=FAILURE_KIND_VENUE_OUTAGE,
                detail=f"{arm} affected",
                recorded_at=ts,
            )
            record["failure"]["outage_evidence"] = "not-a-list"
            store.write_failure_record(record)
        entry = _admit(store)
        self._assert_degraded_malformed(entry)

    def test_builder_fail_fasts_on_malformed_reference(
        self, tmp_path: Path
    ) -> None:
        """`build_failure_record` refuses malformed evidence at write
        time (caller error) — the admission-side degrade exists for
        bytes that bypass the builder."""
        for bad in (
            "plain-string",
            {"kind": "venue_halt", "ref": "x"},  # missing observed_at
            dict(self.WELL_FORMED, kind="unknown_kind"),
            dict(self.WELL_FORMED, observed_at="2026-07-17T14:41:00-04:00"),
        ):
            with pytest.raises(ValueError, match="outage_evidence"):
                build_failure_record(
                    arm=ARM_L1,
                    decision_session=T,
                    kind=FAILURE_KIND_VENUE_OUTAGE,
                    detail="bad evidence",
                    outage_evidence=[bad],
                    recorded_at=dt.datetime(2026, 7, 17, 20, 30, tzinfo=UTC),
                )


# ---------------------------------------------------------------------------
# Registration binding (review 2026-07-18 P0-1/P0-2/P1-4): an admission
# with no frozen registration identifiers is machinery-integrity only and
# is EXPLICITLY not series-eligible.
# ---------------------------------------------------------------------------

class TestRegistrationBinding:
    def test_unbound_admission_is_integrity_only_not_series_eligible(
        self, tmp_path: Path
    ) -> None:
        """No frozen IDs supplied (the public-API default a real caller hits):
        records still pass step-2 machinery integrity, but the verdict is
        EXPLICITLY not a series-admission verdict — the P0-1/P0-2/P1-4
        fail-open ('admissible verdict with unbound IDs') is closed by an
        explicit unbound return (codex option (a))."""
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = admit_g4_session(
            store,
            expected_session=T,
            session_window=_window(T),
            evaluated_at=EVALUATED_AT,
        )
        assert entry["ok"] is True and entry["admissible"] is True
        assert entry["registration_bound"] is False
        assert entry["series_eligible"] is False
        # the explicit unbound marker also rides the daily run-bundle block,
        # so a later enrollment caller sees it without any code change.
        block = g4_session_bundle_block(entry)
        assert block["registration_bound"] is False
        assert block["series_eligible"] is False

    def test_bound_clean_session_is_series_eligible(self, tmp_path: Path) -> None:
        """Frozen IDs supplied (the future pilot runner's job): the contract
        binds them in-record and series_eligible follows admissible."""
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = _admit(store)  # helper supplies CAL_ID / PRICE_ID
        assert entry["ok"] is True and entry["admissible"] is True
        assert entry["registration_bound"] is True
        assert entry["series_eligible"] is True

    def test_frozen_identifier_mismatch_binds_but_fails(self, tmp_path: Path) -> None:
        """Registration WAS supplied but the record's calendar_id does not
        match the frozen value: bound, inadmissible, and not series-eligible
        (the contract's frozen_identifier_mismatch surfaces)."""
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = _admit(store, expected_calendar_id="WRONG-CAL")
        assert entry["registration_bound"] is True
        assert entry["ok"] is False
        assert entry["series_eligible"] is False
        assert REASON_FROZEN_IDENTIFIER_MISMATCH in entry["reason_codes"]

    def test_missing_session_carries_binding_fields(self, tmp_path: Path) -> None:
        """The missing-session early return also carries the binding fields
        (bound here via the helper; series_eligible False because ok False)."""
        store = G4EvidenceStore(tmp_path / "g4")
        entry = _admit(store)  # nothing written -> missing session
        assert entry["ok"] is False
        assert entry["registration_bound"] is True
        assert entry["series_eligible"] is False
        assert REASON_MISSING_SESSION in entry["reason_codes"]


# ---------------------------------------------------------------------------
# Run-bundle surface (the #547/#549 additive/absent-tolerant pattern)
# ---------------------------------------------------------------------------

class TestRunBundleBlock:
    def test_absent_while_job_not_scheduled(self) -> None:
        assert g4_session_bundle_block(None) == "absent"
        assert g4_session_bundle_block() == "absent"

    def test_malformed_entry_degrades_to_absent(self) -> None:
        assert g4_session_bundle_block("not-a-dict") == "absent"
        assert g4_session_bundle_block({"kind": "other"}) == "absent"

    def test_real_entry_summary_forwarded(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = _admit(store)
        block = g4_session_bundle_block(entry)
        assert block["expected_session"] == T
        assert block["ok"] is True and block["admissible"] is True
        assert block["budget"] is None
        assert block["ledger_path"] == entry["ledger_path"]
        json.dumps(block)  # JSON-safe as-is

    def test_failure_entry_summary_carries_budget(self, tmp_path: Path) -> None:
        store = G4EvidenceStore(tmp_path / "g4")
        entry = _admit(store)  # missing session
        block = g4_session_bundle_block(entry)
        assert block["ok"] is False
        assert block["budget"] == BUDGET_IDIOSYNCRATIC
        assert REASON_MISSING_SESSION in block["reason_codes"]
        # decision detail (scores/orders) is NOT in the bundle summary
        assert "arm_verdicts" not in block and "outage_evidence" not in block

    def test_persisted_daily_run_bundle_records_g4_entry(
        self, tmp_path: Path
    ) -> None:
        """End to end through PersistDailyRunBundleTask (the #547 pattern):
        a real admission entry lands in run_bundle.json as the additive
        ``g4_session`` key."""
        from tests.test_serving_bundle_provenance import (
            _persisted_bundle,
            _setup_daily_ctx,
        )

        store = G4EvidenceStore(tmp_path / "g4")
        _run(store)
        entry = _admit(store)
        ctx = _setup_daily_ctx(tmp_path)
        ctx.g4_session_admission = entry
        bundle = _persisted_bundle(tmp_path, ctx)
        block = bundle["g4_session"]
        assert block["expected_session"] == T
        assert block["ok"] is True and block["budget"] is None
        assert block["contract_version"] == 1
