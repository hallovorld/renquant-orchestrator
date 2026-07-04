"""expkit.stats — carried-mask bootstrap, the automatic small-n refusal, and
multi-seed unanimity."""
from __future__ import annotations

import math

import numpy as np
import pytest

from renquant_orchestrator.expkit.stats import (
    SMALL_N_MIN_USABLE_BLOCKS,
    block_bootstrap_conditional_mean,
    block_bootstrap_diff,
    bootstrap_admissible,
    bootstrap_or_exact,
    exact_block_tail_masses,
    exact_sign_test,
    multi_seed_unanimity,
    summarize_boot,
    usable_blocks,
)

ALPHA = 0.05 / 3


# ---------------------------------------------------------------------------
# carried-mask bootstrap
# ---------------------------------------------------------------------------
def test_bootstrap_deterministic_per_seed():
    rng = np.random.default_rng(7)
    vals = rng.standard_normal(300) * 0.1 + 0.02
    mask = np.ones(300, dtype=bool)
    a = block_bootstrap_conditional_mean(vals, mask, block=20, n_boot=500, seed=42)
    b = block_bootstrap_conditional_mean(vals, mask, block=20, n_boot=500, seed=42)
    c = block_bootstrap_conditional_mean(vals, mask, block=20, n_boot=500, seed=43)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_bootstrap_mean_recovers_signal():
    rng = np.random.default_rng(8)
    vals = rng.standard_normal(1000) * 0.05 + 0.03
    mask = np.ones(1000, dtype=bool)
    means = block_bootstrap_conditional_mean(vals, mask, block=20, n_boot=2000, seed=42)
    assert means.mean() == pytest.approx(vals.mean(), abs=0.005)


def test_bootstrap_carried_mask_averages_in_cell_only():
    # in-cell values are +1, off-cell are -1: any leakage of off-cell values
    # into the conditioned mean would pull resample means below +1.
    vals = np.tile([1.0, -1.0], 200)
    mask = np.tile([True, False], 200)
    means = block_bootstrap_conditional_mean(vals, mask, block=10, n_boot=200, seed=1)
    assert np.allclose(means, 1.0)


def test_bootstrap_degenerate_returns_none():
    assert block_bootstrap_conditional_mean(
        np.ones(5), np.ones(5, bool), block=10, n_boot=10, seed=1
    ) is None  # n <= block
    assert block_bootstrap_conditional_mean(
        np.ones(50), np.zeros(50, bool), block=5, n_boot=10, seed=1
    ) is None  # empty cell


def test_bootstrap_diff_centers_on_cell_minus_all():
    vals = np.tile([1.0, 0.0], 300)
    mask = np.tile([True, False], 300)
    diffs = block_bootstrap_diff(vals, mask, block=10, n_boot=500, seed=2)
    # in-cell mean 1.0, overall mean 0.5 -> paired diff ~0.5 every resample
    assert diffs.mean() == pytest.approx(0.5, abs=0.02)


def test_summarize_boot_bounds_and_none_passthrough():
    assert summarize_boot(None, alpha_one_sided=ALPHA) is None
    means = np.linspace(-1.0, 1.0, 2001)
    s = summarize_boot(means, alpha_one_sided=0.05)
    assert s["lb_one_sided"] == pytest.approx(np.percentile(means, 5.0))
    assert s["ub_one_sided"] == pytest.approx(np.percentile(means, 95.0))
    assert s["ci95_two_sided"][0] == pytest.approx(np.percentile(means, 2.5))
    assert s["n_boot_effective"] == 2001


# ---------------------------------------------------------------------------
# the automatic small-n branch (V3 method note)
# ---------------------------------------------------------------------------
def test_usable_blocks_and_admissibility():
    assert usable_blocks(2241, 60) == 37
    assert bootstrap_admissible(2241, 60)
    # V3's own regime: 8-13 dates against block 13 -> refuse
    assert usable_blocks(13, 13) == 1
    assert not bootstrap_admissible(13, 13)
    # boundary: exactly 4 usable blocks is admissible, 3 is not
    assert bootstrap_admissible(240, 60) and not bootstrap_admissible(239, 60)


def test_small_n_refuses_bootstrap_and_requires_null_control():
    rng = np.random.default_rng(3)
    vals = rng.standard_normal(10) * 0.1
    out = bootstrap_or_exact(
        vals, block=13, n_boot=2000, seeds=(42, 43), alpha_one_sided=ALPHA
    )
    assert out["method"] == "exact"
    assert out["requires_null_control"] is True
    assert "refused" in out["refusal"]
    assert out["exact"].exact
    assert "by_seed" not in out


def test_large_n_uses_bootstrap():
    rng = np.random.default_rng(4)
    vals = rng.standard_normal(600) * 0.1
    out = bootstrap_or_exact(
        vals, block=60, n_boot=200, seeds=(42, 43), alpha_one_sided=ALPHA
    )
    assert out["method"] == "block_bootstrap"
    assert out["requires_null_control"] is False
    assert set(out["by_seed"]) == {"42", "43"}


def test_exact_block_tail_masses_constant_series():
    vals = np.full(6, 0.02)
    out = exact_block_tail_masses(vals, block=3, threshold=0.0)
    assert out.exact and out.method == "exact_block_tail_masses"
    assert out.p_ge_threshold == pytest.approx(1.0)  # every resample mean = 0.02
    assert out.p_le_threshold == pytest.approx(0.0)
    assert out.requires_null_control  # always


def test_exact_block_tail_masses_enumeration_count():
    # n=4, block=2 -> 2 blocks -> 4**2 = 16 tuples, enumerated exactly
    vals = np.array([0.1, -0.1, 0.2, -0.2])
    out = exact_block_tail_masses(vals, block=2, threshold=0.0)
    assert out.n_tuples == 16


def test_exact_block_falls_back_to_sign_test_when_unenumerable():
    rng = np.random.default_rng(5)
    vals = rng.standard_normal(50)  # 50**ceil(50/5) is astronomically large
    out = exact_block_tail_masses(vals, block=5, threshold=0.0)
    assert out.method == "exact_sign_test"
    assert "fallback_reason" in out.detail


def test_exact_methods_agree_on_go_kill_orientation():
    """Regression: the two exact methods define p_ge/p_le with OPPOSITE
    GO/KILL orientation (bootstrap tail mass vs null-hypothesis p-value);
    the oriented go/kill_evidence_p fields must agree in direction."""
    strong_positive = np.full(8, 0.2)
    blocks = exact_block_tail_masses(strong_positive, block=4, threshold=0.0)
    sign = exact_sign_test(strong_positive, threshold=0.0)
    assert blocks.go_evidence_p < 0.05 and sign.go_evidence_p < 0.05
    assert blocks.kill_evidence_p > 0.5 and sign.kill_evidence_p > 0.5
    strong_negative = np.full(8, -0.2)
    blocks = exact_block_tail_masses(strong_negative, block=4, threshold=0.0)
    sign = exact_sign_test(strong_negative, threshold=0.0)
    assert blocks.kill_evidence_p < 0.05 and sign.kill_evidence_p < 0.05
    assert blocks.go_evidence_p > 0.5 and sign.go_evidence_p > 0.5


def test_exact_sign_test_binomial():
    # 5 above / 1 below: P(>=5 of 6 | p=.5) = (6+1)/64
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0, -1.0])
    out = exact_sign_test(vals, threshold=0.0)
    assert out.p_ge_threshold == pytest.approx(7 / 64)
    assert out.detail == {"n_above": 5, "n_below": 1, "n_ties_dropped": 0}
    # ties are dropped
    out2 = exact_sign_test(np.array([0.0, 1.0, 1.0]), threshold=0.0)
    assert out2.detail["n_ties_dropped"] == 1


# ---------------------------------------------------------------------------
# multi-seed unanimity (#264)
# ---------------------------------------------------------------------------
def test_multi_seed_unanimity_states():
    hi = {"lb_one_sided": 0.02}
    lo = {"lb_one_sided": 0.01}
    pred = lambda b: b["lb_one_sided"] > 0.015  # noqa: E731
    u = multi_seed_unanimity({"42": hi, "43": hi}, pred)
    assert u["unanimous_true"] and not u["split"]
    u = multi_seed_unanimity({"42": hi, "43": lo}, pred)
    assert u["split"] and not u["unanimous_true"] and not u["unanimous_false"]
    u = multi_seed_unanimity({"42": lo, "43": lo}, pred)
    assert u["unanimous_false"]


def test_multi_seed_unanimity_none_summary_fails_that_seed():
    pred = lambda b: True  # noqa: E731
    u = multi_seed_unanimity({"42": {"x": 1}, "43": None}, pred)
    assert u["per_seed"] == {"42": True, "43": False}
    assert u["split"]
