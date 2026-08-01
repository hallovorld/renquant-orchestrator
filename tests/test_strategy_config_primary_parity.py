"""Do the strategy-config surfaces agree about which model is PRIMARY?

The tests target the ways a parity check can report agreement that is not there: absent
surfaces counted as agreeing, a broken surface silently excluded, an empty run exiting
clean, and containers guarded with `or {}` — which is not a guard.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "strategy_config_primary_parity.py"


def _load():
    spec = importlib.util.spec_from_file_location("scpp", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


P = _load()


def _cfg(tmp_path, name, kind="xgb", artifact="a.json", shadows=("s1",), enabled=True,
         raw=None):
    body = raw if raw is not None else {
        "ranking": {"panel_scoring": {
            "kind": kind, "enabled": enabled, "artifact_path": artifact,
            "shadow_models": [{"name": n} for n in shadows]}}}
    p = tmp_path / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


# --- the finding ------------------------------------------------------------

def test_a_DIFFERENT_primary_kind_is_a_disagreement(tmp_path):
    rep = P.compare([P.read_surface(_cfg(tmp_path, "a.json", kind="xgb")),
                     P.read_surface(_cfg(tmp_path, "b.json", kind="hf_patchtst"))])
    assert any("kind" in d for d in rep["disagreements"]), rep


def test_the_MIRROR_case_is_named(tmp_path):
    """The shape measured on this machine: each surface's PRIMARY is in the other's
    SHADOWS. Reporting it as merely 'the kind differs' understates it — one surface says
    A decides and B watches, the other says exactly the reverse."""
    a = _cfg(tmp_path, "a.json", kind="xgb", shadows=("hf_patchtst_prev",))
    b = _cfg(tmp_path, "b.json", kind="hf_patchtst", shadows=("xgb_prev",))
    rep = P.compare([P.read_surface(a), P.read_surface(b)])
    assert rep["primary_and_shadow_are_mirrored"] is True


def test_a_DIFFERING_shadow_set_is_a_disagreement_even_when_the_primary_matches(
        tmp_path):
    """Otherwise a lane silently added to or dropped from one surface passes."""
    rep = P.compare([P.read_surface(_cfg(tmp_path, "a.json", shadows=("s1", "s2"))),
                     P.read_surface(_cfg(tmp_path, "b.json", shadows=("s1",)))])
    assert any("shadow_models" in d for d in rep["disagreements"]), rep


def test_ANTI_VACUITY_identical_surfaces_agree(tmp_path):
    """Without this the check could flag everything and prove nothing."""
    rep = P.compare([P.read_surface(_cfg(tmp_path, "a.json")),
                     P.read_surface(_cfg(tmp_path, "b.json"))])
    assert rep["disagreements"] == [] and not rep["primary_and_shadow_are_mirrored"]


# --- ways the check could report false agreement -----------------------------

def test_an_ABSENT_surface_is_not_a_disagreement_and_not_agreement(tmp_path):
    """A surface not deployed here says nothing about the ones that are. It is recorded
    and excluded, never counted either way."""
    rep = P.compare([P.read_surface(_cfg(tmp_path, "a.json")),
                     P.read_surface(str(tmp_path / "nope.json"))])
    assert rep["n_absent"] == 1 and rep["n_read"] == 1
    assert rep["disagreements"] == []


def test_a_BROKEN_surface_makes_the_check_FAIL_not_silently_shrink(tmp_path):
    """Excluding an unreadable surface and reporting 'all agree' is the failure mode
    this whole class of tool keeps committing."""
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    rep = P.compare([P.read_surface(_cfg(tmp_path, "a.json")),
                     P.read_surface(str(tmp_path / "bad.json"))])
    assert rep["n_broken"] == 1
    assert P.main(["--config", _cfg(tmp_path, "c.json"),
                   "--config", str(tmp_path / "bad.json")]) == 1


def test_a_STRING_ranking_container_does_not_CRASH(tmp_path):
    """`(x or {}).get(...)` is not a guard — a non-empty string is truthy. Three tools in
    this repo have now needed that sentence."""
    p = _cfg(tmp_path, "a.json", raw={"ranking": "n/a"})
    r = P.read_surface(p)
    assert r["status"] == "no_panel_scoring" and "str" in r["why"]


def test_a_STRING_panel_scoring_does_not_crash(tmp_path):
    r = P.read_surface(_cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": "x"}}))
    assert r["status"] == "no_panel_scoring" and "str" in r["why"]


def test_a_NON_LIST_shadow_models_is_MALFORMED_not_an_empty_shadow_set(tmp_path):
    """Reporting it as [] would make a corrupt surface agree with a genuinely
    shadow-free one."""
    r = P.read_surface(_cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "shadow_models": "s1"}}}))
    assert r["status"] == "malformed_shadow_models"


def test_a_NON_OBJECT_json_root_is_reported_not_crashed(tmp_path):
    (tmp_path / "a.json").write_text("[]", encoding="utf-8")
    r = P.read_surface(str(tmp_path / "a.json"))
    assert r["status"] == "no_panel_scoring" and "list" in r["why"]


def test_ZERO_readable_surfaces_exits_2_not_0(tmp_path, capsys):
    """'Nothing to compare' must never read as 'they agree'."""
    assert P.main(["--config", str(tmp_path / "gone.json")]) == 2
    assert "no subjects" in capsys.readouterr().err


def test_main_exits_zero_only_when_surfaces_genuinely_agree(tmp_path, capsys):
    assert P.main(["--config", _cfg(tmp_path, "a.json"),
                   "--config", _cfg(tmp_path, "b.json")]) == 0
    assert "all readable surfaces agree" in capsys.readouterr().out


def test_the_report_REFUSES_to_say_which_surface_the_run_reads(tmp_path, capsys):
    """The scope that keeps this honest: asserting authority from a directory layout is
    how 'which copy executes' defects get published as facts."""
    P.main(["--config", _cfg(tmp_path, "a.json", kind="xgb"),
            "--config", _cfg(tmp_path, "b.json", kind="hf_patchtst")])
    assert "does NOT identify which one the daily run reads" in capsys.readouterr().out
