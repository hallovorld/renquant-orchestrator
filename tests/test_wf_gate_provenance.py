"""AC6 R4 step 2 — the daily run bundle records the gate it served under.

#669 made this bundle record a CONTRACT VERDICT against `LiveRunBundle`. It still
recorded nothing about the WF gate or any operator override, and `LiveRunBundle` itself
has no override-provenance field. So a run that served under an override left no trace
of it in the artifact kept precisely to answer "what was in force".
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from renquant_orchestrator.wf_gate_provenance import (  # noqa: E402
    CANONICAL_KEY,
    LEGACY_KEY,
    PROVENANCE_FIELDS,
    STATUS_NO_ARTIFACT,
    STATUS_NO_GATE_BLOCK,
    STATUS_PRESENT,
    wf_gate_provenance,
)

FULL = {
    "passed": False,
    "gate_verdict_before_override": "FAIL",
    "operator_authorized_override": True,
    "override_applied_at": "2026-07-20T00:00:00Z",
    "override_reason": "operator accepted a documented risk",
    "diagnostic_only": False,
    "gate_version": "v3",
}


def test_a_served_override_is_recorded_in_full():
    b = wf_gate_provenance({"metadata": {"wf_gate_metadata": FULL}})
    assert b["status"] == STATUS_PRESENT
    assert b["source_key"] == CANONICAL_KEY
    assert b["operator_authorized_override"] is True
    assert b["override_reason"] == "operator accepted a documented risk"
    assert b["fields_absent"] == []


def test_NO_ARTIFACT_and_NO_GATE_STAMP_are_DIFFERENT_statuses():
    """Absent is not clean, and the two absences have different remedies.

    A block that omitted itself when it found nothing would be indistinguishable from a
    clean gate — the failure mode this programme keeps re-learning.
    """
    assert wf_gate_provenance(None)["status"] == STATUS_NO_ARTIFACT
    assert wf_gate_provenance({})["status"] == STATUS_NO_ARTIFACT
    assert wf_gate_provenance({"artifact_id": "x"})["status"] == STATUS_NO_GATE_BLOCK


def test_an_absent_status_never_looks_like_a_pass():
    for arg in (None, {}, {"artifact_id": "x"}):
        b = wf_gate_provenance(arg)
        assert b["status"] != STATUS_PRESENT
        assert "passed" not in b
        assert "operator_authorized_override" not in b
        assert "note" in b and "not evidence" in b["note"] or b["status"] == STATUS_NO_GATE_BLOCK


def test_the_canonical_key_wins_on_CONFLICTING_values():
    """Twin registry R8: the two copies disagree on 2 of the 14 prod panels carrying
    both. A precedence test whose arms are identical asserts nothing."""
    legacy = dict(FULL, override_reason="LEGACY-STALE", gate_version="v1",
                  operator_authorized_override=False)
    b = wf_gate_provenance({"metadata": {"wf_gate_metadata": FULL},
                            "wf_gate_metadata": legacy})
    assert b["source_key"] == CANONICAL_KEY
    assert b["override_reason"] == "operator accepted a documented risk"
    assert b["operator_authorized_override"] is True


def test_an_EMPTY_canonical_block_does_not_resurrect_the_legacy_one():
    """Presence decides, not truthiness — else an emptied stamp seals with a dead value."""
    b = wf_gate_provenance({"metadata": {"wf_gate_metadata": {}},
                            "wf_gate_metadata": FULL})
    assert b["status"] == STATUS_NO_GATE_BLOCK
    assert "operator_authorized_override" not in b


def test_the_legacy_key_is_still_read_when_canonical_is_ABSENT():
    b = wf_gate_provenance({"wf_gate_metadata": FULL})
    assert b["status"] == STATUS_PRESENT
    assert b["source_key"] == LEGACY_KEY


def test_a_PARTIAL_stamp_names_what_is_missing():
    b = wf_gate_provenance({"metadata": {"wf_gate_metadata": {"passed": True}}})
    assert b["status"] == STATUS_PRESENT
    assert b["passed"] is True
    assert set(b["fields_absent"]) == set(PROVENANCE_FIELDS) - {"passed"}


def test_it_never_raises_on_hostile_input():
    """A provenance recorder that can abort the daily run is worse than the gap."""
    for arg in (None, 0, "", [], {"metadata": 5}, {"metadata": {"wf_gate_metadata": 7}},
                {"wf_gate_metadata": "not-a-dict"},
                {"metadata": {"wf_gate_metadata": {"passed": object()}}}):
        out = wf_gate_provenance(arg)
        assert isinstance(out, dict) and "status" in out


def test_the_daily_bundle_actually_carries_the_block():
    """Wiring, not just the helper — a block nothing calls records nothing."""
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "src/renquant_orchestrator/daily.py").read_text(encoding="utf-8")
    assert '"wf_gate_provenance": wf_gate_provenance(' in src
