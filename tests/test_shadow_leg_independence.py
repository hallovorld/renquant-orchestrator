"""A shadow leg that IS a primary component must not be reported as independent.

Fixtures are synthetic. Binding to the live config would go red the day the
_v0_shadow leg is fixed, which is backwards for a regression test.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.shadow_leg_independence_probe import (  # noqa: E402
    INDEPENDENT, SELF_COMPARISON, UNDECLARED, ConfigUnreadable, identity, scan,
)

LEDGER = "artifacts/momentum/ledger.jsonl"


def _cfg(tmp_path: pathlib.Path, components, legs, extra=None) -> pathlib.Path:
    ps = {"components": components, "shadow_models": legs}
    if extra:
        ps.update(extra)
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps({"ranking": {"panel_scoring": ps}}), encoding="utf-8")
    return p


# --- the finding ----------------------------------------------------------

def test_a_leg_serving_a_primary_component_is_a_SELF_COMPARISON(tmp_path):
    p = _cfg(tmp_path,
             [{"kind": "momentum_residual", "artifact_path": LEDGER}],
             [{"name": "mom_shadow", "kind": "momentum_residual",
               "artifact_path": LEDGER}])
    r = scan(p)
    assert r["n_self_comparisons"] == 1
    assert r["self_comparisons"] == ["mom_shadow"]


def test_identity_ignores_the_fingerprint(tmp_path):
    """THE bug this file exists for. Components declare
    expected_config_fingerprint and shadow legs do not, so requiring it compares
    which fields are filled in — and returns 'independent' for the exact leg
    that is a self-comparison."""
    p = _cfg(tmp_path,
             [{"kind": "momentum_residual", "artifact_path": LEDGER,
               "expected_config_fingerprint": "momentum-v0-fd65"}],
             [{"name": "mom_shadow", "kind": "momentum_residual",
               "artifact_path": LEDGER}])
    assert scan(p)["n_self_comparisons"] == 1


def test_identity_is_kind_and_path_only():
    assert identity({"kind": "x", "artifact_path": "p", "expected_content_sha256": "a"}) \
        == identity({"kind": "x", "artifact_path": "p"})


def test_a_genuinely_different_leg_is_independent(tmp_path):
    p = _cfg(tmp_path,
             [{"kind": "panel_ltr", "artifact_path": "artifacts/prod/a.json"}],
             [{"name": "clf", "kind": "xgb", "artifact_path": "artifacts/shadow/b.json"}])
    r = scan(p)
    assert r["n_self_comparisons"] == 0
    assert r["legs"][0]["state"] == INDEPENDENT


def test_same_path_but_different_kind_is_independent(tmp_path):
    """Two scorers reading one ledger with different kinds are different models;
    calling that a self-comparison would be a false positive."""
    p = _cfg(tmp_path,
             [{"kind": "momentum_residual", "artifact_path": LEDGER}],
             [{"name": "other", "kind": "momentum_fast", "artifact_path": LEDGER}])
    assert scan(p)["n_self_comparisons"] == 0


def test_default_kind_is_panel_ltr_on_both_sides(tmp_path):
    p = _cfg(tmp_path,
             [{"artifact_path": "artifacts/prod/a.json"}],
             [{"name": "same", "artifact_path": "artifacts/prod/a.json"}])
    assert scan(p)["n_self_comparisons"] == 1


# --- the single-artifact (non-blend) primary ------------------------------

def test_a_non_blend_primary_is_still_comparable(tmp_path):
    """Without this, a config that scores from one artifact_path would have zero
    components and every leg would look independent by default."""
    p = _cfg(tmp_path, [], [{"name": "leg", "kind": "panel_ltr",
                             "artifact_path": "artifacts/prod/a.json"}],
             extra={"kind": "panel_ltr", "artifact_path": "artifacts/prod/a.json"})
    assert scan(p)["n_self_comparisons"] == 1


# --- refusals and edges ---------------------------------------------------

def test_leg_with_no_artifact_is_its_own_state(tmp_path):
    p = _cfg(tmp_path, [{"kind": "panel_ltr", "artifact_path": "a.json"}],
             [{"name": "bare", "kind": "panel_ltr"}])
    r = scan(p)
    assert r["legs"][0]["state"] == UNDECLARED
    assert r["n_self_comparisons"] == 0


def test_missing_panel_scoring_refuses(tmp_path):
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps({"ranking": {}}), encoding="utf-8")
    with pytest.raises(ConfigUnreadable):
        scan(p)


def test_unreadable_config_refuses(tmp_path):
    p = tmp_path / "strategy_config.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(ConfigUnreadable):
        scan(p)


def test_no_shadow_models_is_clean_not_a_finding(tmp_path):
    p = _cfg(tmp_path, [{"kind": "panel_ltr", "artifact_path": "a.json"}], [])
    r = scan(p)
    assert r["n_shadow_legs"] == 0
    assert r["n_self_comparisons"] == 0


def test_non_dict_leg_is_skipped_not_fatal(tmp_path):
    p = _cfg(tmp_path, [{"kind": "panel_ltr", "artifact_path": "a.json"}],
             ["not-a-dict", {"name": "ok", "kind": "xgb", "artifact_path": "b.json"}])
    assert scan(p)["n_shadow_legs"] == 1


# --- it must not overclaim ------------------------------------------------

def test_result_refuses_to_rank_the_two_rhos(tmp_path):
    p = _cfg(tmp_path, [{"kind": "momentum_residual", "artifact_path": LEDGER}],
             [{"name": "mom", "kind": "momentum_residual", "artifact_path": LEDGER}])
    r = scan(p)
    assert "must not be ranked against each other" in r["does_NOT_establish"]
    assert "is bad" in r["does_NOT_establish"]

def test_non_utf8_config_refuses(tmp_path):
    p = tmp_path / "strategy_config.json"
    p.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ConfigUnreadable):
        scan(p)

def test_non_utf8_primary_config_makes_the_cli_exit_2_not_crash(tmp_path):
    """A UnicodeDecodeError on the PRIMARY read must land in REFUSING (exit 2),
    not propagate uncaught — an uncaught exception would exit 1, which
    ops_audit reads as a finding, misclassifying a corrupted config as a clean
    result."""
    from ops.renquant104.shadow_leg_independence_probe import main
    p = tmp_path / "strategy_config.json"
    p.write_bytes(b"\xff\xfe\x00\x01")
    assert main(["--config", str(p)]) == 2
