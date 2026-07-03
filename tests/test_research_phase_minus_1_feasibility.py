"""Pure-function tests for the renquant105 Phase -1 feasibility probe.

These tests DO NOT touch the network (the live Alpaca pull is guarded behind ``__main__`` /
``_run_live`` and is not exercised here). They lock the pre-registered thresholds and the
STOP/GO decision logic so a future edit cannot silently re-tune the gate.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the script as a module (it lives under scripts/, not an importable package).
# Register it in sys.modules BEFORE exec so the dataclass machinery can resolve cls.__module__.
_SPEC_PATH = Path(__file__).resolve().parents[1] / "scripts" / "research_phase_minus_1_feasibility.py"
_spec = importlib.util.spec_from_file_location("phase_minus_1", _SPEC_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules["phase_minus_1"] = mod
_spec.loader.exec_module(mod)  # type: ignore[union-attr]


# --- pre-registered constants are LOCKED (the whole point is no post-hoc tuning) -----------
def test_pinned_thresholds_match_design_doc():
    assert mod.ASSUMED_SIGMA_OC_LO_BPS == 150.0
    assert mod.ASSUMED_SIGMA_OC_HI_BPS == 250.0
    assert mod.GO_MIN_INTRADAY_NAMES == 30
    assert mod.GO_MIN_EFF_BREADTH == 4.0
    assert mod.COST_CONSERVATIVE_LEG_BPS == 17.0
    assert mod.COST_PRIOR_BPS == 11.0
    assert mod.IC_GRID == (0.03, 0.05)


# --- open_close_returns: overnight excluded, invalid legs dropped --------------------------
def test_open_close_returns_basic():
    r = mod.open_close_returns([100.0, 50.0], [110.0, 45.0])
    assert r == pytest.approx([0.10, -0.10])


def test_open_close_returns_drops_invalid_legs():
    # non-positive open, NaN close, None -> all dropped; only the valid pair survives.
    r = mod.open_close_returns([0.0, 100.0, float("nan"), None, 200.0],
                               [10.0, 105.0, 50.0, 5.0, float("nan")])
    assert r == pytest.approx([0.05])


# --- cross_sectional_dispersion_bps -------------------------------------------------------
def test_dispersion_needs_two_names():
    assert mod.cross_sectional_dispersion_bps([0.01]) is None
    assert mod.cross_sectional_dispersion_bps([]) is None


def test_dispersion_std_in_bps():
    # returns +/-1% -> population std = 1% = 100 bps.
    d = mod.cross_sectional_dispersion_bps([0.01, -0.01])
    assert d is not None
    assert d["std_bps"] == pytest.approx(100.0)
    assert d["breadth"] == 2.0


def test_dispersion_robust_estimators_present():
    d = mod.cross_sectional_dispersion_bps([0.0, 0.01, 0.02, -0.01, -0.02])
    assert d is not None
    assert d["robust_mad_std_bps"] > 0
    assert d["robust_iqr_std_bps"] > 0


# --- summarize_distribution / quantiles ---------------------------------------------------
def test_summarize_distribution_quantiles():
    s = mod.summarize_distribution([100.0, 200.0, 300.0, 400.0, 500.0])
    assert s["n"] == 5
    assert s["median"] == pytest.approx(300.0)
    assert s["p25"] == pytest.approx(200.0)
    assert s["p75"] == pytest.approx(400.0)
    assert s["min"] == 100.0 and s["max"] == 500.0


def test_summarize_distribution_empty():
    assert mod.summarize_distribution([])["n"] == 0


def test_effective_breadth_is_median():
    assert mod.effective_breadth([100, 142, 142, 50]) == 121.0
    assert mod.effective_breadth([]) == 0.0


# --- net_edge_band: gross = IC * sigma_oc * factor; net = gross - cost ---------------------
def test_net_edge_band():
    band = mod.net_edge_band_bps(sigma_oc_bps=200.0, cost_bps=11.0)
    assert band["IC=0.03"]["gross_edge_bps"] == pytest.approx(6.0)   # 0.03 * 200 * 1.0
    assert band["IC=0.03"]["net_edge_bps"] == pytest.approx(-5.0)
    assert band["IC=0.05"]["gross_edge_bps"] == pytest.approx(10.0)
    assert band["IC=0.05"]["net_edge_bps"] == pytest.approx(-1.0)


# --- decide(): the PRE-REGISTERED STOP/GO table EXACTLY -----------------------------------
def test_decide_all_pass_is_go():
    v = mod.decide(sigma_oc_median_bps=152.5, n_intraday_names=142, eff_breadth=142.0, cost_bps=11.0)
    assert v.go is True
    assert all(v.criteria.values())


def test_decide_sigma_below_band_is_stop():
    # sigma_oc below 150 -> STOP regardless of the other three (criterion (b) fails).
    v = mod.decide(sigma_oc_median_bps=120.0, n_intraday_names=142, eff_breadth=142.0, cost_bps=11.0)
    assert v.go is False
    assert v.criteria["b_sigma_oc_ge_150bps"] is False


def test_decide_sigma_exactly_at_floor_is_go():
    # The floor is inclusive (">= ~150").
    v = mod.decide(sigma_oc_median_bps=150.0, n_intraday_names=30, eff_breadth=4.0, cost_bps=17.0)
    assert v.criteria["b_sigma_oc_ge_150bps"] is True
    assert v.go is True


def test_decide_thin_coverage_is_stop():
    v = mod.decide(sigma_oc_median_bps=200.0, n_intraday_names=10, eff_breadth=142.0, cost_bps=11.0)
    assert v.go is False
    assert v.criteria["a_intraday_names_ge_30"] is False


def test_decide_thin_breadth_is_stop():
    v = mod.decide(sigma_oc_median_bps=200.0, n_intraday_names=142, eff_breadth=2.0, cost_bps=11.0)
    assert v.go is False
    assert v.criteria["c_eff_breadth_ge_4"] is False


def test_decide_cost_over_cap_is_stop():
    v = mod.decide(sigma_oc_median_bps=200.0, n_intraday_names=142, eff_breadth=142.0, cost_bps=18.0)
    assert v.go is False
    assert v.criteria["d_cost_le_17bps"] is False


def test_decide_unmeasurable_sigma_is_stop():
    v = mod.decide(sigma_oc_median_bps=None, n_intraday_names=142, eff_breadth=142.0, cost_bps=11.0)
    assert v.go is False
    assert v.criteria["b_sigma_oc_ge_150bps"] is False


# --- offline CLI path makes no network call ------------------------------------------------
def test_offline_main_returns_zero(capsys):
    rc = mod.main(["--offline"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Phase -1" in out
    assert "150" in out  # the sigma_oc lower-edge threshold is printed
