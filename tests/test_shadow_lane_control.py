"""A shadow lane that equals prod is not a control, and must be named as one.

Fixtures are synthetic. Binding to the live configs would go red the day the
_mom lane is fixed, which is backwards for a regression test.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.shadow_lane_control_probe import (  # noqa: E402
    COPY_OF_PROD, IS_A_CONTROL, UNREADABLE, ProdConfigUnreadable, compare,
    scan, scoring_identity,
)


def _cfg(d: pathlib.Path, name: str, ps: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"ranking": {"panel_scoring": ps}}), encoding="utf-8")


BASE = {"enabled": True, "buy_floor": 0.2, "components": [{"artifact_path": "a.json"}]}


# --- the finding ----------------------------------------------------------

def test_identical_scoring_config_is_a_COPY(tmp_path):
    _cfg(tmp_path, "strategy_config.json", BASE)
    _cfg(tmp_path, "strategy_config.shadow_x.json", dict(BASE))
    r = scan(tmp_path)
    assert r["n_copies_of_prod"] == 1
    assert r["copies_of_prod"] == ["strategy_config.shadow_x.json"]


def test_one_differing_scoring_key_makes_it_a_control(tmp_path):
    _cfg(tmp_path, "strategy_config.json", BASE)
    _cfg(tmp_path, "strategy_config.shadow_x.json", {**BASE, "buy_floor": 0.9})
    assert scan(tmp_path)["n_copies_of_prod"] == 0


def test_differing_ONLY_in_shadow_legs_is_still_a_copy(tmp_path):
    """shadow_experiment / shadow_models are reported alongside a decision, not
    used to compute it. The live _mom lane differs from prod in exactly these
    two and nothing else."""
    _cfg(tmp_path, "strategy_config.json",
         {**BASE, "shadow_experiment": "x", "shadow_models": [{"name": "leg"}]})
    _cfg(tmp_path, "strategy_config.shadow_x.json",
         {**BASE, "shadow_experiment": None, "shadow_models": None})
    assert scan(tmp_path)["n_copies_of_prod"] == 1


# --- commentary must not be mistaken for substance ------------------------

def test_underscore_comment_keys_are_stripped_at_every_level(tmp_path):
    """Recursion matters: stripping only the top level would call two blocks
    differing solely in a NESTED `_reason` a genuine control — a lane declared
    informative on the strength of a comment."""
    _cfg(tmp_path, "strategy_config.json",
         {**BASE, "_why": "a", "sizing": {"floor": 0, "_reason": "prod note"}})
    _cfg(tmp_path, "strategy_config.shadow_x.json",
         {**BASE, "_why": "b", "sizing": {"floor": 0, "_reason": "TOTALLY different note"}})
    assert scan(tmp_path)["n_copies_of_prod"] == 1


def test_nested_substantive_difference_is_still_detected(tmp_path):
    """The anti-vacuity twin of the test above: stripping comments must not
    also blind the probe to a real nested change."""
    _cfg(tmp_path, "strategy_config.json", {**BASE, "sizing": {"floor": 0.0}})
    _cfg(tmp_path, "strategy_config.shadow_x.json", {**BASE, "sizing": {"floor": 0.7}})
    assert scan(tmp_path)["n_copies_of_prod"] == 0


def test_scoring_identity_drops_comments_and_legs():
    out = scoring_identity({"a": 1, "_c": "x", "shadow_models": [1]})
    assert out == {"a": 1}


def test_component_digest_change_is_a_real_difference():
    a = {"components": [{"artifact_path": "p.json", "expected_content_sha256": "sha256:aa"}]}
    b = {"components": [{"artifact_path": "p.json", "expected_content_sha256": "sha256:bb"}]}
    assert compare(a, b)["state"] == IS_A_CONTROL
    assert compare(a, dict(a))["state"] == COPY_OF_PROD


# --- refusals -------------------------------------------------------------

def test_missing_prod_refuses_rather_than_calling_every_lane_a_control(tmp_path):
    _cfg(tmp_path, "strategy_config.shadow_x.json", BASE)
    with pytest.raises(ProdConfigUnreadable):
        scan(tmp_path)


def test_prod_with_empty_panel_scoring_refuses(tmp_path):
    _cfg(tmp_path, "strategy_config.json", {})
    with pytest.raises(ProdConfigUnreadable):
        scan(tmp_path)


def test_unreadable_lane_is_its_own_state_not_a_control(tmp_path):
    _cfg(tmp_path, "strategy_config.json", BASE)
    (tmp_path / "strategy_config.shadow_bad.json").write_text("{nope", encoding="utf-8")
    r = scan(tmp_path)
    assert r["n_unreadable"] == 1
    assert r["lanes"][0]["state"] == UNREADABLE
    assert r["n_copies_of_prod"] == 0


def test_lane_without_panel_scoring_is_unreadable_not_a_copy(tmp_path):
    _cfg(tmp_path, "strategy_config.json", BASE)
    (tmp_path / "strategy_config.shadow_empty.json").write_text(
        json.dumps({"ranking": {}}), encoding="utf-8")
    assert scan(tmp_path)["n_unreadable"] == 1


def test_unreadable_lane_makes_the_cli_exit_nonzero(tmp_path):
    from ops.renquant104.shadow_lane_control_probe import main
    _cfg(tmp_path, "strategy_config.json", BASE)
    (tmp_path / "strategy_config.shadow_bad.json").write_text("{nope", encoding="utf-8")
    assert main(["--configs", str(tmp_path)]) == 1


# --- it must not overclaim ------------------------------------------------

def test_result_refuses_to_call_a_differing_lane_good(tmp_path):
    _cfg(tmp_path, "strategy_config.json", BASE)
    _cfg(tmp_path, "strategy_config.shadow_x.json", {**BASE, "buy_floor": 0.9})
    r = scan(tmp_path)
    assert "necessary" in r["does_NOT_establish"]
    assert "not sufficient" in r["does_NOT_establish"]
