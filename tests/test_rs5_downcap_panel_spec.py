"""Consistency/completeness tests for the RS-5 down-cap panel preregistration.

Guards against the exact class of bug Codex found in review round 3: a prior
round corrected Section 2's fallback-authority rule, but Section 5 (a
different part of the same prose doc) still carried the old, contradictory
asymmetric rule. These tests assert the prose doc and the machine-readable
prereg_contract.json agree on every binding decision, and that the contract
itself declares every field the review named as required.
"""
from __future__ import annotations

import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_DOC = os.path.join(
    REPO_ROOT, "doc/design/2026-07-02-rs5-downcap-panel-spec.md")
CONTRACT_PATH = os.path.join(
    REPO_ROOT,
    "doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json",
)


def _load_contract() -> dict:
    with open(CONTRACT_PATH) as f:
        return json.load(f)


def _load_spec_text() -> str:
    with open(SPEC_DOC) as f:
        return f.read()


def test_contract_file_exists_and_is_valid_json():
    assert os.path.exists(CONTRACT_PATH)
    contract = _load_contract()
    assert isinstance(contract, dict)
    assert contract["schema_version"] == 1


def test_no_stale_fallback_asymmetry_language_in_prose():
    """The exact bug this round fixes: a stale sentence in one section
    claiming a fallback NO-GO IS decision-grade, contradicting the corrected
    rule elsewhere in the same document."""
    text = _load_spec_text()
    stale_patterns = [
        r"only a fallback NO-GO is decision-grade",
        r"only.{0,20}fallback.{0,20}NO-GO.{0,20}decision-grade",
    ]
    for pattern in stale_patterns:
        assert not re.search(pattern, text, re.IGNORECASE), (
            f"stale asymmetric fallback rule still present, matching: {pattern!r}")


def test_fallback_authority_matches_between_contract_and_prose():
    contract = _load_contract()
    assert contract["survivorship_and_delisting"]["fallback_panel_may_gate_d3"] is False
    assert contract["verdict_logic"]["d3_consequence"]["fallback_panel_any_result"] == (
        "never_authorizes_d3_pipeline_feasibility_and_procurement_gate_only")
    assert contract["admissibility"]["fallback_panel_gating"] == (
        "never_admissible_pipeline_feasibility_only")

    text = _load_spec_text()
    # The prose must assert BOTH GO and NO-GO lack D3 authority under fallback
    # — not the old GO-only-excluded asymmetric framing.
    assert re.search(
        r"NEITHER a GO NOR a NO-GO computed on the fallback panel is\s*\n?"
        r"decision-grade, and NEITHER may feed D3",
        text,
    ), "prose does not state the symmetric no-authority rule for the fallback panel"


def test_economic_gate_is_long_only_not_ls():
    contract = _load_contract()
    gate_b = contract["verdict_logic"]["gate_b_net_return_round_2_corrected"]
    assert gate_b["construction"] == "long_only_top_decile_minus_benchmark_spy"
    assert gate_b["ls_zero_borrow_fee_sharpe"] == (
        "demoted_to_diagnostic_only_not_gating_round_2_correction")

    text = _load_spec_text()
    assert "DEMOTED to a FACTOR-DIAGNOSTIC metric only" in text
    assert "the zero-borrow-fee L/S Sharpe cannot gate D3" in text


def test_regime_diagnostics_are_non_gating():
    contract = _load_contract()
    gate_c = contract["verdict_logic"]["gate_c_regime_robustness_round_2_split"]
    assert gate_c["c1_largest_regime_cell_removed"]["gates"] is False
    assert gate_c["c1_largest_regime_cell_removed"]["role"] == "exploratory_diagnostic_only"
    # c2/c3 are pure calendar-time splits, independent of the contaminated
    # regime labels, and DO gate — this is intentional, not a bug.
    assert gate_c["c2_two_half_stability"]["gates"] is True
    assert gate_c["c3_yearly_breakdown"]["gates"] is True
    assert contract["admissibility"]["regime_conditioned_checks"] == (
        "diagnostic_only_not_admissible_for_gating_round_2_correction")


def test_delisting_policy_enum_and_sensitivity_present():
    contract = _load_contract()
    policy = contract["survivorship_and_delisting"]["delisting_return_policy"]
    assert "priority_1" in policy
    assert "priority_2_bankruptcy_liquidation_delinquency" in policy
    assert policy["priority_2_bankruptcy_liquidation_delinquency"] == (
        "minus_100_percent_terminal_return_from_last_trading_date")
    assert "priority_3_if_neither_rigorous" in policy
    assert "inadmissible" in policy["priority_3_if_neither_rigorous"]
    assert "sensitivity_of_verdict_to_minus_100_convention" in policy["mandatory_reporting"]


def test_multiplicity_and_factor_family_declared():
    contract = _load_contract()
    families = contract["factor_families"]
    assert set(families["multiplicity_family"]) == {"MOM", "REV", "VAL", "QUAL"}
    assert families["family_size_k"] == 4
    bootstrap = contract["bootstrap"]
    assert bootstrap["multiplicity_correction"] == "bonferroni"
    assert bootstrap["multiplicity_k"] == 4


def test_bootstrap_methodology_declared():
    contract = _load_contract()
    bootstrap = contract["bootstrap"]
    assert bootstrap["method"] == "moving_block_bootstrap"
    assert bootstrap["block_size_sessions"] == 60
    assert bootstrap["seeds"] == [42, 43, 44]
    assert bootstrap["one_sided_ci_level"] == 0.9875


def test_frozen_thresholds_declared():
    contract = _load_contract()
    gate_a = contract["verdict_logic"]["gate_a_net_relevant_placebo_clean_ic"]
    assert gate_a["point_estimate_threshold"] == 0.02
    gate_b = contract["verdict_logic"]["gate_b_net_return_round_2_corrected"]
    assert gate_b["annualized_net_sharpe_point_estimate_threshold"] == 0.5


def test_admissibility_rules_declared():
    contract = _load_contract()
    admissibility = contract["admissibility"]
    assert admissibility["primary_panel_required_for_gating"] is True
    floors = admissibility["sample_floors"]
    assert floors["min_pooled_clean_decision_dates"] == 600
    assert floors["min_names_per_date_cross_section"] == 200


def test_d3_authority_declared():
    contract = _load_contract()
    d3 = contract["verdict_logic"]["d3_consequence"]
    assert "go" in d3
    assert "no_go_or_miss" in d3
    assert "fallback_panel_any_result" in d3


def test_c3_status_is_unadjudicated_not_settled():
    """Regression guard for the doc-wide sweep: C3 must never be cited as a
    settled MISS or any other decided prior anywhere in this prose doc."""
    text = _load_spec_text()
    assert "UNADJUDICATED" in text
    assert not re.search(r"C3['’]?s?\s+MISS\b", text), (
        "C3 still cited as a settled MISS somewhere in the doc")
