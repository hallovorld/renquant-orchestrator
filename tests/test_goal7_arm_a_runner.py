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
    def test_all_four_conditions_met_certifies_ON_ARM_B(self):
        v = R.evaluate_predicate(arm="B", per_regime=_cell())
        assert v["outcome"] == "CERTIFIED" and v["failed_conditions"] == []
        assert R.certify(v) == "CERTIFIED"

    @pytest.mark.parametrize("kw,failed", [
        ({"n_dates": 29}, "n_dates>=30"),
        ({"mean_ic": -0.01}, "E1>0"),
        ({"placebo_shuffle": 0.05}, "E1>max_shuffle"),
        ({"placebo_shift": 0.05}, "E1>placebo_shift"),
    ])
    def test_each_condition_can_fail_ALONE(self, kw, failed):
        """Anti-vacuity: a predicate whose conditions cannot individually bite
        is one condition wearing four names."""
        v = R.evaluate_predicate(arm="B", per_regime=_cell(**kw))
        assert v["outcome"] == "NOT CERTIFIED"
        assert failed in v["failed_conditions"], v["failed_conditions"]

    def test_the_sample_floor_is_29_vs_30_not_a_soft_bar(self):
        assert R.evaluate_predicate(
            arm="B", per_regime=_cell(n_dates=30))["outcome"] == "CERTIFIED"
        assert R.evaluate_predicate(
            arm="B", per_regime=_cell(n_dates=29))["outcome"] == "NOT CERTIFIED"

    def test_a_missing_regime_or_missing_field_fails_CLOSED(self):
        for per_regime in ({}, {"BEAR": {"mean_ic": 0.9, "n_dates": 99}},
                           {"BULL_CALM": {}}):
            v = R.evaluate_predicate(arm="B", per_regime=per_regime)
            assert v["outcome"] == "NOT CERTIFIED", per_regime

    def test_NOT_CERTIFIED_is_about_the_EVIDENCE_not_the_signal(self):
        """§6, and the correction codex forced on orch#810: a conservative
        predicate can reject a member with E1 > 0."""
        v = R.evaluate_predicate(arm="B", per_regime=_cell(placebo_shuffle=0.05))
        assert v["mean_ic"] > 0 and v["outcome"] == "NOT CERTIFIED"
        assert "NOT a finding that the signal is absent" in v["meaning"]


class TestArmACannotCertify:
    def test_arm_A_never_reports_a_certification_even_when_all_four_hold(self):
        v = R.evaluate_predicate(arm="A", per_regime=_cell())
        assert v["failed_conditions"] == []          # the numbers pass …
        assert v["outcome"] == "EXPLORATORY — NOT A CERTIFICATION"   # … and it still cannot

    def test_certify_REFUSES_on_arm_A(self):
        v = R.evaluate_predicate(arm="A", per_regime=_cell())
        with pytest.raises(R.ArmMisuse, match="cannot certify"):
            R.certify(v)

    def test_an_unknown_arm_is_rejected(self):
        with pytest.raises(ValueError):
            R.evaluate_predicate(arm="C", per_regime=_cell())


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
        """It must orchestrate the gate's reviewed code, not grow a second
        harness — that is how two answers to one question appear."""
        src = Path(R.__file__).read_text(encoding="utf-8")
        for forbidden in ("spearmanr", "np.corrcoef", "def summarize_ic"):
            assert forbidden not in src, forbidden
        assert "regime_diagnostics" in src and "build_regime_series" in src
