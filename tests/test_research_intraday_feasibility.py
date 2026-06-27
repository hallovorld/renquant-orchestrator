"""Tests for the reproducible renquant105 intraday-feasibility study (no network, no DB).

The study (``scripts/research_intraday_feasibility.py``) trains nothing and reads
nothing -- it is a transparent cost-vs-edge accounting identity over published
parameters. These tests pin the pure functions to their closed-form values (so the
committed feasibility numbers cannot silently drift), verify the arithmetic Codex
flagged on PR #198 (``11/(0.05*1.75) = 125.7 bps``, NOT 3.6%), check the
cost-clearing-horizon scaling model, and confirm the default run still prints NO-GO.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research_intraday_feasibility.py"
_spec = importlib.util.spec_from_file_location("intraday_feas", _SCRIPT)
feas = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass field-type resolution (which reads
# sys.modules[cls.__module__].__dict__) succeeds for the `tuple`-typed defaults.
sys.modules[_spec.name] = feas
_spec.loader.exec_module(feas)


# ---- A.1 round-trip cost --------------------------------------------------------------
def test_round_trip_cost_is_two_legs_plus_impact():
    # per-leg 5.5 -> RT 11.0 (the committed base placeholder)
    assert feas.round_trip_cost_bps(2.5, 1.5, 1.5) == pytest.approx(11.0)
    # impact is added once, not per leg
    assert feas.round_trip_cost_bps(2.5, 1.5, 1.5, impact_bps=2.0) == pytest.approx(13.0)


def test_square_root_impact_is_negligible_at_account_size():
    # $5k notional vs $2B ADV, 2% daily vol -> sub-bp
    imp = feas.square_root_impact_bps(5000.0, 2.0e9, 0.02)
    assert 0.0 < imp < 1.0


def test_square_root_impact_rejects_nonpositive_adv():
    with pytest.raises(ValueError):
        feas.square_root_impact_bps(5000.0, 0.0, 0.02)


# ---- A.2 edge of the top pick ---------------------------------------------------------
def test_expected_top_edge_identity():
    # E[edge] = IC * sigma_xs * factor ; IC=0.05, sigma=25, factor=1.75 -> 2.1875
    assert feas.expected_top_edge_bps(0.05, 25.0, 1.75) == pytest.approx(2.1875)
    # honest-band IC ~ 1 bp single-bar edge
    assert feas.expected_top_edge_bps(0.02, 25.0, 1.75) == pytest.approx(0.875)


def test_net_edge_is_underwater_at_plausible_ic():
    # at any IC in the honest band, single-horizon net edge is deeply negative vs RT=11
    for ic in (0.01, 0.02, 0.03, 0.05):
        assert feas.net_edge_bps(ic, 25.0, 1.75, 11.0) < -8.0


# ---- the arithmetic Codex flagged -----------------------------------------------------
def test_required_cumulative_dispersion_matches_codex_125_7_bps():
    # Codex: 11/(0.05*1.75) = 125.7 bps (NOT 3.6%). This is the break-even (k=1) cum disp.
    assert feas.required_cumulative_dispersion_bps(11.0, 0.05, 1.75, k=1.0) == pytest.approx(125.71, abs=0.1)


def test_doc_3p6pct_2p5day_claim_is_the_ic0p03_k1p75_cell():
    # The doc's under-derived "~3.6% / ~2.5-day" = the IC=0.03, k=1.75 cell:
    cum = feas.required_cumulative_dispersion_bps(11.0, 0.03, 1.75, k=1.75)
    assert cum == pytest.approx(366.7, abs=1.0)          # 3.67%
    h = feas.cost_clearing_horizon_bars(11.0, 0.03, 25.0, 1.75, k=1.75)
    assert h / feas.BARS_PER_SESSION_5MIN == pytest.approx(2.76, abs=0.05)   # ~2.76 days


def test_cost_clearing_horizon_scaling_model():
    # sqrt-of-h scaling: h = [k*RT / (ic*factor*sigma)]^2 ; and sigma_cum(h)=sigma*sqrt(h)
    h = feas.cost_clearing_horizon_bars(11.0, 0.05, 25.0, 1.75, k=1.0)
    assert h == pytest.approx(25.29, abs=0.1)            # 25.3 bars
    # cross-check: sigma_cum at that h equals the required cumulative dispersion
    sigma_cum = 25.0 * math.sqrt(h)
    assert sigma_cum == pytest.approx(feas.required_cumulative_dispersion_bps(11.0, 0.05, 1.75, k=1.0), abs=0.5)


def test_single_open_close_horizon_is_one_session():
    assert feas.BARS_PER_SESSION_5MIN == 78
    # one open->close = one session = 1.0 day; the honest-band hold is MULTI-day -> not intraday
    days_03 = feas.cost_clearing_horizon_bars(11.0, 0.03, 25.0, 1.75, k=1.75) / feas.BARS_PER_SESSION_5MIN
    assert days_03 > 1.0


# ---- A.4 Fundamental Law + cost drag --------------------------------------------------
def test_fundamental_law_gross_ir():
    # IR = TC * IC * sqrt(breadth) ; TC=0.5, IC=0.03, breadth=1008 -> ~0.476
    breadth = feas.effective_breadth_per_year(4.0)
    assert breadth == pytest.approx(1008.0)
    assert feas.fundamental_law_gross_ir(0.03, breadth, 0.5) == pytest.approx(0.476, abs=0.01)


def test_cost_drag_is_negative_and_churn_is_worse():
    open_close = feas.cost_drag_sharpe(11.0, 1.0, 1.0, 0.012)
    churn = feas.cost_drag_sharpe(11.0, 6.0, 1.0, 0.012)
    assert open_close < 0 and churn < 0
    assert churn < open_close                     # 6x rebalances -> 6x the drag
    assert churn == pytest.approx(6.0 * open_close)


def test_net_sharpe_adds_drag():
    assert feas.net_sharpe(0.48, -1.46) == pytest.approx(-0.98)


# ---- block bootstrap ------------------------------------------------------------------
def test_block_bootstrap_recovers_mean_and_brackets_it():
    rng = __import__("numpy").random.default_rng(1)
    sample = rng.normal(0.5, 1.0, size=400).tolist()
    mean, lo, hi = feas.block_bootstrap_mean_ci(sample, block=5, n_boot=1000, seed=2)
    assert lo < mean < hi
    assert mean == pytest.approx(sum(sample) / len(sample))


def test_block_bootstrap_validates_block_size():
    with pytest.raises(ValueError):
        feas.block_bootstrap_mean_ci([1.0, 2.0, 3.0], block=10)
    with pytest.raises(ValueError):
        feas.block_bootstrap_mean_ci([], block=1)


# ---- end-to-end verdict ---------------------------------------------------------------
def test_default_run_is_no_go():
    res = feas.run_feasibility()
    assert res.verdict == "NO-GO"
    assert res.rt_cost_bps == pytest.approx(11.0)
    # net-Sharpe band centered negative at the primary open->close horizon
    assert (res.net_sharpe_band[0] + res.net_sharpe_band[1]) / 2.0 < 0
    # no positive-net cell anywhere in the honest IC<=0.05 sensitivity grid
    assert not any(s["positive"] for s in res.sensitivity)


def test_go_only_if_some_cell_clears_and_band_positive():
    # an (unrealistic) high-IC, low-cost, low-churn world should flip to GO -- proves the
    # verdict is a function of the inputs, not hard-coded.
    inp = feas.FeasibilityInputs(
        half_spread_bps=0.5, slippage_bps=0.0, adverse_selection_bps=0.0,  # RT=1.0 bps
        sigma_xs_bps=200.0, ic_band=(0.10, 0.15, 0.20),
        rebalances_per_day=1.0, independent_bets_per_day=20.0, k_hurdle=1.5)
    res = feas.run_feasibility(inp)
    assert res.verdict == "GO"


def test_formatter_prints_verdict_and_reproduce_command():
    out = feas._fmt(feas.run_feasibility())
    assert "VERDICT: NO-GO" in out
    assert "research_intraday_feasibility.py" in out
    assert "125.7" in out  # the corrected arithmetic surfaces in the printed horizon table
