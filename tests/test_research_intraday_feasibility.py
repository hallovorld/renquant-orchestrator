"""Tests for the renquant105 intraday-feasibility PRIORS (no network, no DB).

The study (``scripts/research_intraday_feasibility.py``) trains nothing and reads
nothing -- it computes transparent **parametric priors** (NOT measurement) over published
cost/edge parameters. These tests pin the pure functions to their closed-form values (so
the committed feasibility numbers cannot silently drift), add **dimensional/unit tests that
prevent the round-1 horizon-aliasing bug** (using a 5-min dispersion as if it were the
open->close dispersion), verify the stateful H1 turnover accounting, and confirm the
default run's verdict is **UNDETERMINED** with a non-empty open->close marginal/viable grid
(NOT a "demonstrated NO-GO").
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


# ---- DIMENSIONAL / UNIT tests: prevent horizon aliasing (the verdict-changing bug) ----
def test_open_close_dispersion_is_sqrt_bars_larger_than_5min():
    # The CORE fix: an open->close dispersion is ~sqrt(78) larger than a single 5-min-bar
    # dispersion. Using one value for BOTH (round-1 bug) understated the open->close edge ~9x.
    sig_5m = 25.0
    sig_oc = feas.sigma_open_close_from_5m_bps(sig_5m)
    assert sig_oc == pytest.approx(25.0 * math.sqrt(78), rel=1e-9)
    ratio = sig_oc / sig_5m
    assert ratio == pytest.approx(math.sqrt(78), rel=1e-9)
    assert 8.0 < ratio < 9.5            # ~8.83x -- they are NOT the same number


def test_default_inputs_keep_5min_and_open_close_dispersion_distinct():
    inp = feas.FeasibilityInputs()
    # the two dispersions MUST be different fields with different magnitudes (no aliasing)
    assert inp.sigma_xs_5m_bps == pytest.approx(25.0)
    assert inp.sigma_xs_open_close_bps == pytest.approx(200.0)
    assert inp.sigma_xs_open_close_bps > 5.0 * inp.sigma_xs_5m_bps   # not the same unit
    # the open->close prior is inside a plausible liquid-large-cap band
    assert 150.0 <= inp.sigma_xs_open_close_bps <= 250.0


def test_open_close_edge_uses_dispersion_directly_no_sqrt78_scaling():
    # E[edge] at the open->close horizon uses sigma_oc DIRECTLY. IC=0.05, sigma_oc=200,
    # factor=1.75 -> 17.5 bps (NOT 200*sqrt(78)*... and NOT the 2.19 bps from the 25-bps bug).
    assert feas.expected_top_edge_bps(0.05, 200.0, 1.75) == pytest.approx(17.5)
    # sanity: the bugged 5-min number would have given ~2.19 bps -- ~8x smaller.
    assert feas.expected_top_edge_bps(0.05, 25.0, 1.75) == pytest.approx(2.1875)
    assert feas.expected_top_edge_bps(0.05, 200.0, 1.75) > 5.0 * feas.expected_top_edge_bps(0.05, 25.0, 1.75)


def test_scale_helper_rejects_bad_bar_count():
    with pytest.raises(ValueError):
        feas.sigma_open_close_from_5m_bps(25.0, bars_per_session=0)


# ---- A.2 edge of the top pick: open->close CLEARS cost at realistic IC/dispersion ------
def test_open_close_net_edge_clears_cost_at_realistic_ic_dispersion():
    # at sigma_oc=200, IC=0.05 the open->close top pick clears the 11 bps round trip...
    assert feas.net_edge_bps(0.05, 200.0, 1.75, 11.0) > 0
    # ...and at IC=0.03 it is ~break-even (within a couple bps), NOT "underwater 10x".
    assert -2.0 < feas.net_edge_bps(0.03, 200.0, 1.75, 11.0) < 2.0


def test_required_dispersion_to_clear_matches_codex_125_7_bps():
    # 11/(0.05*1.75) = 125.7 bps is the OPEN->CLOSE dispersion needed to break even at IC 0.05.
    assert feas.required_dispersion_to_clear_bps(11.0, 0.05, 1.75, k=1.0) == pytest.approx(125.71, abs=0.1)
    # ...which is INSIDE the plausible 150-250 bps band -> break-even is reachable.
    assert feas.required_dispersion_to_clear_bps(11.0, 0.05, 1.75, k=1.0) < 200.0


# ---- A.4 Fundamental Law + cost drag --------------------------------------------------
def test_fundamental_law_gross_ir():
    # IR = TC * IC * sqrt(breadth) ; TC=0.5, IC=0.03, breadth=1008 -> ~0.476
    breadth = feas.effective_breadth_per_year(4.0)
    assert breadth == pytest.approx(1008.0)
    assert feas.fundamental_law_gross_ir(0.03, breadth, 0.5) == pytest.approx(0.476, abs=0.01)


def test_cost_drag_is_negative_and_churn_is_worse():
    # one full book rotation/day (open->close) vs a churn-y multi-rotation/day
    open_close = feas.cost_drag_sharpe(11.0, 1.0, 1.0, 0.012)     # 1.0 book turnover/day
    churn = feas.cost_drag_sharpe(11.0, 1.5, 1.0, 0.012)          # 1.5 book turnover/day
    assert open_close < 0 and churn < 0
    assert churn < open_close                                     # more turnover -> more drag


def test_net_sharpe_adds_drag():
    assert feas.net_sharpe(0.48, -1.46) == pytest.approx(-0.98)


def test_honest_net_sharpe_band_uses_ic_band_only_upper_bound_is_minus_0_98():
    # finding 6 (Codex round-3): the HONEST net-Sharpe band must be computed over inp.ic_band
    # ONLY (0.01->0.03). Its UPPER bound = gir(0.03)+drag ~ 0.476 - 1.455 ~ -0.98, NOT -0.66.
    res = feas.run_feasibility()
    lo, hi = res.honest_net_sharpe_band
    assert hi == pytest.approx(-0.98, abs=0.02)     # gir(max(ic_band)=0.03) + drag, NOT IC=0.05
    assert lo == pytest.approx(-1.30, abs=0.02)     # gir(min(ic_band)=0.01) + drag
    assert lo < hi < 0.0
    # the upper bound must NOT have been pulled up to the optimistic IC=0.05 (the round-2 bug)
    assert hi < -0.8                                  # -0.66 (the IC=0.05 ref) would violate this


def test_optimistic_net_sharpe_ref_is_separate_and_is_minus_0_66():
    # the IC=0.05 reference is reported SEPARATELY, NOT folded into the honest band.
    res = feas.run_feasibility()
    assert res.optimistic_net_sharpe_ref == pytest.approx(-0.66, abs=0.02)
    # it is strictly above (less negative than) the honest band's upper bound
    assert res.optimistic_net_sharpe_ref > res.honest_net_sharpe_band[1]


def test_honest_band_upper_bound_is_a_function_of_ic_band_not_0_05():
    # a DIFFERENT honest ic_band must move the honest upper bound (proving 0.05 is not baked in)
    inp = feas.FeasibilityInputs(ic_band=(0.01, 0.015, 0.02))
    res = feas.run_feasibility(inp)
    # honest upper now uses max(ic_band)=0.02, strictly worse than the 0.03 default upper bound
    default_hi = feas.run_feasibility().honest_net_sharpe_band[1]
    assert res.honest_net_sharpe_band[1] < default_hi
    # the optimistic IC=0.05 reference is unchanged (it does not depend on ic_band)
    assert res.optimistic_net_sharpe_ref == pytest.approx(-0.66, abs=0.02)


# ---- H1 trading policy: STATEFUL bounded turnover (finding 4) --------------------------
def test_h1_policy_is_one_round_trip_per_name_per_session():
    pol = feas.H1Policy()
    # bounded open->close: enter once, exit at close, NO re-entry -> exactly 1 RT/name.
    assert pol.round_trips_per_name_per_session() == 1
    assert pol.max_replacements_per_session == 0
    assert pol.one_open_per_name is True
    assert pol.exit_rule == "session_close"
    assert pol.overnight_excluded is True


def test_h1_policy_total_round_trips_from_stateful_path():
    pol = feas.H1Policy()
    # total RT/session = names entered * 1 (NOT asserted rebalances_per_day=1)
    assert pol.round_trips_per_session(4) == 4
    assert pol.round_trips_per_session(0) == 0
    with pytest.raises(ValueError):
        pol.round_trips_per_session(-1)


def test_h1_policy_churn_variant_incurs_more_round_trips():
    # a policy that allows intraday replacements is a churn variant: 1 + replacements
    churny = feas.H1Policy(max_replacements_per_session=3)
    assert churny.round_trips_per_name_per_session() == 4


def test_inputs_book_turnover_is_one_rotation_not_4x_book():
    inp = feas.FeasibilityInputs()
    # 4 names * 0.25 book/name = 1.0 book turnover/day (one rotation), NOT 4x the book
    assert inp.open_close_round_trips_per_day() == pytest.approx(4.0)
    assert inp.open_close_book_turnover_per_day() == pytest.approx(1.0)


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


# ---- end-to-end verdict: UNDETERMINED, marginal/viable open->close grid (NOT NO-GO) ----
def test_default_run_verdict_is_undetermined_not_no_go():
    res = feas.run_feasibility()
    assert "UNDETERMINED" in res.verdict
    assert "NO-GO" not in res.verdict          # the over-claimed verdict must NOT reappear
    assert res.rt_cost_bps == pytest.approx(11.0)


def test_open_close_grid_is_not_all_negative():
    # the verdict-changing result: the corrected open->close grid has MANY positive cells
    # (it was a spurious 0/36 in round 1). At sigma_oc~200 + IC 0.03-0.05 the trade clears cost.
    res = feas.run_feasibility()
    assert res.n_positive_cells > 0
    assert res.n_positive_cells >= 10          # ~14/48 at the committed grid
    # a concrete marginal/viable cell: IC=0.05, sigma_oc=200, RT=11 -> net +6.5 bps
    cell = next(s for s in res.sensitivity
                if s["ic"] == 0.05 and s["sigma_oc_bps"] == 200.0 and s["rt_bps"] == 11.0)
    assert cell["positive"] and cell["net_edge_bps"] == pytest.approx(6.5)


def test_edge_table_clears_cost_at_optimistic_ic():
    res = feas.run_feasibility()
    top = next(c for c in res.edge_table if c["ic"] == 0.05)
    assert top["clears_break_even"]            # IC=0.05 open->close clears the 11 bps cost
    assert top["net_edge_bps"] == pytest.approx(6.5)


def test_verdict_is_a_function_of_inputs_not_hardcoded():
    # an UNFAVORABLE world (tiny dispersion, high cost) classifies the prior as UNFAVORABLE,
    # but it is STILL UNDETERMINED -- the script never "demonstrates" a verdict.
    inp = feas.FeasibilityInputs(
        half_spread_bps=8.5, slippage_bps=4.0, adverse_selection_bps=4.5,   # RT=34 bps
        sigma_xs_open_close_bps=80.0, ic_band=(0.005, 0.01, 0.015))
    res = feas.run_feasibility(inp)
    assert "UNDETERMINED" in res.verdict
    assert "UNFAVORABLE" in res.verdict
    assert res.n_positive_cells >= 0           # grid is over its own fixed sigma_oc range


def test_formatter_prints_undetermined_and_reproduce_command():
    out = feas._fmt(feas.run_feasibility())
    assert "VERDICT: UNDETERMINED" in out
    assert "NO-GO" not in out                  # the over-claim must not be printed
    assert "PARAMETRIC PRIORS, NOT MEASUREMENT" in out
    assert "research_intraday_feasibility.py" in out
    assert "125.7" in out  # the corrected break-even dispersion surfaces in the printed table
    # finding 6: the printed summary must show the HONEST band and the OPTIMISTIC ref DISTINCTLY
    assert "HONEST NET SHARPE BAND" in out
    assert "OPTIMISTIC REFERENCE" in out
    assert "-0.98" in out   # the honest band's UPPER bound (NOT -0.66)
    assert "-0.66" in out   # the SEPARATE optimistic IC=0.05 reference
    # the dispersion band is an ASSUMED SENSITIVITY RANGE, not "realistic", until M0 measures it
    assert "ASSUMED SENSITIVITY RANGE" in out
