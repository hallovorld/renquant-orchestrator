"""Tests for scripts/v6_phase_minus_1_recompute.py's pure helpers.

Network- and data-free (stdlib only): the loader (pandas) and the Monte Carlo
(numpy) are lazy imports inside functions this file never calls. Includes the
S-REL R2 POSITIVE-CONTROL fixture: a planted +30 bps intraday edge on a
synthetic cross-section MUST be detected by the harness's top-k / IC
estimator, and the unplanted null arm must stay clean.
"""
import importlib.util
import math
import os
import random
import sys

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "v6_phase_minus_1_recompute.py",
)
_spec = importlib.util.spec_from_file_location("v6_phase_minus_1_recompute", _SCRIPT)
v6 = importlib.util.module_from_spec(_spec)
sys.modules["v6_phase_minus_1_recompute"] = v6
_spec.loader.exec_module(v6)


# ---------------------------------------------------------------------------
# valid_oc_return
# ---------------------------------------------------------------------------
def test_valid_oc_return_basic():
    assert v6.valid_oc_return(100.0, 101.0) == pytest.approx(0.01)
    assert v6.valid_oc_return(100.0, 100.0) == pytest.approx(0.0)


@pytest.mark.parametrize("o,c", [
    (None, 100.0), (100.0, None), (0.0, 100.0), (-1.0, 100.0), (100.0, 0.0),
    (float("nan"), 100.0), (100.0, float("inf")), ("x", 100.0),
])
def test_valid_oc_return_rejects_bad_legs(o, c):
    assert v6.valid_oc_return(o, c) is None


# ---------------------------------------------------------------------------
# xs_dispersion_bps
# ---------------------------------------------------------------------------
def test_xs_dispersion_none_below_two_names():
    assert v6.xs_dispersion_bps([]) is None
    assert v6.xs_dispersion_bps([0.01]) is None


def test_xs_dispersion_known_vector():
    # returns +/-1%: population std = 1% = 100 bps; MAD = 1% -> *1.4826
    d = v6.xs_dispersion_bps([0.01, -0.01, 0.01, -0.01])
    assert d["breadth"] == 4.0
    assert d["std_bps"] == pytest.approx(100.0)
    assert d["mad_std_bps"] == pytest.approx(100.0 * 1.4826)
    assert d["winsor_std_bps"] == pytest.approx(100.0)  # no clipping below 10%


def test_xs_dispersion_robust_vs_outlier():
    # one absurd print blows up std but not the robust/winsorized estimators
    base = [0.001 * ((i % 5) - 2) for i in range(50)]      # +/-20 bps grid
    spiked = base + [5.0]                                   # a 500x bad print
    clean = v6.xs_dispersion_bps(base)
    spike = v6.xs_dispersion_bps(spiked)
    assert spike["std_bps"] > 10 * clean["std_bps"]
    assert spike["mad_std_bps"] < 2 * clean["mad_std_bps"]
    assert spike["winsor_std_bps"] < spike["std_bps"] / 3


def test_xs_dispersion_gaussian_consistency():
    rng = random.Random(7)
    rs = [rng.gauss(0.0, 0.015) for _ in range(4000)]
    d = v6.xs_dispersion_bps(rs)
    assert d["std_bps"] == pytest.approx(150.0, rel=0.05)
    assert d["mad_std_bps"] == pytest.approx(150.0, rel=0.06)
    assert d["iqr_std_bps"] == pytest.approx(150.0, rel=0.06)


# ---------------------------------------------------------------------------
# breakeven algebra — must reproduce the memo's exact rows
# ---------------------------------------------------------------------------
def test_net_edge_reproduces_memo_rows():
    assert v6.net_edge_bps(0.03, 152.5, 1.0, 11.0) == pytest.approx(-6.425)
    assert v6.net_edge_bps(0.05, 152.5, 1.0, 11.0) == pytest.approx(-3.375)


def test_breakeven_sigma_reproduces_memo():
    assert v6.breakeven_sigma_bps(11.0, 0.03, 1.0) == pytest.approx(366.67, abs=0.01)
    assert v6.breakeven_sigma_bps(11.0, 0.05, 1.0) == pytest.approx(220.0)


def test_breakeven_ic_is_inverse_of_net_edge():
    for sigma in (114.0, 152.5):
        for cost in (11.0, 22.0, 40.0):
            for factor in (1.0, 1.75, 2.34):
                ic_star = v6.breakeven_ic(cost, sigma, factor)
                assert v6.net_edge_bps(ic_star, sigma, factor, cost) == pytest.approx(0.0, abs=1e-9)
                assert v6.net_edge_bps(ic_star * 1.01, sigma, factor, cost) > 0
                assert v6.net_edge_bps(ic_star * 0.99, sigma, factor, cost) < 0


# ---------------------------------------------------------------------------
# top-k / pearson estimator primitives
# ---------------------------------------------------------------------------
def test_top_k_mean_picks_by_signal():
    rets = [0.01, 0.02, 0.03, -0.05]
    sig = [1.0, 3.0, 2.0, 0.0]
    assert v6.top_k_mean(rets, sig, 2) == pytest.approx((0.02 + 0.03) / 2)


def test_pearson_perfect_and_null():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert v6.pearson(xs, [2.0, 4.0, 6.0, 8.0]) == pytest.approx(1.0)
    assert v6.pearson(xs, [-1.0, -2.0, -3.0, -4.0]) == pytest.approx(-1.0)
    assert v6.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert v6.pearson([1.0, 2.0], [1.0, 2.0]) is None


# ---------------------------------------------------------------------------
# POSITIVE CONTROL (S-REL R2) — the committed fixture
# ---------------------------------------------------------------------------
def _synthetic_cross_section(n_dates=400, n_names=142, sigma=0.0150, seed=99):
    rng = random.Random(seed)
    return {f"d{i:04d}": [rng.gauss(0.0, sigma) for _ in range(n_names)]
            for i in range(n_dates)}


def test_positive_control_detects_planted_edge_and_null_stays_clean():
    """A +30 bps planted mean o->c edge (near decision scale: cost floor is 11 bps,
    planted implied IC ~0.06-0.08) MUST fire the detection rule; the unplanted
    null arm on the SAME cross-section must not."""
    rets = _synthetic_cross_section()
    pc = v6.positive_control(rets)
    assert pc["planted_detected"] is True
    assert pc["null_clean"] is True
    assert pc["pass"] is True
    # the planted arm's realized gross must be in the neighborhood of the plant
    assert pc["planted"]["gross_bps"] == pytest.approx(30.0, abs=12.0)
    assert pc["planted"]["net_bps"] > 0
    assert pc["null"]["net_bps"] < 0
    # planted implied IC is near the memo's anchor band, not 10x it (R2 scale rule)
    assert 0.03 < pc["planted"]["mean_ic"] < 0.12


def test_positive_control_zero_plant_is_not_detected():
    """Mechanism-off arm: with plant_bps=0 the detection rule must NOT fire —
    the harness does not hallucinate edge (lambda-round-1 guard)."""
    rets = _synthetic_cross_section(seed=123)
    pc = v6.positive_control(rets, plant_bps=0.0)
    assert pc["planted_detected"] is False
    assert pc["pass"] is False


def test_positive_control_deterministic():
    rets = _synthetic_cross_section(n_dates=60, seed=5)
    a = v6.positive_control(rets)
    b = v6.positive_control(rets)
    assert a["planted"]["gross_bps"] == b["planted"]["gross_bps"]
    assert a["null"]["gross_bps"] == b["null"]["gross_bps"]


# ---------------------------------------------------------------------------
# sensitivity grid
# ---------------------------------------------------------------------------
def test_sensitivity_grid_shape_and_flip_monotonicity():
    rows = v6.sensitivity_grid({"std": 152.5, "mad": 114.0},
                               {"f1": 1.0, "top3": 2.34})
    assert len(rows) == 2 * 2 * 3  # sigma x factor x cost
    for row in rows:
        # net edge strictly increasing in IC at fixed everything else
        nets = [row[f"net_bps_ic_{ic:g}"] for ic in (0.01, 0.03, 0.05, 0.08)]
        assert nets == sorted(nets)
    # breakeven IC doubles when cost doubles (fixed sigma/factor)
    by_cost = {r["cost_bps"]: r["breakeven_ic"] for r in rows
               if r["sigma"] == "std" and r["factor"] == "f1"}
    assert by_cost[22.0] == pytest.approx(2 * by_cost[11.0])
