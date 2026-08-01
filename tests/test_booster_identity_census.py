"""Distinct learned models hiding behind one admission fingerprint.

The tests target the ways an identity census can be reassuring and wrong: two artifacts
colliding into one identity because something was missing rather than equal, a served
artifact guessed instead of named, and a scope note that lets a byte fact read as a
behavioural one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "booster_identity_census.py"


def _load():
    spec = importlib.util.spec_from_file_location("bic", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


B = _load()


def _art(d, name, booster="tree", fp="RECIPE1", stamped=True, legacy=False):
    body = {"feature_cols": ["a", "b"]}
    if booster is not None:
        body["booster_raw_json"] = booster
    block = {"artifact_usage": {"candidate_recipe_fingerprint": fp}}
    if stamped:
        if legacy:
            body["wf_gate_metadata"] = block
        else:
            body["metadata"] = {"wf_gate_metadata": block}
    else:
        body["config_fingerprint"] = fp
    (d / name).write_text(json.dumps(body), encoding="utf-8")


# --- identity ---------------------------------------------------------------

def test_same_recipe_DIFFERENT_boosters_is_reported_as_a_COLLAPSE(tmp_path):
    _art(tmp_path, "a.json", booster="tree-A")
    _art(tmp_path, "b.json", booster="tree-B")
    rep = B.census(str(tmp_path), "*.json")
    g = rep["collapse_groups"][0]
    assert g["n_artifacts"] == 2 and g["n_distinct_boosters"] == 2


def test_ANTI_VACUITY_identical_boosters_are_ONE_identity(tmp_path):
    """Without this the census could call everything a collapse and prove nothing."""
    _art(tmp_path, "a.json", booster="same")
    _art(tmp_path, "b.json", booster="same")
    assert B.census(str(tmp_path), "*.json")["collapse_groups"][0][
        "n_distinct_boosters"] == 1
    assert B.main(["--root", str(tmp_path)]) == 0


def test_a_MISSING_booster_is_None_not_a_digest_of_emptiness(tmp_path):
    """An artifact with no booster must not collide with one whose booster is empty —
    that collision is the exact failure this tool measures, committed by the tool."""
    assert B.booster_digest({}) is None
    assert B.booster_digest({"booster_raw_json": ""}) == hashlib.sha256(
        b"").hexdigest()


def test_the_fingerprint_SOURCE_is_recorded(tmp_path):
    """Canonical vs legacy vs no-stamp are different provenance, not one string."""
    _art(tmp_path, "a.json")
    _art(tmp_path, "b.json", legacy=True)
    _art(tmp_path, "c.json", stamped=False)
    fps = {r["recipe_fingerprint"] for r in
           B.census(str(tmp_path), "*.json")["artifacts"]}
    assert any("|canonical" in f for f in fps)
    assert any("|legacy" in f for f in fps)
    assert any("no_gate_stamp" in f for f in fps)


def test_a_NON_OBJECT_root_is_UNREADABLE_not_an_artifact(tmp_path):
    (tmp_path / "bad.json").write_text("[]", encoding="utf-8")
    rep = B.census(str(tmp_path), "*.json")
    assert rep["n_artifacts"] == 0 and rep["n_unreadable"] == 1


def test_an_EMPTY_census_exits_2_not_0(tmp_path, capsys):
    """'No subjects' must never read as 'one identity per model'."""
    assert B.main(["--root", str(tmp_path)]) == 2
    assert "no subjects" in capsys.readouterr().err


# --- promotion series -------------------------------------------------------

def test_the_served_artifact_must_be_NAMED_not_guessed(tmp_path):
    _art(tmp_path, "a.json")
    rep = B.census(str(tmp_path), "*.json")
    out = B.promotion_series(rep, "not_here.json")
    assert "never guessed" in out["error"]


def test_staged_candidates_are_compared_to_the_SERVED_booster(tmp_path):
    _art(tmp_path, "panel.json", booster="SERVED")
    _art(tmp_path, "panel.weekly_20260718T110005Z.staging.json", booster="cand-1")
    _art(tmp_path, "panel.weekly_20260719T110005Z.staging.json", booster="cand-2")
    rep = B.census(str(tmp_path), "*.json")
    p = B.promotion_series(rep, "panel.json")
    assert p["n_staged_candidates"] == 2
    assert p["n_distinct_staged_boosters"] == 2
    assert p["n_staged_matching_served"] == 0
    assert [s["date"] for s in p["staged"]] == ["2026-07-18", "2026-07-19"]


def test_a_PROMOTED_candidate_is_detected(tmp_path):
    """Anti-vacuity for the promotion series: if a staged booster IS the served one it
    must say so, or 'nothing was promoted' is unfalsifiable."""
    _art(tmp_path, "panel.json", booster="X")
    _art(tmp_path, "panel.weekly_20260718T110005Z.staging.json", booster="X")
    p = B.promotion_series(B.census(str(tmp_path), "*.json"), "panel.json")
    assert p["n_staged_matching_served"] == 1 and p["staged"][0]["equals_served"]


def test_rollback_series_reports_WHEN_the_booster_changed(tmp_path):
    _art(tmp_path, "panel.json", booster="C")
    for d, b in (("2026-07-16", "A"), ("2026-07-17", "A"), ("2026-07-18", "B")):
        _art(tmp_path, f"panel.weekly_rollback_{d}.json", booster=b)
    p = B.promotion_series(B.census(str(tmp_path), "*.json"), "panel.json")
    assert p["rollback_snapshots"] == 3
    assert p["rollback_booster_changed_on"] == ["2026-07-18"]


def test_the_scope_notes_refuse_the_two_over_readings(tmp_path, capsys):
    """A byte fact must not be readable as a behavioural one, and 'not promoted' must
    not be readable as 'rejected'."""
    _art(tmp_path, "panel.json", booster="X")
    _art(tmp_path, "panel.weekly_20260718T110005Z.staging.json", booster="Y")
    B.main(["--root", str(tmp_path), "--served-artifact", "panel.json"])
    out = capsys.readouterr().out
    assert "does not follow that their predictions differ" in out
    assert "does NOT establish why" in out
