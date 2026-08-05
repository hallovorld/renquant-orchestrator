"""The frozen predicate, and the one misuse the registration names.

`doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md` §6 freezes four
conditions and §3 freezes that Arm A — a RECONSTRUCTION — cannot certify,
whatever its numbers say. Both are transcribed here so a later run cannot
quietly loosen either.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import goal7_arm_a_per_regime_runner as R  # noqa: E402

PREREG = (Path(__file__).resolve().parent.parent / "doc" / "research"
          / "2026-08-05-goal7-momentum-per-regime-prereg.md")


def _cell(**kw):
    base = {"mean_ic": 0.03, "n_dates": 40, "placebo_shuffle": 0.01,
            "placebo_shift": 0.02}
    base.update(kw)
    return {"BULL_CALM": base}


class TestTheFrozenPredicate:
    def test_all_four_conditions_can_be_MET_and_it_still_certifies_nothing(self):
        v = R.evaluate_predicate(_cell())
        assert v["failed_conditions"] == []
        assert v["outcome"] == "EXPLORATORY — NOT A CERTIFICATION"

    @pytest.mark.parametrize("kw,failed", [
        ({"n_dates": 29}, "n_dates>=30"),
        ({"mean_ic": -0.01}, "E1>0"),
        ({"placebo_shuffle": 0.05}, "E1>max_shuffle"),
        ({"placebo_shift": 0.05}, "E1>placebo_shift"),
    ])
    def test_each_condition_can_fail_ALONE(self, kw, failed):
        """Anti-vacuity: a predicate whose conditions cannot individually bite
        is one condition wearing four names."""
        assert failed in R.evaluate_predicate(_cell(**kw))["failed_conditions"]

    def test_the_sample_floor_is_29_vs_30_not_a_soft_bar(self):
        assert R.evaluate_predicate(_cell(n_dates=30))["failed_conditions"] == []
        assert R.evaluate_predicate(_cell(n_dates=29))["failed_conditions"] == \
            ["n_dates>=30"]

    def test_a_missing_regime_or_missing_field_fails_CLOSED(self):
        for per_regime in ({}, {"BEAR": {"mean_ic": 0.9, "n_dates": 99}},
                           {"BULL_CALM": {}}):
            assert R.evaluate_predicate(per_regime)["failed_conditions"], per_regime


class TestArmACannotCertifyByANY_PATH:
    """[codex on orch#816] The first version took an `arm` argument and returned
    CERTIFIED for arm="B" — the frozen §3 distinction undone by passing a
    string, in an Arm-A-named runner, exposed on the CLI."""

    def test_there_is_no_arm_parameter_to_pass(self):
        import inspect

        assert "arm" not in inspect.signature(R.evaluate_predicate).parameters

    def test_the_outcome_is_never_a_certification(self):
        for per_regime in (_cell(), _cell(n_dates=29), {}):
            assert "CERTIF" not in R.evaluate_predicate(per_regime)["outcome"] \
                or R.evaluate_predicate(per_regime)["outcome"].startswith("EXPLORATORY")

    def test_certify_ALWAYS_raises_even_on_a_passing_verdict(self):
        v = R.evaluate_predicate(_cell())
        assert v["failed_conditions"] == []
        with pytest.raises(R.ArmMisuse, match="cannot certify"):
            R.certify(v)

    def test_certify_raises_on_a_hand_built_arm_B_verdict_too(self):
        with pytest.raises(R.ArmMisuse):
            R.certify({"arm": "B", "outcome": "CERTIFIED"})

    def test_the_CLI_exposes_no_arm_flag(self):
        src = Path(R.__file__).read_text(encoding="utf-8")
        assert "--arm" not in src


class TestProvenanceIsENFORCED:
    """[codex on orch#816] The write-up claimed 'built on the gate's own
    statistics' while the runtime accepted any JSON from any source."""

    def _payload(self, producers):
        return {"provenance": {"producers": list(producers)},
                "per_regime": _cell()}

    def test_a_payload_with_NO_provenance_is_refused(self):
        with pytest.raises(R.ProvenanceMissing, match="no `provenance` block"):
            R.require_gate_provenance({"per_regime": _cell()})

    def test_a_payload_missing_ANY_producer_is_refused(self):
        for drop in R.REQUIRED_PRODUCERS:
            rest = [p for p in R.REQUIRED_PRODUCERS if p != drop]
            with pytest.raises(R.ProvenanceMissing, match="does not name"):
                R.require_gate_provenance(self._payload(rest))

    def test_a_fully_attributed_payload_is_accepted(self):
        got = R.require_gate_provenance(self._payload(R.REQUIRED_PRODUCERS))
        assert "BULL_CALM" in got

    def test_a_payload_with_no_per_regime_block_is_refused(self):
        with pytest.raises(R.ProvenanceMissing, match="no `per_regime` block"):
            R.require_gate_provenance(
                {"provenance": {"producers": list(R.REQUIRED_PRODUCERS)}})

    def test_the_required_producers_are_the_gate_helpers(self):
        assert set(R.REQUIRED_PRODUCERS) == {
            "build_regime_series", "regime_diagnostics", "regime_shift_diagnostics"}


class TestItMatchesTheFrozenDocument:
    """A predicate that drifts from its registration is not preregistered."""

    def test_the_constants_are_the_registered_ones(self):
        text = " ".join(PREREG.read_text(encoding="utf-8").split())
        assert R.PRIMARY_REGIME == "BULL_CALM" and "E1(BULL_CALM)" in text
        assert R.MIN_DATES_PRIMARY == 30 and "n_dates(BULL_CALM) ≥ 30" in text
        assert R.N_SHUFFLE_REPS == 5 and "exactly 5 replications" in text
        assert R.GATE_SHIFT_DAYS == 120

    def test_the_worst_case_shuffle_rule_is_the_registered_one(self):
        text = " ".join(PREREG.read_text(encoding="utf-8").split())
        assert "max_k shuffle_ic_k(R)" in text and "the WORST case" in text

    def test_the_module_computes_no_statistic_of_its_own(self):
        """It must not grow a second harness — that is how two answers to one
        question appear. [codex on orch#816] The source scan alone was
        grep-theatre, so the RUNTIME boundary is the provenance refusal tested
        above; this only checks the module did not sprout its own statistics."""
        src = Path(R.__file__).read_text(encoding="utf-8")
        for forbidden in ("spearmanr", "np.corrcoef", "def summarize_ic"):
            assert forbidden not in src, forbidden
