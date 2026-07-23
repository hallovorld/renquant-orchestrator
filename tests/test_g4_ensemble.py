"""GOAL-4 tiered-evaluation harness tests.

Two groups:
1. power.py — the MDE / required-blocks / achieved-power closed forms, checked
   against textbook one-sided z-values (this is the numeric backbone of the
   whole "can we even detect it" argument).
2. harness.py — the controls the frozen spec mandates actually behave:
   * positive control recovers a known injected signal (Tier-0),
   * a null score produces no spurious existence (no false positive),
   * the paired increment fires only when the ensemble genuinely dominates.
3. spec.py — the frozen spec builds, validates R3/R4, and hashes stably.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.expkit.evaluation import fwd_excess
from renquant_orchestrator.g4_ensemble import (
    achieved_power,
    build_spec,
    effective_blocks,
    evaluate_existence,
    evaluate_increment,
    min_detectable_ic,
    positive_control_recovery,
    required_blocks,
)
from renquant_orchestrator.expkit.prereg import load_frozen_spec, write_frozen_spec


# --------------------------------------------------------------------------- #
# 1. power.py — closed forms vs textbook z-values
# --------------------------------------------------------------------------- #

def test_min_detectable_ic_matches_closed_form():
    # (z_.95 + z_.80) = 1.644854 + 0.841621 = 2.486475
    # K=100, sigma=0.10 -> 2.486475 * 0.10 / 10 = 0.02486
    assert min_detectable_ic(100, 0.10) == pytest.approx(0.024865, abs=1e-4)
    # K=10 (the 60d-horizon reality) -> ~0.0786 one-sided
    assert min_detectable_ic(10, 0.10) == pytest.approx(0.078630, abs=1e-4)


def test_min_detectable_ic_degenerate():
    assert min_detectable_ic(0, 0.10) == math.inf


def test_required_blocks_inverts_mde():
    mde = min_detectable_ic(100, 0.10)
    # inverse should return ~100 blocks for that MDE
    assert required_blocks(mde, 0.10) == pytest.approx(100, abs=1)


def test_achieved_power_at_mde_is_target():
    mde = min_detectable_ic(10, 0.10, power=0.80)
    assert achieved_power(10, mde, 0.10) == pytest.approx(0.80, abs=1e-2)


def test_achieved_power_tiny_effect_is_low():
    # a true IC of 0.02 over just 10 blocks is essentially undetectable
    assert achieved_power(10, 0.02, 0.10) < 0.25


def test_effective_blocks_is_non_overlapping_count():
    assert effective_blocks(600, 60) == 10
    assert effective_blocks(600, 5) == 120


# --------------------------------------------------------------------------- #
# synthetic panel
# --------------------------------------------------------------------------- #

def _panel(n_dates=460, n_names=40, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_dates)
    names = [f"T{i:02d}" for i in range(n_names)]
    rets = rng.standard_normal((n_dates, n_names)) * 0.02
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=names
    )
    bench = pd.Series(
        100.0 * np.exp(np.cumsum(rng.standard_normal(n_dates) * 0.01)), index=dates
    )
    return close, bench


def _signal_score(label: pd.DataFrame, rho: float, seed: int) -> pd.DataFrame:
    """score = rho * standardized(label) + sqrt(1-rho^2)*noise (a known-SNR
    predictor built from the realized forward label — a deliberate leak, which
    is exactly what a positive control is)."""
    rng = np.random.default_rng(seed)
    std = label.stack().std() or 1.0
    noise = pd.DataFrame(
        rng.standard_normal(label.shape), index=label.index, columns=label.columns
    )
    return rho * (label / std) + math.sqrt(1 - rho * rho) * noise


# --------------------------------------------------------------------------- #
# 2. harness.py — controls behave
# --------------------------------------------------------------------------- #

def test_positive_control_recovery_detects_known_signal():
    _, _ = _panel()
    # a standalone label frame; recovery injects a rho=0.8 signal into it
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2023-01-02", periods=420)
    names = [f"T{i:02d}" for i in range(40)]
    label = pd.DataFrame(
        rng.standard_normal((420, 40)), index=dates, columns=names
    )
    res = positive_control_recovery(label, rho=0.8, horizon=20, n_boot=400, seed=1)
    assert res.real_ic_mean > 0.5           # strong signal recovered
    assert res.exists is True               # clean CI lower bound > 0
    assert res.clean_boot is not None and res.clean_boot["lb_one_sided"] > 0


def test_existence_fires_on_real_signal():
    close, bench = _panel(seed=1)
    label = fwd_excess(close, bench, 20)
    score = _signal_score(label, rho=0.8, seed=2)
    res = evaluate_existence(score, close, bench, 20, n_boot=400, seed=1)
    assert res.exists is True
    assert res.real_ic_mean > 0.4
    assert res.n_blocks > 0
    assert math.isfinite(res.mde)


def test_existence_no_false_positive_on_null_score():
    close, bench = _panel(seed=5)
    rng = np.random.default_rng(9)
    score = pd.DataFrame(
        rng.standard_normal(close.shape), index=close.index, columns=close.columns
    )
    res = evaluate_existence(score, close, bench, 20, n_boot=400, seed=1)
    # a score independent of the label must not manufacture a clean IC
    assert abs(res.clean_ic_mean) < 0.05


def test_increment_beats_only_on_real_dominance():
    close, bench = _panel(seed=2)
    label = fwd_excess(close, bench, 20)
    strong = _signal_score(label, rho=0.8, seed=10)   # "ensemble"
    weak = _signal_score(label, rho=0.2, seed=11)     # "best single"
    res = evaluate_increment(strong, weak, close, bench, 20, n_boot=400, seed=1)
    assert res.beats_best_single is True
    assert res.delta_mean > 0


def test_increment_no_gain_when_identical():
    close, bench = _panel(seed=3)
    label = fwd_excess(close, bench, 20)
    same = _signal_score(label, rho=0.6, seed=12)
    res = evaluate_increment(same, same, close, bench, 20, n_boot=400, seed=1)
    assert res.beats_best_single is False
    assert res.delta_mean == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 3. spec.py — frozen spec builds, validates, hashes
# --------------------------------------------------------------------------- #

def test_frozen_spec_builds_and_validates():
    spec = build_spec()
    assert spec.experiment_id == "g4-ensemble-2expert-2026-07-23"
    assert spec.family_size_k == 6
    assert spec.alpha_one_sided == pytest.approx(0.05 / 6)
    # R3/R4 invariants were enforced by __post_init__ (would have raised)
    assert spec.criterion("tier1_existence_clean_ic_lb").direction == "gt"
    assert spec.reopening_conditions  # non-empty


def test_frozen_spec_hash_is_stable_and_roundtrips(tmp_path):
    spec = build_spec()
    h1 = spec.sha256()
    assert h1 == build_spec().sha256()          # deterministic
    p = tmp_path / "frozen_spec.json"
    write_frozen_spec(spec, p)
    reloaded = load_frozen_spec(p)
    assert reloaded.sha256() == h1              # round-trips
