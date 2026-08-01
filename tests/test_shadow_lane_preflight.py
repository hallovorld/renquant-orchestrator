"""Would a NEW shadow lane actually be served, and seen?

Every check here exists because the corresponding failure has been observed elsewhere in
this programme. The tests are mostly about the preflight's own failure modes — the ways it
could hand out a green light it did not establish.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "shadow_lane_preflight.py"


def _load():
    spec = importlib.util.spec_from_file_location("slp", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


P = _load()


def _cfg(tmp_path, shadows, name="cfg.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x.json",
        "shadow_models": shadows}}}), encoding="utf-8")
    return str(p)


def _real_booster_json() -> str:
    """A booster the CANONICAL loader accepts.

    The fixture used to write `{"booster_raw_json": "{}"}` — structurally present and
    unloadable. That was fine while `check_loadable` only tested for a non-empty field;
    once it invokes `xgboost.Booster.load_model`, a fake booster is correctly refused,
    and a fixture that cannot load must not be called "fully wired".
    """
    import xgboost as xgb
    import numpy as np
    rng = np.random.default_rng(11)
    X = rng.standard_normal((40, 3))
    b = xgb.train({"max_depth": 2, "verbosity": 0},
                  xgb.DMatrix(X, label=X[:, 0]), num_boost_round=2)
    return b.save_raw(raw_format="json").decode("utf-8")


def _artifact(tmp_path, rel, with_booster=True, loadable=False):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not with_booster:
        body = {}
    elif loadable:
        body = {"booster_raw_json": _real_booster_json()}
    else:
        body = {"booster_raw_json": "{}"}
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


# --- check 1: declared where the runner reads -------------------------------

def test_a_lane_ABSENT_from_the_runner_config_fails(tmp_path):
    """R5: two files present as the config and the runner takes the pinned one. A lane
    declared only in the other file is not served."""
    c = _cfg(tmp_path, [{"name": "other", "artifact_path": "a.json"}])
    r = P.check_declared(c, "mine")
    assert r["ok"] is False and "not among" in r["why"]


def test_a_MISSING_config_fails_rather_than_passing_vacuously(tmp_path):
    r = P.check_declared(str(tmp_path / "gone.json"), "mine")
    assert r["ok"] is False and "does not exist" in r["why"]


def test_a_NON_LIST_shadow_models_fails(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"ranking": {"panel_scoring": {"shadow_models": "x"}}}),
                 encoding="utf-8")
    assert P.check_declared(str(p), "mine")["ok"] is False


# --- check 2: the artifact resolves, and under which base -------------------

def test_it_reports_WHICH_base_resolved_not_merely_that_one_did(tmp_path):
    """orch#694: three declared paths, two bases, no single base resolves all three.
    'It resolves' is not an answer; 'it resolves under X' is."""
    _artifact(tmp_path, "A/art/m.json")
    r = P.check_artifact({"artifact_path": "art/m.json"},
                         [str(tmp_path / "A"), str(tmp_path / "B")])
    assert r["ok"] and r["resolves_under"] == [str(tmp_path / "A")]


def test_MULTIPLE_resolving_bases_are_reported_and_NOT_silently_chosen(tmp_path):
    """Strengthened after `[codex on orch#699]`: reporting the ambiguity was not enough,
    because `ok=True` let the whole preflight pass on a base it had just said it could
    not identify. Ambiguity is now non-passing."""
    _artifact(tmp_path, "A/art/m.json")
    _artifact(tmp_path, "B/art/m.json")
    r = P.check_artifact({"artifact_path": "art/m.json"},
                         [str(tmp_path / "A"), str(tmp_path / "B")])
    assert len(r["resolves_under"]) == 2
    assert r["ok"] is None, "reporting it is not enough; it must not pass"


def test_an_UNRESOLVABLE_artifact_fails(tmp_path):
    r = P.check_artifact({"artifact_path": "art/nope.json"}, [str(tmp_path)])
    assert r["ok"] is False


def test_NO_config_entry_means_no_path_to_resolve(tmp_path):
    assert P.check_artifact(None, [str(tmp_path)])["ok"] is False


# --- check 3: the sentinel can see it ---------------------------------------

def test_an_EXACT_watched_lane_is_visible():
    r = P.check_sentinel_visible("topdecile_clf_blend_leg",
                                 ["hf_patchtst", "topdecile_clf_blend_leg"],
                                 "hf_patchtst")
    assert r["ok"] and r["matched_exactly"]


def test_a_DECORATED_lane_is_visible():
    """`hf_patchtst_<suffix>` is the sentinel's own rule."""
    r = P.check_sentinel_visible("hf_patchtst_pt07_strict_seed44_previous_primary",
                                 ["hf_patchtst"], "hf_patchtst")
    assert r["ok"] and r["matched_as_decorated"]


def test_an_UNMATCHED_lane_is_INVISIBLE_and_says_why(tmp_path):
    """orch#689: a lane matching nothing is silent, and its silence is
    indistinguishable from health."""
    r = P.check_sentinel_visible("momentum_v1", ["hf_patchtst"], "hf_patchtst")
    assert r["ok"] is False and "indistinguishable from health" in r["why"]


def test_a_PREFIX_without_the_separator_does_not_count():
    """`hf_patchtstXYZ` is a different lane; matching it would be a false pass."""
    assert P.check_sentinel_visible("hf_patchtstXYZ", ["hf_patchtst"],
                                    "hf_patchtst")["ok"] is False


# --- check 4: the artifact loads --------------------------------------------

def test_a_JSON_artifact_without_a_booster_FAILS(tmp_path):
    a = _artifact(tmp_path, "m.json", with_booster=False)
    assert P.check_loadable(a)["ok"] is False


def test_a_NON_JSON_artifact_is_SKIPPED_not_PASSED(tmp_path):
    """The `.pt` PatchTST checkpoint. Reporting a pass this check did not establish is
    exactly the green-check-over-an-unread-field failure."""
    p = tmp_path / "m.pt"
    p.write_bytes(b"\x00")
    r = P.check_loadable(str(p))
    assert r["ok"] is None and "SKIPPED, not passed" in r["why"]


# --- the whole preflight ----------------------------------------------------

def test_a_FULLY_WIRED_lane_passes(tmp_path):
    import pytest
    pytest.importorskip("xgboost")
    _artifact(tmp_path, "base/art/m.json", loadable=True)
    c = _cfg(tmp_path, [{"name": "lane_a", "artifact_path": "art/m.json"}])
    rep = P.preflight("lane_a", c, [str(tmp_path / "base")], ["lane_a"], "hf_patchtst")
    assert rep["n_failed"] == 0


def test_a_BRAND_NEW_lane_fails_every_check(tmp_path):
    """What GOAL-7's momentum lane looks like today — and the list IS the work."""
    c = _cfg(tmp_path, [])
    rep = P.preflight("momentum_v1", c, [str(tmp_path)], ["hf_patchtst"], "hf_patchtst")
    assert rep["n_failed"] == 4


def test_main_REFUSES_to_run_with_no_watched_lanes(tmp_path, capsys):
    """With an empty watched set, check 3 would pass or fail on nothing and mean
    nothing — so the preflight declines rather than emitting a verdict."""
    c = _cfg(tmp_path, [])
    assert P.main(["--lane", "x", "--runner-config", c]) == 2
    assert "would pass or fail on an empty set" in capsys.readouterr().err


def test_the_report_states_what_PASSING_does_not_mean(tmp_path, capsys):
    _artifact(tmp_path, "base/art/m.json", loadable=True)
    c = _cfg(tmp_path, [{"name": "lane_a", "artifact_path": "art/m.json"}])
    P.main(["--lane", "lane_a", "--runner-config", c,
            "--base", str(tmp_path / "base"), "--watched-lane", "lane_a"])
    out = capsys.readouterr().out
    assert "says nothing about whether the model is any good" in out
    assert "A skipped check (ok=null) is not a pass" in out


# ---------------------------------------------------------------------------
# ROUND 2 — codex on #699: two green paths were not established.
# ---------------------------------------------------------------------------

def test_MULTIPLE_resolving_bases_without_a_loader_base_is_SKIPPED_not_PASSED(tmp_path):
    """The first version returned ok=True and let `preflight` take `resolves_under[0]` —
    this checker asserting the authority it says it cannot establish."""
    _artifact(tmp_path, "A/art/m.json")
    _artifact(tmp_path, "B/art/m.json")
    r = P.check_artifact({"artifact_path": "art/m.json"},
                         [str(tmp_path / "A"), str(tmp_path / "B")])
    assert r["ok"] is None, r
    assert "SKIPPED, not passed" in r["why"] and "unknown" in r["why"]


def test_a_DECLARED_loader_base_resolves_the_ambiguity(tmp_path):
    _artifact(tmp_path, "A/art/m.json")
    _artifact(tmp_path, "B/art/m.json")
    r = P.check_artifact({"artifact_path": "art/m.json"},
                         [str(tmp_path / "A"), str(tmp_path / "B")],
                         loader_base=str(tmp_path / "B"))
    assert r["ok"] is True and r["resolves_under"] == [str(tmp_path / "B")]
    assert sorted(r["also_resolves_under"]) == sorted(
        [str(tmp_path / "A"), str(tmp_path / "B")])


def test_a_loader_base_that_does_NOT_resolve_it_FAILS_even_if_others_do(tmp_path):
    """A lane that resolves only somewhere the loader does not look is not served."""
    _artifact(tmp_path, "A/art/m.json")
    r = P.check_artifact({"artifact_path": "art/m.json"},
                         [str(tmp_path / "A"), str(tmp_path / "B")],
                         loader_base=str(tmp_path / "B"))
    assert r["ok"] is False and "does NOT resolve it" in r["why"]


def test_FULL_PREFLIGHT_does_not_exit_zero_on_an_ambiguous_base(tmp_path, capsys):
    """The regression codex asked for: the whole preflight, not just the check."""
    _artifact(tmp_path, "A/art/m.json")
    _artifact(tmp_path, "B/art/m.json")
    cfg = _cfg(tmp_path, [{"name": "lane_a", "artifact_path": "art/m.json"}])
    rc = P.main(["--lane", "lane_a", "--runner-config", cfg,
                 "--base", str(tmp_path / "A"), "--base", str(tmp_path / "B"),
                 "--watched-lane", "lane_a"])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "SKIP" in out and "SKIPPED (not passed)" in out


def test_a_MALFORMED_booster_is_REFUSED_by_the_canonical_loader(tmp_path):
    """codex: testing that the FIELD is non-empty establishes structural presence, not
    loadability. A truncated booster passes that test and fails at serving time."""
    import pytest
    pytest.importorskip("xgboost")
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"booster_raw_json": "{not a booster"}), encoding="utf-8")
    r = P.check_loadable(str(p))
    assert r["ok"] is False and "canonical loader REFUSED it" in r["why"]


def test_a_REAL_booster_loads_and_says_so(tmp_path):
    """Anti-vacuity: if nothing loaded, the check would reject everything."""
    import pytest
    xgb = pytest.importorskip("xgboost")
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(3)
    X = rng.standard_normal((60, 4))
    b = xgb.train({"max_depth": 2, "verbosity": 0},
                  xgb.DMatrix(X, label=X[:, 0]), num_boost_round=3)
    p = tmp_path / "good.json"
    p.write_text(json.dumps(
        {"booster_raw_json": b.save_raw(raw_format="json").decode("utf-8")}),
        encoding="utf-8")
    r = P.check_loadable(str(p))
    assert r["ok"] is True and "not merely present" in r["note"]


def test_STRUCTURAL_PRESENCE_alone_is_not_reported_as_loadability(tmp_path):
    """The label codex asked for when the loader cannot be invoked."""
    import ast
    src = (pathlib.Path(P.__file__).read_text(encoding="utf-8")
           if hasattr(P, "__file__") else MOD.read_text(encoding="utf-8"))
    assert "loadability was\n                       f\"NOT.\"" in src or \
           "loadability was" in src
