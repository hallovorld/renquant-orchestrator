"""expkit.controls — the mandatory positive-plant + true-null gate."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.expkit.controls import (
    ControlsNotPassedError,
    plant_mean_shift,
    plant_rank_blend,
    run_controls,
    sign_flip_null,
    within_date_permutation_null,
)
from renquant_orchestrator.expkit.verdict import GateDecision, Outcome


def _decision(outcome: Outcome, method: str = "block_bootstrap") -> GateDecision:
    return GateDecision(
        outcome=outcome,
        mechanical_outcome=outcome,
        rule="toy",
        n_dates=100,
        floor_met=True,
        observed_mean=0.0,
        mde=None,
        power={},
        unanimity_go={},
        unanimity_kill={},
        method=method,
        requires_null_control=False,
        controls_ok=True,
    )


def _gate_by_marker(mapping):
    """Fake gate: routes each control input (a string marker) to an outcome."""
    return lambda marker: _decision(*mapping[marker])


# ---------------------------------------------------------------------------
# run_controls semantics
# ---------------------------------------------------------------------------
def test_both_controls_pass():
    gate = _gate_by_marker({"pos": (Outcome.GO,), "null": (Outcome.KILL,)})
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert report.positive.passed and report.null.passed and report.all_passed
    report.raise_if_failed()  # no raise


def test_positive_must_detect():
    gate = _gate_by_marker({"pos": (Outcome.INCONCLUSIVE,), "null": (Outcome.KILL,)})
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert not report.positive.passed
    with pytest.raises(ControlsNotPassedError, match="positive_plant"):
        report.raise_if_failed()


def test_null_must_not_detect():
    gate = _gate_by_marker({"pos": (Outcome.GO,), "null": (Outcome.GO,)})
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert not report.null.passed


def test_null_negative_branch_must_fire_by_default():
    # INCONCLUSIVE on a true null = harness cannot classify a pure null
    gate = _gate_by_marker({"pos": (Outcome.GO,), "null": (Outcome.INCONCLUSIVE,)})
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert not report.null.passed
    # ... unless explicitly waived (documented-reason enforcement lives on the
    # plugin; run_controls exposes the switch)
    report2 = run_controls(
        gate, positive_input="pos", null_input="null", require_negative_branch=False
    )
    assert report2.null.passed


def test_null_null_outcome_counts_as_negative_branch():
    gate = _gate_by_marker({"pos": (Outcome.GO,), "null": (Outcome.NULL,)})
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert report.null.passed


def test_exact_branch_null_passes_on_non_detection():
    # small-n exact branch: INCONCLUSIVE-only power is already encoded, so
    # non-detection suffices
    gate = _gate_by_marker(
        {"pos": (Outcome.GO,), "null": (Outcome.INCONCLUSIVE, "exact")}
    )
    report = run_controls(gate, positive_input="pos", null_input="null")
    assert report.null.passed


def test_report_serializes():
    gate = _gate_by_marker({"pos": (Outcome.GO,), "null": (Outcome.KILL,)})
    d = run_controls(gate, positive_input="pos", null_input="null").to_dict()
    assert d["all_passed"] is True
    assert d["positive"]["kind"] == "positive_plant"
    assert d["null"]["kind"] == "true_null"


# ---------------------------------------------------------------------------
# injection helpers
# ---------------------------------------------------------------------------
def test_plant_mean_shift_is_exact_delta():
    s = pd.Series([0.01, -0.02, 0.03])
    assert np.allclose(plant_mean_shift(s, 0.05) - s, 0.05)


def test_plant_rank_blend_moves_score_toward_label():
    rng = np.random.default_rng(11)
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    names = [f"T{i}" for i in range(40)]
    score = pd.DataFrame(rng.standard_normal((20, 40)), index=dates, columns=names)
    label = pd.DataFrame(rng.standard_normal((20, 40)), index=dates, columns=names)
    planted = plant_rank_blend(score, label, weight=0.5)
    from renquant_orchestrator.expkit.evaluation import spearman

    dt = dates[0]
    ic_before = spearman(score.loc[dt].to_numpy(), label.loc[dt].to_numpy())
    ic_after = spearman(planted.loc[dt].to_numpy(), label.loc[dt].to_numpy())
    assert ic_after > ic_before + 0.2
    # NaN mask of the original score is preserved
    score2 = score.copy()
    score2.iloc[0, 0] = np.nan
    assert np.isnan(plant_rank_blend(score2, label, weight=0.5).iloc[0, 0])
    with pytest.raises(ValueError):
        plant_rank_blend(score, label, weight=1.5)


def test_sign_flip_null_preserves_magnitudes_and_kills_mean():
    rng = np.random.default_rng(12)
    s = pd.Series(rng.standard_normal(2000) * 0.01 + 0.05)
    flipped = sign_flip_null(s, seed=142)
    assert np.allclose(flipped.abs(), s.abs())
    assert abs(flipped.mean()) < 0.01  # mean destroyed
    assert np.array_equal(sign_flip_null(s, seed=142), flipped)  # deterministic


def test_within_date_permutation_preserves_row_multisets():
    rng = np.random.default_rng(13)
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    score = pd.DataFrame(
        rng.standard_normal((5, 30)), index=dates, columns=[f"T{i}" for i in range(30)]
    )
    permuted = within_date_permutation_null(score, seed=778)
    for dt in dates:
        assert sorted(permuted.loc[dt]) == pytest.approx(sorted(score.loc[dt]))
    assert not np.allclose(permuted.to_numpy(), score.to_numpy())
