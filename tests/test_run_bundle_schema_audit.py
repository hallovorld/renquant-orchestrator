"""The audit must detect BOTH failure modes and must pass a clean bundle.

A check that only ever reports a problem is as useless as one that never does, so
every failure mode below is paired with the negative case that proves the report
is caused by the defect and not by the fixture.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "run_bundle_schema_audit",
    Path(__file__).resolve().parent.parent / "ops" / "run_bundle_schema_audit.py",
)
audit_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_mod)


def _write(tmp_path: Path, payload: object, name: str = "run_bundle.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    return p


def _minimal_valid() -> dict:
    """A bundle the REAL validator accepts.

    Note what this is not: the set of fields `is_required()` reports. That set
    (`source`, `decision_trace`, `order_intents`) does NOT validate on its own,
    because `LiveRunBundle` carries a cross-field rule --- *"requires at least one
    state source: state_mutations, execution_audit, or submitted_orders"*
    `[VERIFIED — validate_live_run_bundle on a required-fields-only dict]`.

    That discovery is the codex BLOCKER on orch#624 in miniature: the audit used to
    infer `would_validate` from key presence, and key presence accepts a bundle the
    real validator rejects. The fixture below therefore satisfies the rule, and
    `test_required_fields_alone_do_NOT_validate` pins the gap explicitly.
    """
    return {"source": "test", "decision_trace": [], "order_intents": [],
            "submitted_orders": [{"symbol": "AAPL", "qty": 1}]}


def test_required_fields_alone_do_NOT_validate(tmp_path):
    """The exact approximation codex blocked. `is_required()` understates the
    requirement, so a presence check is not a validation."""
    required, _ = audit_mod.schema_fields()
    presence_only = {"source": "t", "decision_trace": [], "order_intents": []}
    assert required - set(presence_only) == set(), (
        "fixture must contain every is_required() field, or it tests the wrong thing")
    r = audit_mod.audit_bundle(_write(tmp_path, presence_only))
    assert r["missing_required"] == [], "no required KEY is absent"
    assert r["would_validate"] is False, (
        "the real validator rejects it on a cross-field rule --- a presence check "
        "would have called this valid")
    assert "at least one state source" in r["validation_error"]


def test_all_required_keys_present_but_an_invalid_VALUE_is_rejected(tmp_path):
    """The regression fixture codex asked for. Every required key is present and one
    value has the wrong type; an inferred `would_validate` would return True."""
    for field, bad in (("decision_trace", "not-a-list"),
                       ("source", None),
                       ("submitted_orders", "nope")):
        payload = _minimal_valid() | {field: bad}
        r = audit_mod.audit_bundle(_write(tmp_path, payload, name=f"rb_{field}.json"))
        assert r["missing_required"] == [], f"{field}: no key is absent"
        assert r["would_validate"] is False, f"{field}: invalid value must not validate"
        assert r["validation_error"], f"{field}: the validator error must be recorded"


def test_the_validator_error_is_recorded_not_just_a_boolean(tmp_path):
    """A bare False cannot be triaged. The audit must carry WHY."""
    r = audit_mod.audit_bundle(_write(tmp_path, {"decision_trace": []}))
    assert r["would_validate"] is False
    assert isinstance(r["validation_error"], str) and r["validation_error"]


# --- failure mode 1: a required field is absent -----------------------------

def test_missing_required_field_is_reported(tmp_path):
    """The orchestrator's daily bundle has no `source`, so it cannot validate."""
    payload = _minimal_valid()
    del payload["source"]
    r = audit_mod.audit_bundle(_write(tmp_path, payload))
    assert r["missing_required"] == ["source"]
    assert r["would_validate"] is False
    assert r["conformant"] is False


def test_a_bundle_with_every_required_field_validates(tmp_path):
    """Negative case: the rejection above is caused by absence, not the fixture."""
    r = audit_mod.audit_bundle(_write(tmp_path, _minimal_valid()))
    assert r["missing_required"] == []
    assert r["would_validate"] is True
    assert r["conformant"] is True


# --- failure mode 2: fields the schema silently discards --------------------

def test_undeclared_fields_are_reported_as_dropped(tmp_path):
    """THE POINT OF THE TOOL. A bundle can validate while losing its provenance.

    This is the AC6 R4 finding in miniature: `override_provenance` is exactly the
    kind of field AC6 wants recorded, and a schema that discards undeclared keys
    would return a green check having thrown it away.
    """
    payload = _minimal_valid() | {
        "override_provenance": {"identity": "x", "expiry": "y", "binding": "z"},
        "artifact_manifest": {"sha256": "deadbeef"},
    }
    r = audit_mod.audit_bundle(_write(tmp_path, payload))
    assert r["would_validate"] is True, "it validates -- that is the hazard"
    assert "override_provenance" in r["dropped_by_schema"]
    assert "artifact_manifest" in r["dropped_by_schema"]
    assert r["conformant"] is False, (
        "validating while discarding the provenance field must NOT count as conformant"
    )


def test_the_drop_hazard_is_read_from_the_schema_not_assumed():
    """Anti-vacuity: if the schema ever sets extra='forbid', this must change.

    The tool's warning is only meaningful if it tracks the real config. Pinning the
    observed value keeps a future schema change from silently invalidating the
    finding this audit was written to support.
    """
    assert audit_mod.schema_drops_unknown_keys() is True, (
        "the shared schema no longer discards undeclared keys -- re-derive the "
        "AC6 R4 recommendation, it was grounded on this behaviour"
    )


# --- IO / usage errors must not read as a clean audit -----------------------

def test_unreadable_bundle_is_not_a_pass(tmp_path):
    bad = tmp_path / "run_bundle.json"
    bad.write_text("{not json")
    r = audit_mod.audit_bundle(bad)
    assert r["readable"] is False
    assert audit_mod.main([str(bad)]) == 2


def test_non_object_top_level_is_rejected(tmp_path):
    r = audit_mod.audit_bundle(_write(tmp_path, [1, 2, 3]))
    assert r["readable"] is False
    assert "not an object" in r["error"]


def test_no_bundles_found_exits_2_not_0(tmp_path):
    """An empty sweep must not look like a clean sweep."""
    assert audit_mod.main([str(tmp_path)]) == 2


def test_directory_recursion_finds_nested_bundles(tmp_path):
    nested = tmp_path / "run-a"
    nested.mkdir()
    _write(nested, _minimal_valid())
    assert audit_mod.main([str(tmp_path)]) == 0


def test_exit_code_1_when_a_bundle_loses_fields(tmp_path):
    _write(tmp_path, _minimal_valid() | {"stage_trace": []})
    assert audit_mod.main([str(tmp_path)]) == 1


# --- the tool must not mutate what it audits --------------------------------

def test_audit_does_not_modify_the_bundle_file(tmp_path):
    p = _write(tmp_path, _minimal_valid() | {"stage_trace": []})
    before = p.read_bytes()
    audit_mod.audit_bundle(p)
    assert p.read_bytes() == before, "the audit is read-only by contract"
