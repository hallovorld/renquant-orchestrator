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


# ---------------------------------------------------------------------------
# Path resolution: which base does each declared artifact_path resolve against?
# Measured on the pinned surface — three paths, two bases, no single base.
# ---------------------------------------------------------------------------

def _tree(tmp_path, *rels):
    for rel in rels:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")


def test_it_reports_EVERY_base_a_path_resolves_under_not_the_first(tmp_path):
    """Returning the first hit would hide the finding: 'it resolved' conceals WHICH base
    answered, and the whole point is that different paths answer differently."""
    (tmp_path / "b1").mkdir(); (tmp_path / "b2").mkdir()
    _tree(tmp_path, "b1/a.json", "b2/a.json")
    hits = P.resolve_against("a.json", [str(tmp_path / "b1"), str(tmp_path / "b2")])
    assert len(hits) == 2


def test_BASES_DISAGREE_when_one_config_names_paths_under_different_bases(tmp_path):
    """The measured shape: the primary resolves under one base, a shadow under another,
    and no single base resolves both."""
    b1, b2 = tmp_path / "umbrella", tmp_path / "sub"
    _tree(tmp_path, "sub/artifacts/prod/p.json", "umbrella/artifacts/shadow/s.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True,
        "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/shadow/s.json"}]}}})
    pa = P.audit_paths(P.read_surface(cfg), [str(b1), str(b2)])
    assert pa["no_common_base"] is True
    assert pa["single_base_that_resolves_everything"] == []
    assert pa["n_unresolvable"] == 0          # both DO resolve — just not together


def test_ANTI_VACUITY_one_base_resolving_everything_is_not_flagged(tmp_path):
    """Without this the check would flag every config and prove nothing."""
    _tree(tmp_path, "base/artifacts/prod/p.json", "base/artifacts/shadow/s.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/shadow/s.json"}]}}})
    pa = P.audit_paths(P.read_surface(cfg), [str(tmp_path / "base")])
    assert pa["no_common_base"] is False
    assert pa["single_base_that_resolves_everything"] == [str(tmp_path / "base")]


def test_an_UNRESOLVABLE_path_is_distinct_from_a_base_disagreement(tmp_path):
    """Different defects: 'the file is nowhere' vs 'the files are in different places'."""
    _tree(tmp_path, "base/artifacts/prod/p.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/gone/x.json"}]}}})
    pa = P.audit_paths(P.read_surface(cfg), [str(tmp_path / "base")])
    assert pa["n_unresolvable"] == 1
    assert any(e["status"] == "unresolvable" for e in pa["entries"])


def test_path_audit_is_SKIPPED_entirely_when_no_base_is_given(tmp_path, capsys):
    """A resolution check with no bases would report every path unresolvable — an alarm
    manufactured by the absence of an argument."""
    cfg = _cfg(tmp_path, "c.json")
    assert P.main(["--config", cfg]) == 0
    assert "PATHS" not in capsys.readouterr().out


def test_an_EMPTY_INTERSECTION_alone_makes_main_exit_nonzero(tmp_path, capsys):
    """Identity can agree while no single base resolves every path — the exit code must
    reflect both. Renamed from "a base disagreement": differing hit SETS are no longer
    the failure, an empty intersection is `[codex on #694]`."""
    _tree(tmp_path, "sub/artifacts/prod/p.json", "umbrella/artifacts/shadow/s.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/shadow/s.json"}]}}})
    rc = P.main(["--config", cfg, "--base", str(tmp_path / "umbrella"),
                 "--base", str(tmp_path / "sub")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "NO SINGLE BASE" in out


def test_an_ABSOLUTE_artifact_path_is_handled_without_a_base(tmp_path):
    _tree(tmp_path, "x/a.json")
    assert P.resolve_against(str(tmp_path / "x" / "a.json"), []) == [""]
    assert P.resolve_against(str(tmp_path / "x" / "gone.json"), []) == []


# ---------------------------------------------------------------------------
# ROUND 2 — codex on #694: two fail-open paths, both the same shape — silently
# normalising corruption into a value that can MATCH.
# ---------------------------------------------------------------------------

def test_a_MALFORMED_shadow_ENTRY_is_broken_not_an_empty_shadow_list(tmp_path):
    """Measured pre-fix: `[{"name": 7}]` normalised to `[]` and AGREED with a genuinely
    empty shadow list. A corrupt deployed surface read as agreeing."""
    corrupt = _cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x",
        "shadow_models": [{"name": 7}]}}})
    empty = _cfg(tmp_path, "b.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x",
        "shadow_models": []}}})
    r = P.read_surface(corrupt)
    assert r["status"] == "malformed_shadow_models" and "int" in r["why"]
    rep = P.compare([P.read_surface(corrupt), P.read_surface(empty)])
    assert rep["n_broken"] == 1
    assert P.main(["--config", corrupt, "--config", empty]) == 1


def test_a_NON_OBJECT_shadow_entry_is_also_broken(tmp_path):
    r = P.read_surface(_cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x",
        "shadow_models": ["just-a-string"]}}}))
    assert r["status"] == "malformed_shadow_models" and "not an object" in r["why"]


def test_EVERY_malformed_entry_is_reported_not_just_the_first(tmp_path):
    """One repaired entry must not hide the next."""
    r = P.read_surface(_cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x",
        "shadow_models": [{"name": 7}, "str", {"name": None}]}}}))
    assert r["why"].count(";") == 2, r["why"]


def test_a_MISSING_identity_field_is_INCOMPLETE_not_a_comparable_None(tmp_path):
    """Measured pre-fix: two surfaces each missing kind/enabled/artifact_path compared
    as equal `None` values and 'agreed' about who decides."""
    a = _cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "shadow_models": []}}})
    b = _cfg(tmp_path, "b.json", raw={"ranking": {"panel_scoring": {
        "shadow_models": []}}})
    assert P.read_surface(a)["status"] == "incomplete_identity"
    rep = P.compare([P.read_surface(a), P.read_surface(b)])
    assert rep["n_broken"] == 2 and rep["n_read"] == 0
    assert P.main(["--config", a, "--config", b]) == 2   # nothing readable to compare


def test_EACH_identity_field_is_required_individually(tmp_path):
    for drop in ("kind", "enabled", "artifact_path"):
        ps = {"kind": "xgb", "enabled": True, "artifact_path": "x",
              "shadow_models": []}
        ps.pop(drop)
        r = P.read_surface(_cfg(tmp_path, f"{drop}.json",
                                raw={"ranking": {"panel_scoring": ps}}))
        assert r["status"] == "incomplete_identity", drop
        assert drop in r["why"], drop


def test_ANTI_VACUITY_a_complete_surface_with_valid_shadows_still_reads(tmp_path):
    """Without this the new strictness could reject everything and prove nothing."""
    r = P.read_surface(_cfg(tmp_path, "a.json", shadows=("s1", "s2")))
    assert r["status"] == "read" and r["shadow_models"] == ["s1", "s2"]


def test_an_EMPTY_shadow_list_is_still_VALID_when_identity_is_complete(tmp_path):
    """A lane-free config is legitimate; only a corrupt one is broken. The distinction
    has to cut both ways or this is just a stricter alarm."""
    r = P.read_surface(_cfg(tmp_path, "a.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "x",
        "shadow_models": []}}}))
    assert r["status"] == "read" and r["shadow_models"] == []


def test_the_REAL_surfaces_still_read_and_still_disagree():
    """The finding must survive the strictness — if the real configs became 'broken',
    the disagreement would be hidden behind a validation error."""
    import os
    a = "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
    b = ("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/"
         "strategy_config.json")
    if not (os.path.exists(a) and os.path.exists(b)):
        import pytest
        pytest.skip("live surfaces not present on this machine")
    rep = P.compare([P.read_surface(a), P.read_surface(b)])
    assert rep["n_read"] == 2 and rep["n_broken"] == 0
    assert rep["primary_and_shadow_are_mirrored"] is True


def test_a_COMMON_BASE_with_different_hit_sets_is_NOT_a_failure(tmp_path):
    """codex on #694: if the primary resolves under {A, B} and a shadow only under {A},
    the intersection is {A} and the loader can consistently use A. Flagging that would
    condemn a perfectly coherent configuration.

    The duplicate placement is still REPORTED — a path present under two bases is how a
    copy gets edited in the wrong place — but it does not fail.
    """
    a, b = tmp_path / "A", tmp_path / "B"
    _tree(tmp_path, "A/artifacts/prod/p.json", "B/artifacts/prod/p.json",
          "A/artifacts/shadow/s.json")            # shadow exists under A only
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/shadow/s.json"}]}}})
    pa = P.audit_paths(P.read_surface(cfg), [str(a), str(b)])

    assert pa["hit_sets_differ"] is True          # visible …
    assert pa["no_common_base"] is False          # … but NOT a failure
    assert pa["single_base_that_resolves_everything"] == [str(a)]
    assert P.main(["--config", cfg, "--base", str(a), "--base", str(b)]) == 0


def test_the_common_base_case_is_still_PRINTED_as_a_note(tmp_path, capsys):
    """'Not a failure' must not mean 'invisible' — duplicate placement is diagnostic."""
    a, b = tmp_path / "A", tmp_path / "B"
    _tree(tmp_path, "A/artifacts/prod/p.json", "B/artifacts/prod/p.json",
          "A/artifacts/shadow/s.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/shadow/s.json"}]}}})
    P.main(["--config", cfg, "--base", str(a), "--base", str(b)])
    out = capsys.readouterr().out
    assert "reported for visibility only" in out
    assert "NO SINGLE BASE" not in out


def test_an_UNRESOLVABLE_path_still_fails_even_with_a_common_base(tmp_path):
    """The two conditions are independent: a common base for what DOES resolve says
    nothing about a path that resolves nowhere."""
    _tree(tmp_path, "A/artifacts/prod/p.json", "B/artifacts/prod/p.json")
    cfg = _cfg(tmp_path, "c.json", raw={"ranking": {"panel_scoring": {
        "kind": "xgb", "enabled": True, "artifact_path": "artifacts/prod/p.json",
        "shadow_models": [{"name": "s", "artifact_path": "artifacts/gone/x.json"}]}}})
    pa = P.audit_paths(P.read_surface(cfg), [str(tmp_path / "A"), str(tmp_path / "B")])
    assert pa["no_common_base"] is False and pa["n_unresolvable"] == 1
    assert P.main(["--config", cfg, "--base", str(tmp_path / "A"),
                   "--base", str(tmp_path / "B")]) == 1


def test_the_REAL_pinned_config_still_has_an_EMPTY_intersection():
    """The finding must survive the narrowing — if it did not, the narrowing would have
    dissolved the defect rather than sharpened the check."""
    import os
    cfg = "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
    u = "/Users/renhao/git/github/RenQuant"
    if not os.path.exists(cfg):
        import pytest
        pytest.skip("live surface not present on this machine")
    pa = P.audit_paths(P.read_surface(cfg),
                       [u, os.path.join(u, "backtesting", "renquant_104")])
    assert pa["no_common_base"] is True
    assert pa["single_base_that_resolves_everything"] == []
