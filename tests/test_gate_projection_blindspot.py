"""What the WF gate hashes vs what actually distinguishes the boosters.

Measured 2026-08-01 over 12 distinct boosters: 40 artifact fields, 23 constant, 17
varying — and ALL SIX fields of `run_wf_gate._recipe_projection` are in the constant set.
The recipe fingerprint is invariant by construction, not by accident.

The varying set includes `oos_mean_ic` / `oos_per_fold_ic` / `oos_std_ic`, 12 distinct
values each: per-artifact evidence the admission path never reads. And it is not decisive
either — 3 folds, best-worst gap 0.51–0.65 SE — so "just promote on oos_mean_ic" would
rank on noise. Both halves are pinned here because either alone misleads.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import gate_projection_blindspot as G  # noqa: E402

DATA = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "research" / "data"
        / "2026-08-01-gate-projection-blindspot")


@pytest.fixture(scope="module")
def rep():
    return json.loads((DATA / "blindspot.json").read_text())


# ------------------------------------------------------------------ the blind spot --
def test_every_projection_field_is_CONSTANT_across_the_twelve(rep):
    assert rep["n_distinct_boosters"] == 12
    assert rep["projection_fields_all_constant"] is True
    assert [p["field"] for p in rep["projection_fields"]] == list(G.PROJECTION_FIELDS)
    assert not any(p["varies"] for p in rep["projection_fields"])


def test_seventeen_fields_DO_vary_so_the_artifacts_are_not_identical(rep):
    """If nothing varied, an invariant fingerprint would be correct rather than blind."""
    assert rep["n_varying"] == 17 and rep["n_constant"] == 23
    assert rep["n_fields"] == 40
    varying = {v["field"] for v in rep["varying_fields"]}
    assert "booster_raw_json" in varying and "trained_date" in varying


def test_the_ignored_evidence_is_named_and_out_of_the_projection(rep):
    for f in ("oos_mean_ic", "oos_per_fold_ic", "oos_std_ic"):
        e = rep["evidence_fields"][f]
        assert e["n_distinct"] == 12, f
        assert e["in_projection"] is False, f


# --------------------------------------------- the half that forecloses the easy fix --
def test_the_recorded_evidence_CANNOT_rank_the_boosters(rep):
    """Reporting only 'the gate ignores oos_mean_ic' would invite exactly the wrong
    remedy. At 3 folds the best-worst gap is under one standard error."""
    d = rep["decisiveness"]
    assert d["n_folds_per_artifact"] == 3
    assert d["best_minus_worst_oos_mean_ic"] == pytest.approx(0.01429, abs=1e-4)
    assert d["gap_over_se_max"] < 1.0
    assert "rank on noise" in d["note"]


def test_decisiveness_is_None_when_fold_counts_DIFFER(tmp_path):
    """A gap over SE computed across artifacts with different fold counts would be
    comparing standard errors of different things."""
    arts = {
        "a": {"oos_mean_ic": 0.05, "oos_std_ic": 0.04, "oos_per_fold_ic": [1, 2, 3],
              "kind": "x"},
        "b": {"oos_mean_ic": 0.04, "oos_std_ic": 0.04, "oos_per_fold_ic": [1, 2],
              "kind": "x"},
    }
    assert G.analyse(arts)["decisiveness"] is None


# ------------------------------------------------ the false finding it exists to stop --
def test_the_two_FINGERPRINTS_are_recorded_as_NOT_a_finding(rep):
    """`config_fingerprint` never equals `candidate_recipe_fingerprint` — correct
    behaviour, since they hash different objects. Two names containing 'fingerprint'
    are not one object."""
    n = rep["not_a_finding"]
    assert "config_fingerprint" in n and "candidate_recipe_fingerprint" in n
    assert "CORRECT" in n and "watchlist" in n


def test_the_derived_projection_field_is_declared_not_silently_skipped(rep):
    """`feature_source_contract_keys` is computed inside the gate, not an artifact field.
    Omitting it without saying so would overstate the projection's coverage."""
    assert rep["derived_projection_fields_not_checked"] == [
        "feature_source_contract_keys"]


# ------------------------------------------------------------------------- the method --
def test_boosters_are_keyed_on_the_BYTES_not_any_fingerprint(tmp_path):
    for i, raw in enumerate(["A", "B", "A"]):
        (tmp_path / f"{i}.json").write_text(json.dumps(
            {"booster_raw_json": raw, "config_fingerprint": "same"}))
    assert len(G.distinct_boosters(str(tmp_path / "*.json"))) == 2


def test_an_artifact_without_a_booster_is_skipped(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"config_fingerprint": "x"}))
    (tmp_path / "b.json").write_text("not json")
    assert G.distinct_boosters(str(tmp_path / "*.json")) == {}


def test_fewer_than_two_boosters_SKIPS_with_3(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"booster_raw_json": "A"}))
    assert G.main(["--artifact-glob", str(tmp_path / "*.json")]) == 3


def test_a_projection_field_that_VARIES_exits_0_not_1(tmp_path):
    """The exit code has to distinguish 'the gate discriminates' from 'the gate is
    blind'; a detector that always returns 1 says nothing."""
    for i, k in enumerate(["xgb", "lgbm"]):
        (tmp_path / f"{i}.json").write_text(json.dumps(
            {"booster_raw_json": f"B{i}", "kind": k}))
    assert G.main(["--artifact-glob", str(tmp_path / "*.json")]) == 0
