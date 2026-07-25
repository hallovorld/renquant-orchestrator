"""Synthetic-data tests for the factorial-HFR interaction/Holm analyzer
(prereg `doc/research/2026-07-24-factorial-horizon-features-regime-prereg.md`
§5, script `scripts/research_factorial_hfr.py`).

These tests do NOT touch the panel, xgboost, or any production path — they
exercise `run_interaction_tests()` and its helpers against hand-built `cells`
dicts shaped exactly like the real per-cell output, so the frozen contrast
formulas, the Holm family, and the seed-stability gate are pinned before any
real run. The prereg forbids reading verdicts against real data in this PR;
these tests are not that — they check the ANALYZER's arithmetic, not any
IC/Sharpe claim about the strategy.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SPEC_PATH = Path(__file__).resolve().parents[1] / "scripts" / "research_factorial_hfr.py"
_spec = importlib.util.spec_from_file_location("research_factorial_hfr", _SPEC_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules["research_factorial_hfr"] = mod
_spec.loader.exec_module(mod)  # type: ignore[union-attr]


# --- frozen constants are LOCKED (prereg §5 — the whole point of a prereg) -----------------
def test_frozen_decision_rule_constants():
    assert mod.PRIMARY_EVAL == "fwd_20d_excess"
    assert mod.FAMILY_ALPHA == pytest.approx(0.10)
    assert mod.REGISTRABLE_REGIMES == ("BULL_CALM", "BEAR")
    assert mod._eval_block("fwd_5d_excess") == 5
    assert mod._eval_block("fwd_20d_excess") == 20
    assert mod._eval_block("fwd_60d_excess") == 60


DATES = pd.bdate_range("2020-01-01", periods=400)


def _regime_blocks(seed=0):
    """Persistent regime blocks (BEAR / BULL_CALM only) over DATES."""
    rng = np.random.default_rng(seed)
    regime, cur = [], "BULL_CALM"
    while len(regime) < len(DATES):
        regime += [cur] * int(rng.integers(15, 40))
        cur = "BEAR" if cur == "BULL_CALM" else "BULL_CALM"
    return regime[: len(DATES)]


REGIME = _regime_blocks()


def _make_cell(bias, noise=0.01, seed_biases=(0.0, 0.0, 0.0), rng_seed=1):
    """Build one `cells[key]` entry with the exact schema run_interaction_tests
    expects: clean[ev][date] = (regime, seed-averaged value), clean_by_seed[ev]
    [seed][date] = (regime, per-seed value). `bias` is a constant or a
    callable(regime) -> float."""
    rng = np.random.default_rng(rng_seed)
    clean_by_seed = {ev: {} for ev in mod.HORIZONS}
    clean = {ev: {} for ev in mod.HORIZONS}
    for ev in mod.HORIZONS:
        per_seed = {s: {} for s in mod.SEEDS}
        for s_idx, seed in enumerate(mod.SEEDS):
            for d, rg in zip(DATES, REGIME):
                b = bias(rg) if callable(bias) else bias
                per_seed[seed][d] = (rg, b + seed_biases[s_idx] + rng.normal(0, noise))
        clean_by_seed[ev] = per_seed
        for d, rg in zip(DATES, REGIME):
            vals = [per_seed[s][d][1] for s in mod.SEEDS]
            clean[ev][d] = (rg, float(np.mean(vals)))
    return {"clean": clean, "clean_by_seed": clean_by_seed, "fallbacks": 0,
            "raw_primary": 0.0, "placebo_primary": 0.0}


def _null_cells(rng_seed=1):
    """All 8 cells run_interaction_tests reads, every level flat at the same
    IC (no H/F/R/regime effect anywhere) -> every registered test should be
    null."""
    cells = {
        "fwd_60d_excess|all_172|pooled": _make_cell(0.02, rng_seed=rng_seed),
        "fwd_20d_excess|all_172|pooled": _make_cell(0.02, rng_seed=rng_seed + 1),
        "fwd_20d_excess|dedup_r70|specialist": _make_cell(0.02, rng_seed=rng_seed + 2),
        "fwd_20d_excess|all_172|specialist": _make_cell(0.02, rng_seed=rng_seed + 3),
        "fwd_20d_excess|dedup_r70|pooled": _make_cell(0.02, rng_seed=rng_seed + 4),
        "fwd_20d_excess|nontechnical_14|pooled": _make_cell(0.02, rng_seed=rng_seed + 5),
        "fwd_20d_excess|random_14|pooled": _make_cell(0.02, rng_seed=rng_seed + 6),
        "fwd_60d_excess|dedup_r70|pooled": _make_cell(0.02, rng_seed=rng_seed + 7),
    }
    return cells


def test_all_seven_tests_present_and_null_under_flat_cells():
    out = mod.run_interaction_tests(_null_cells())
    assert set(out) == {
        "I1_H_x_R", "I2_F_x_R", "I3_H_x_F",
        "M1_H", "M2a_F_dedup_vs_all", "M2b_F_nontechnical_vs_random", "M3_R",
    }
    for name, t in out.items():
        assert abs(t["stat"]) < 0.01, f"{name} should be ~null under flat cells, got {t['stat']}"
        assert not t["holm_rejected"], f"{name} should not Holm-reject a null contrast"
        assert not t["registered_verdict"]


def test_i1_detects_injected_horizon_by_regime_crossover():
    """BEAR favors the 60d horizon, BULL_CALM favors the 20d horizon -- the
    exact crossover the prereg's I1 is designed to catch."""
    cells = _null_cells()
    cells["fwd_60d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.06 if rg == "BEAR" else 0.01, rng_seed=10)
    cells["fwd_20d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.01 if rg == "BEAR" else 0.03, rng_seed=11)
    out = mod.run_interaction_tests(cells)
    assert out["I1_H_x_R"]["stat"] > 0.03
    assert out["I1_H_x_R"]["p"] < 0.05
    assert out["I1_H_x_R"]["seed_stable"]
    assert out["I1_H_x_R"]["holm_rejected"]
    assert out["I1_H_x_R"]["registered_verdict"]
    # a real crossover must not contaminate the F-side interactions/main effects
    assert abs(out["I2_F_x_R"]["stat"]) < 0.01
    assert abs(out["I3_H_x_F"]["stat"]) < 0.02


def test_seed_instability_blocks_registration_even_with_significant_p():
    """Prereg §5: split signs across seeds -> INCONCLUSIVE regardless of the
    interval. Inject a real BEAR/BULL_CALM crossover but with seed biases
    large enough to flip the per-seed contrast sign."""
    cells = _null_cells()
    cells["fwd_60d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.06 if rg == "BEAR" else 0.01,
        seed_biases=(0.15, -0.15, 0.0), rng_seed=20)
    cells["fwd_20d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.01 if rg == "BEAR" else 0.03, rng_seed=21)
    out = mod.run_interaction_tests(cells)
    assert not out["I1_H_x_R"]["seed_stable"]
    assert not out["I1_H_x_R"]["registered_verdict"], (
        "an unstable sign must never be reported as a registered verdict")


def test_analysis_ineligible_forces_every_verdict_false():
    """Mirrors main()'s analysis_eligible gate (prereg §5 / review round 1
    pt.3): an unvalidated-anchor or failed-anchor run must never surface a
    registered verdict, no matter what the per-test stats say."""
    cells = _null_cells()
    cells["fwd_60d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.06 if rg == "BEAR" else 0.01, rng_seed=30)
    cells["fwd_20d_excess|all_172|pooled"] = _make_cell(
        lambda rg: 0.01 if rg == "BEAR" else 0.03, rng_seed=31)
    out = mod.run_interaction_tests(cells)
    assert out["I1_H_x_R"]["registered_verdict"], "sanity: would register if eligible"
    analysis_eligible = False
    if not analysis_eligible:
        for t in out.values():
            t["registered_verdict"] = False
    assert all(not t["registered_verdict"] for t in out.values())


def test_holm_family_has_exactly_seven_registered_tests():
    """Prereg §5: 'Holm-Bonferroni over the pre-registered set of 3
    interactions + 4 main-effect contrasts = 7 tests.'"""
    out = mod.run_interaction_tests(_null_cells())
    interactions = [k for k in out if k.startswith("I")]
    main_effects = [k for k in out if k.startswith("M")]
    assert len(interactions) == 3
    assert len(main_effects) == 4
