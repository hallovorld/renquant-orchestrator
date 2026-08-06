"""The monitor and the buy-admission license must not disagree silently.

Fixtures are synthetic. One test does read the LIVE monitor — but only to assert
that this probe's mirrored field list still equals the monitor's, which is a
property of the code, not of today's artifacts. A mirror that drifts is worse
than no mirror.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.freshness_axis_agreement_probe import (  # noqa: E402
    AGREE, CONTRADICTION, DATA_CUTOFF_FIELDS, NOT_LICENSED,
    ArtifactUnreadable, main, probe,
)

LICENSED = "freshness_fallback_rfc210"


def _art(tmp_path: pathlib.Path, payload: dict, name="a.json") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --- the mirror must not drift -------------------------------------------

def test_mirrored_field_list_equals_the_monitors():
    """This probe mirrors DATA_CUTOFF_FIELDS so it still reports when the
    monitor cannot be imported. If the monitor gains an axis and this list does
    not, the probe would call a licensed artifact a CONTRADICTION that the
    monitor can actually resolve."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
    from renquant_orchestrator import model_freshness_monitor as M
    assert list(M.DATA_CUTOFF_FIELDS) == DATA_CUTOFF_FIELDS


def test_trained_date_is_not_one_of_the_binding_axes():
    """The load-bearing asymmetry. If trained_date ever enters this list the
    contradiction disappears by redefinition rather than by fix."""
    assert "trained_date" not in DATA_CUTOFF_FIELDS


# --- the three states -----------------------------------------------------

def test_licensed_with_no_binding_cutoff_is_a_CONTRADICTION(tmp_path):
    a = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02"})
    p = probe(a)
    assert p["state"] == CONTRADICTION
    assert p["n_binding_cutoff_fields"] == 0
    assert p["under_rfc210_license"] is True


@pytest.mark.parametrize("field", DATA_CUTOFF_FIELDS)
def test_any_single_binding_axis_resolves_it(tmp_path, field):
    a = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02",
                        field: "2026-07-30"}, name=f"{field}.json")
    p = probe(a)
    assert p["state"] == AGREE
    assert p["binding_cutoff_fields_present"] == [field]


def test_an_unlicensed_artifact_is_its_own_state(tmp_path):
    """No contradiction if the license is not the admitting authority — saying
    otherwise would flag every artifact that never invoked the fallback."""
    a = _art(tmp_path, {"promotion_basis": "wf_gate_pass", "trained_date": "2026-08-02"})
    assert probe(a)["state"] == NOT_LICENSED


def test_metadata_fallback_is_read_like_the_license_reads_it(tmp_path):
    """The license looks top-level first then metadata. A probe that only read
    top-level would report a CONTRADICTION for an artifact the license resolves
    from metadata — a false finding in my own favour."""
    a = _art(tmp_path, {"metadata": {"promotion_basis": LICENSED,
                                     "trained_date": "2026-08-02",
                                     "cutoff_date": "2026-07-01"}})
    p = probe(a)
    assert p["state"] == AGREE
    assert p["under_rfc210_license"] is True


def test_top_level_wins_over_metadata(tmp_path):
    a = _art(tmp_path, {"promotion_basis": LICENSED,
                        "metadata": {"promotion_basis": "wf_gate_pass"}})
    assert probe(a)["under_rfc210_license"] is True


# --- it must not overclaim ------------------------------------------------

def test_contradiction_carries_the_refusal_to_call_it_stale(tmp_path):
    """The probe reports an UNKNOWABLE vintage, never a stale one. Concluding
    'the model is stale' would invent the number it exists to report missing."""
    a = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02"})
    p = probe(a)
    assert "does_NOT_establish" in p
    assert "stale" in p["does_NOT_establish"]
    assert "may be perfectly" in p["does_NOT_establish"]


def test_render_of_a_contradiction_says_what_it_does_not_establish(tmp_path):
    from ops.renquant104.freshness_axis_agreement_probe import render
    a = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02"})
    text = render(probe(a))
    assert "does NOT establish" in text


# --- refusals -------------------------------------------------------------

def test_missing_artifact_refuses(tmp_path):
    with pytest.raises(ArtifactUnreadable):
        probe(tmp_path / "absent.json")


def test_non_object_payload_refuses_rather_than_agreeing(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("[]", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable):
        probe(a)


def test_exit_codes(tmp_path):
    bad = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02"},
               name="bad.json")
    ok = _art(tmp_path, {"promotion_basis": LICENSED, "trained_date": "2026-08-02",
                         "cutoff_date": "2026-07-01"}, name="ok.json")
    assert main(["--artifact", str(bad)]) == 1
    assert main(["--artifact", str(ok)]) == 0
    assert main(["--artifact", str(tmp_path / "gone.json")]) == 2
