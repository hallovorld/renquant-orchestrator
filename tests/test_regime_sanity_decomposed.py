"""GOAL-6 — the question orch#673 left: is the regime criterion satisfiable at all?

It is. `BEAR` clears the placebo leg on **11 of 11** artifacts with a placebo IC at
**4%** of its real IC. So the criterion is not impossible, and #673's two hypotheses
("the gate is right and the models are bad" / "the gate is mis-specified") are BOTH
wrong.

What actually happens in `BULL_CALM` and `CHOPPY` is that a **60-day-shifted label
out-ranks the aligned one** — median placebo/real of **2.15** and **6.61**. That is a
property of the labels in those regimes, not of the model's skill.
"""

from __future__ import annotations

import csv
import pathlib
import statistics

CSV = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-07-31-regime-sanity-decomposed"
       / "regime_placebo_vs_real.csv")


def _reg(name):
    with CSV.open() as fh:
        return [r for r in csv.DictReader(fh) if r["regime"] == name]


def _median_ratio(rows):
    v = [float(r["placebo_over_real"]) for r in rows if r["placebo_over_real"]]
    return statistics.median(v)


def test_the_criterion_IS_satisfiable():
    """THE answer. Without a regime that passes, 'the models are bad' and 'the gate
    is impossible' would be indistinguishable."""
    bear = _reg("BEAR")
    assert len(bear) == 11
    assert all(r["placebo_leg_ok"] == "True" for r in bear)
    assert _median_ratio(bear) < 0.10


def test_bull_calm_fails_the_PLACEBO_leg_not_the_skill_floor():
    """`min_mean_ic = max(0.0, 0.25*|real_ic|)` — a floor the regime's own IC scales
    with. The failing conjunct is the placebo ceiling, on every artifact."""
    bc = _reg("BULL_CALM")
    assert len(bc) == 11
    assert all(r["placebo_leg_ok"] == "False" for r in bc)
    assert all(float(r["mean_ic"]) > 0 for r in bc)          # positive IC throughout


def test_a_shifted_label_OUT_RANKS_the_aligned_one_in_the_failing_regimes():
    assert _median_ratio(_reg("BULL_CALM")) > 2.0
    assert _median_ratio(_reg("CHOPPY")) > 6.0


def test_the_bar_a_model_would_have_to_clear_by_skill_alone():
    """ceiling = 0.5*|aligned_real_ic|, so passing with the observed placebo needs
    real_ic >= 2*placebo. Measured on the newest artifact that is ~4x today's."""
    newest = [r for r in _reg("BULL_CALM") if "20260730" in r["artifact"]][0]
    need = 2.0 * abs(float(newest["placebo_60_ic"]))
    have = abs(float(newest["aligned_real_ic"]))
    assert need / have > 4.0


def test_exactly_one_artifact_is_the_deployed_one():
    assert sum(1 for r in _reg("BULL_CALM") if r["deployed"] == "True") == 1
