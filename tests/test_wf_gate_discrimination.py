"""The admission key must not collapse artifacts whose measured skill differs.

Fixtures are synthetic. The live tree currently shows 36 artifacts under one
fingerprint with 8 distinct genuine_ic values; a test bound to those numbers
would go red the day the collapse is FIXED, which is backwards.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.wf_gate_discrimination_probe import (  # noqa: E402
    KEY_FINGERPRINT, KEY_GENUINE_IC, KEY_USED, NoArtifacts, scan, wf_metadata,
)


def _art(root: pathlib.Path, name: str, *, fp="sha256:aaa", ic=0.001,
         used=False, nest=True, omit_fp=False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    wf = {KEY_USED: used, KEY_GENUINE_IC: ic}
    if not omit_fp:
        wf[KEY_FINGERPRINT] = fp
    payload = {"metadata": {"wf_gate_metadata": wf}} if nest else {"wf_gate_metadata": wf}
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


# --- the collapse ---------------------------------------------------------

def test_one_key_over_differing_skill_is_NO_DISCRIMINATION(tmp_path):
    for i, ic in enumerate([0.001, 0.005, 0.009]):
        _art(tmp_path, f"a{i}.json", fp="sha256:same", ic=ic)
    r = scan(tmp_path)
    assert r["n_distinct_fingerprints"] == 1
    assert r["n_sharing_largest_fingerprint"] == 3
    assert r["n_distinct_genuine_ic_under_largest_fingerprint"] == 3
    assert r["discriminates"] is False


def test_one_key_over_IDENTICAL_skill_is_not_a_finding(tmp_path):
    """Sharing a key is only a defect when the things behind it differ."""
    for i in range(3):
        _art(tmp_path, f"a{i}.json", fp="sha256:same", ic=0.004)
    r = scan(tmp_path)
    assert r["n_distinct_genuine_ic_under_largest_fingerprint"] == 1
    assert r["discriminates"] is True


def test_distinct_keys_discriminate(tmp_path):
    _art(tmp_path, "a.json", fp="sha256:one", ic=0.001)
    _art(tmp_path, "b.json", fp="sha256:two", ic=0.009)
    r = scan(tmp_path)
    assert r["n_distinct_fingerprints"] == 2
    assert r["discriminates"] is True


# --- keys are READ, not guessed -------------------------------------------

def test_a_missing_fingerprint_is_MISSING_not_silently_None(tmp_path):
    """The failure this probe's docstring records: guessing a field name got
    None from every artifact and nearly published '1 distinct hash'."""
    _art(tmp_path, "a.json", omit_fp=True)
    r = scan(tmp_path)
    assert r["n_artifacts_missing_fingerprint"] == 1
    assert "<MISSING>" in r["largest_fingerprint"]


def test_metadata_nesting_is_canonical_and_top_level_is_the_fallback(tmp_path):
    _art(tmp_path, "nested.json", fp="sha256:x", nest=True)
    _art(tmp_path, "flat.json", fp="sha256:x", nest=False)
    assert scan(tmp_path)["n_artifacts_with_wf_metadata"] == 2


def test_nested_wins_when_both_present(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "both.json").write_text(json.dumps({
        "metadata": {"wf_gate_metadata": {KEY_FINGERPRINT: "sha256:nested"}},
        "wf_gate_metadata": {KEY_FINGERPRINT: "sha256:top"}}), encoding="utf-8")
    assert scan(tmp_path)["largest_fingerprint"] == "sha256:nested"


def test_non_dict_wf_metadata_is_not_adopted():
    assert wf_metadata({"wf_gate_metadata": "nope"}) is None
    assert wf_metadata({"metadata": {"wf_gate_metadata": []}}) is None
    assert wf_metadata([]) is None


# --- exclusions and refusals ---------------------------------------------

def test_diagnostics_and_bundle_copies_are_excluded(tmp_path):
    """Archived snapshots inflated an earlier reachability count 47x. They are
    not production artifacts and must not pad this one."""
    _art(tmp_path, "real.json", fp="sha256:x")
    _art(tmp_path / "diagnostics" / "sweep", "copy.json", fp="sha256:x")
    _art(tmp_path / "bundle", "copy.json", fp="sha256:x")
    assert scan(tmp_path)["n_artifacts_with_wf_metadata"] == 1


def test_zero_artifacts_refuses_rather_than_reporting_discrimination(tmp_path):
    with pytest.raises(NoArtifacts):
        scan(tmp_path)


def test_unparseable_json_is_skipped_not_fatal(tmp_path):
    _art(tmp_path, "good.json", fp="sha256:x")
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
    assert scan(tmp_path)["n_artifacts_with_wf_metadata"] == 1


# --- it must not overclaim ------------------------------------------------

def test_result_refuses_to_rank_the_artifacts(tmp_path):
    _art(tmp_path, "a.json", fp="sha256:s", ic=0.001)
    _art(tmp_path, "b.json", fp="sha256:s", ic=0.009)
    r = scan(tmp_path)
    assert "which artifact is better" in r["does_NOT_establish"]
    assert "not enforced" in r["does_NOT_establish"]
