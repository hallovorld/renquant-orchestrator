#!/usr/bin/env python3
"""Reproducible feasibility analysis for renquant105 intraday alpha (READ-ONLY).

Why this script exists (Codex PR #198 review, finding 1)
--------------------------------------------------------
The load-bearing economic verdict of the renquant105 design suite -- "intraday-alpha
trading is likely NOT VIABLE at this size on this data" -- was asserted in
``doc/design/2026-06-27-renquant105-intraday-system.md`` (§A) with hand-computed
numbers and no committed, runnable derivation. Codex (correctly) rejected an unbacked
assertion and flagged the arithmetic: the doc's "~3.6% cumulative dispersion / ~2.5-day
hold" was under-derived, and ``11 / (0.05*1.75)`` is ``125.7 bps``, not ``3.6%``.

This module is that derivation. It is PURE, OFFLINE, and READ-ONLY:

* every feasibility number is computed from an explicit formula with documented units;
* a sensitivity grid sweeps ``IC x sigma_xs x round_trip_cost``;
* a block-bootstrap function gives an uncertainty band whenever a *measured*
  per-bar/per-day dispersion or cost sample is supplied (none is committed yet, so the
  default run states its inputs are ASSUMPTIONS, not measurements);
* it trains nothing, fetches nothing, and touches no production path. It only prints.

It does NOT soften the verdict. With the honest priors it still prints ``NO-GO``. The
contribution is that the verdict is now *reproducible from a committed artifact* rather
than asserted -- exactly what Codex asked for.

This repo orchestrates; it does not implement model/signal internals. Nothing here is a
model -- it is a transparent cost-vs-edge accounting identity over published parameters.

Reproduce
---------
::

    /Users/renhao/git/github/RenQuant/.venv/bin/python \
        scripts/research_intraday_feasibility.py

(any Python 3.10+ with numpy works; no other dependency, no network, no DB).

Parameter provenance / units
----------------------------
* ``round_trip_cost`` bps -- 2 * (half_spread + slippage + IEX adverse-selection);
  liquid large-cap on Alpaca free IEX. ASSUMPTION band 7-17 bps until M0/M1 commit a
  MEASURED arrival/quote/fill distribution by ticker x time-of-day x order type
  (Codex finding 5). The committed default is the *placeholder* base 11 bps -- the
  script's whole point is that the verdict must survive replacing it with measurement.
* ``sigma_xs`` bps -- single-bar (open->close-leg-equivalent at the chosen horizon)
  cross-sectional dispersion of name returns. ASSUMPTION 25 bps; M1 replaces it with a
  measured per-horizon dispersion from the M0 panel.
* ``ic`` -- out-of-sample rank IC at the *trading horizon* (open->close per Codex
  finding 2). Honest band 0.01-0.03 (= 1/2 in-sample minus the leakage floor).
* ``factor`` -- conditional-mean multiplier of the selected (top) bucket vs the
  cross-section sigma; ``E[ret | top bucket] = factor * sigma_xs``. 1.75 ~ the mean of
  a top-decile truncated standard normal (E[Z | Z>1.2816] ~ 1.75).
* ``transfer_coeff`` -- Fundamental-Law transfer coefficient (implementation shortfall
  of the paper signal into the realized book). 0.5.

The cost-clearing-horizon model and its independence assumption are stated explicitly
in ``cost_clearing_horizon`` below -- this is the piece Codex flagged as under-derived.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

BARS_PER_SESSION_5MIN = 78  # 6.5h RTH / 5min; the open->close horizon = 1 session = 78 bars


# --------------------------------------------------------------------------------------
# Pure feasibility functions (each is a documented identity with units; all unit-tested)
# --------------------------------------------------------------------------------------
def round_trip_cost_bps(half_spread_bps: float, slippage_bps: float,
                        adverse_selection_bps: float, impact_bps: float = 0.0) -> float:
    """Round-trip cost in bps: ``RT = 2*(half_spread + slippage + adverse_sel) + impact``.

    Two legs (entry + exit) each pay half-spread + slippage + IEX adverse selection;
    market impact is added once (it is size-, not leg-, driven). At this account size
    impact ~ 0 (see ``square_root_impact_bps``), so the default is 0.
    """
    per_leg = half_spread_bps + slippage_bps + adverse_selection_bps
    return 2.0 * per_leg + impact_bps


def square_root_impact_bps(notional_usd: float, adv_usd: float, daily_vol: float,
                           y: float = 1.0) -> float:
    """Almgren square-root market impact in bps: ``I = Y * sigma * sqrt(Q/ADV)``.

    ``daily_vol`` is the asset's daily return stdev (fraction, e.g. 0.02). Returns bps.
    At ``$1k-7.5k`` notional vs ``$300M-$40B`` ADV this is < 1 bp -- a non-constraint.
    """
    if adv_usd <= 0:
        raise ValueError("adv_usd must be positive")
    return y * daily_vol * math.sqrt(notional_usd / adv_usd) * 1e4


def expected_top_edge_bps(ic: float, sigma_xs_bps: float, factor: float) -> float:
    """Expected single-horizon edge of the top-ranked pick: ``E[edge] = IC * sigma_xs * factor``.

    Standard linear-forecast identity: a rank-IC ``ic`` forecast captures ``ic`` of the
    cross-sectional dispersion ``sigma_xs``; the selected (top) bucket sits ``factor``
    sigmas into the conditional mean. Units: bps in, bps out.
    """
    return ic * sigma_xs_bps * factor


def net_edge_bps(ic: float, sigma_xs_bps: float, factor: float, rt_cost_bps: float) -> float:
    """Net single-horizon edge after one round trip: ``gross_edge - RT``. bps."""
    return expected_top_edge_bps(ic, sigma_xs_bps, factor) - rt_cost_bps


def required_cumulative_dispersion_bps(rt_cost_bps: float, ic: float, factor: float,
                                       k: float = 1.0) -> float:
    """Cumulative cross-sectional dispersion needed to clear ``k * RT``.

    From ``E[edge] = ic * factor * sigma_cum >= k * RT`` solve for ``sigma_cum``::

        sigma_cum >= (k * RT) / (ic * factor)

    This is the number Codex computed: at ``ic=0.05, factor=1.75, RT=11, k=1`` it is
    ``11/(0.05*1.75) = 125.7 bps`` (NOT 3.6%). bps in, bps out.
    """
    return (k * rt_cost_bps) / (ic * factor)


def cost_clearing_horizon_bars(rt_cost_bps: float, ic: float, sigma_xs_bps: float,
                               factor: float, k: float = 1.0) -> float:
    """Horizon (in bars) over which the accumulated edge clears ``k * RT``.

    SCALING MODEL (made explicit -- this is the piece Codex flagged as under-derived):
    we assume the per-bar SIGNED return increments of a held name are approximately
    serially UNCORRELATED, so cross-sectional dispersion of the *cumulative* return over
    ``h`` bars grows like a random walk::

        sigma_cum(h) = sigma_xs * sqrt(h)               (iid-increments assumption)

    and we hold the rank-IC of the cumulative-h label roughly constant across the small
    intraday-horizon range considered (a conservative simplification -- empirically IC
    tends to DECAY with horizon, which only makes the required hold LONGER, i.e. worse).

    Setting ``ic * factor * sigma_xs * sqrt(h) >= k * RT`` and solving::

        sqrt(h) >= (k * RT) / (ic * factor * sigma_xs)
        h       >= [ (k * RT) / (ic * factor * sigma_xs) ] ** 2

    Returns ``h`` in bars (continuous). The independence assumption is the load-bearing
    simplification and is stated as such; with positive autocorrelation ``h`` shrinks,
    with mean reversion it grows. ``bars -> days`` via ``BARS_PER_SESSION_5MIN``.
    """
    sqrt_h = (k * rt_cost_bps) / (ic * factor * sigma_xs_bps)
    return sqrt_h ** 2


def fundamental_law_gross_ir(ic: float, breadth_per_year: float,
                             transfer_coeff: float = 1.0) -> float:
    """Grinold-Kahn Fundamental Law (annualized): ``IR = TC * IC * sqrt(breadth)``.

    ``breadth_per_year`` = number of approximately-INDEPENDENT bets per year. For an
    intraday book this is NOT (names * rebalances): overlapping intraday labels and the
    same-time-of-day autocorrelation (Heston-Korajczyk-Sadka) collapse N_eff to a few
    independent bets/day. We pass the EFFECTIVE breadth, not the raw count -- see
    ``effective_breadth_per_year``.
    """
    return transfer_coeff * ic * math.sqrt(breadth_per_year)


def effective_breadth_per_year(independent_bets_per_day: float,
                               sessions_per_year: float = 252.0) -> float:
    """Effective annual breadth = independent bets/day * trading days/year.

    The honest input is independent BETS, not order count: ~3-6 independent
    cross-sectional bets per session after deflating for overlap + intraday
    autocorrelation. The naive (names * rebalances/day) count is rejected.
    """
    return independent_bets_per_day * sessions_per_year


def cost_drag_sharpe(rt_cost_bps: float, rebalances_per_day: float,
                     turnover_fraction: float, daily_return_vol: float,
                     sessions_per_year: float = 252.0) -> float:
    """Annualized Sharpe DRAG from paying round-trip cost on turnover.

    Daily cost as a fraction of equity::

        daily_cost = (rt_cost_bps / 1e4) * rebalances_per_day * turnover_fraction

    Annualized Sharpe drag = ``-daily_cost / daily_return_vol * sqrt(sessions/year)``.
    ``turnover_fraction`` = fraction of book turned over per rebalance (1.0 = full).
    Returns a NEGATIVE number (a drag). This replaces the doc's bare "Sharpe -5 to -7"
    assertion with an explicit identity over (cost, rebalances, turnover, vol).
    """
    daily_cost = (rt_cost_bps / 1e4) * rebalances_per_day * turnover_fraction
    return -(daily_cost / daily_return_vol) * math.sqrt(sessions_per_year)


def net_sharpe(gross_ir: float, drag: float) -> float:
    """Net Sharpe = transferred gross IR + cost drag (drag is already negative)."""
    return gross_ir + drag


def block_bootstrap_mean_ci(sample: Sequence[float], block: int = 5,
                            n_boot: int = 2000, alpha: float = 0.05,
                            seed: int = 0) -> tuple[float, float, float]:
    """Moving-block bootstrap CI for the mean of a dependence-carrying sample.

    Intraday per-bar/per-day net-edge observations are serially dependent (overlapping
    labels + intraday autocorrelation), so an iid bootstrap understates the interval.
    We resample contiguous blocks of length ``block`` (Kunsch 1989) to preserve local
    dependence. Returns ``(mean, lo, hi)`` for the ``1-alpha`` CI. Used ONLY where a
    MEASURED sample is supplied; with assumptions there is no sample to bootstrap.
    """
    x = np.asarray(sample, dtype=float)
    n = x.size
    if n == 0:
        raise ValueError("empty sample")
    if block < 1 or block > n:
        raise ValueError("block must be in [1, len(sample)]")
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts_max = n - block + 1
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, starts_max, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = x[idx].mean()
    lo, hi = np.quantile(means, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(x.mean()), float(lo), float(hi)


# --------------------------------------------------------------------------------------
# Scenario container + verdict
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FeasibilityInputs:
    """All feasibility inputs in ONE place, with units. Defaults = the committed priors.

    Every default is an ASSUMPTION (band noted) until M0/M1 commits the measured value.
    """
    # cost (bps) -- base scenario; band 7-17
    half_spread_bps: float = 2.5
    slippage_bps: float = 1.5
    adverse_selection_bps: float = 1.5     # IEX off-NBBO adverse selection, per leg
    # per leg = 5.5 -> RT = 11.0 (the committed base placeholder)
    # cross-section
    sigma_xs_bps: float = 25.0             # single-(open->close)-horizon dispersion
    factor: float = 1.75                   # top-bucket conditional-mean multiplier
    # forecast
    ic_band: tuple[float, float, float] = (0.01, 0.02, 0.03)   # honest OOS band
    transfer_coeff: float = 0.5
    # turnover / breadth
    rebalances_per_day: float = 6.0
    turnover_fraction: float = 1.0
    independent_bets_per_day: float = 4.0  # N_eff after overlap deflation (3-6)
    daily_return_vol: float = 0.012        # ~19% annualized; 104 book order of magnitude
    k_hurdle: float = 1.75                 # admission hurdle: net must clear k*RT

    def round_trip_cost_bps(self) -> float:
        return round_trip_cost_bps(self.half_spread_bps, self.slippage_bps,
                                   self.adverse_selection_bps)


@dataclass
class FeasibilityResult:
    inputs: FeasibilityInputs
    rt_cost_bps: float
    impact_bps: float
    edge_table: list[dict] = field(default_factory=list)         # per-IC single-bar edge
    horizon_table: list[dict] = field(default_factory=list)      # cost-clearing horizon
    net_sharpe_band: tuple[float, float] = (0.0, 0.0)
    drag_open_close: float = 0.0
    drag_churn: float = 0.0
    sensitivity: list[dict] = field(default_factory=list)
    verdict: str = ""


def run_feasibility(inp: FeasibilityInputs | None = None) -> FeasibilityResult:
    """Compute the full feasibility picture from ``inp`` (defaults = committed priors)."""
    inp = inp or FeasibilityInputs()
    rt = inp.round_trip_cost_bps()
    # impact at this account size (illustrative liquid large-cap)
    impact = square_root_impact_bps(notional_usd=5000.0, adv_usd=2.0e9, daily_vol=0.02)

    # A.2 single-(open->close)-horizon edge vs cost, per IC in the honest band (+0.05 ref)
    edge_table = []
    for ic in (*inp.ic_band, 0.05):
        gross = expected_top_edge_bps(ic, inp.sigma_xs_bps, inp.factor)
        edge_table.append({
            "ic": ic,
            "gross_edge_bps": gross,
            "rt_cost_bps": rt,
            "net_edge_bps": gross - rt,
            "clears_hurdle": (gross - rt) > (inp.k_hurdle - 1.0) * rt,
        })

    # cost-clearing horizon: bars/days to accumulate edge = k*RT (break-even k=1 + hurdle)
    horizon_table = []
    for ic in (*inp.ic_band, 0.05):
        for k in (1.0, inp.k_hurdle):
            h = cost_clearing_horizon_bars(rt, ic, inp.sigma_xs_bps, inp.factor, k=k)
            horizon_table.append({
                "ic": ic, "k": k,
                "req_cum_dispersion_bps": required_cumulative_dispersion_bps(rt, ic, inp.factor, k),
                "horizon_bars": h,
                "horizon_days": h / BARS_PER_SESSION_5MIN,
            })

    # A.4 net Sharpe via the Fundamental Law +/- cost drag, over the IC band.
    # Two cost regimes: the PRIMARY open->close horizon (1 round-trip/day) and the
    # rejected intra-session-CHURN variant (rebalances_per_day round-trips). Standardizing
    # on open->close (Codex finding 2) means the relevant cost drag is the 1-rebalance one;
    # the churn drag is shown to demonstrate why multi-rebalance intraday is hopeless.
    breadth = effective_breadth_per_year(inp.independent_bets_per_day)
    drag_open_close = cost_drag_sharpe(rt, 1.0, inp.turnover_fraction, inp.daily_return_vol)
    drag_churn = cost_drag_sharpe(rt, inp.rebalances_per_day, inp.turnover_fraction,
                                  inp.daily_return_vol)
    # net-Sharpe band at the PRIMARY (open->close) horizon, over the honest IC band (+0.05 ref)
    net_lo = net_sharpe(fundamental_law_gross_ir(min(inp.ic_band), breadth, inp.transfer_coeff),
                        drag_open_close)
    net_hi = net_sharpe(fundamental_law_gross_ir(max((*inp.ic_band, 0.05)), breadth, inp.transfer_coeff),
                        drag_open_close)
    net_band = (round(net_lo, 2), round(net_hi, 2))

    # sensitivity grid: IC x sigma_xs x RT -> net single-horizon edge sign
    sensitivity = []
    for ic in (0.01, 0.02, 0.03, 0.05):
        for sig in (15.0, 25.0, 40.0):
            for rt_s in (7.0, 11.0, 17.0):
                ne = net_edge_bps(ic, sig, inp.factor, rt_s)
                sensitivity.append({"ic": ic, "sigma_xs_bps": sig, "rt_bps": rt_s,
                                    "net_edge_bps": ne, "positive": ne > 0})

    # verdict: GO only if SOME plausible cell in the honest band clears the hurdle at a
    # single intraday horizon AND the net-Sharpe band is centered positive.
    any_single_horizon_go = any(
        c["clears_hurdle"] for c in edge_table if c["ic"] in inp.ic_band)
    band_centered_positive = (net_band[0] + net_band[1]) / 2.0 > 0.0
    go = any_single_horizon_go and band_centered_positive
    verdict = "GO" if go else "NO-GO"

    return FeasibilityResult(
        inputs=inp, rt_cost_bps=rt, impact_bps=impact, edge_table=edge_table,
        horizon_table=horizon_table, net_sharpe_band=net_band,
        drag_open_close=round(drag_open_close, 2), drag_churn=round(drag_churn, 2),
        sensitivity=sensitivity, verdict=verdict)


def _fmt(res: FeasibilityResult) -> str:
    inp = res.inputs
    L = []
    L.append("renquant105 intraday-alpha feasibility (reproducible; READ-ONLY; no network)")
    L.append("=" * 78)
    L.append("Primary horizon: OPEN->CLOSE (intraday-only; overnight excluded).")
    L.append("Inputs are ASSUMPTIONS (bands noted) until M0/M1 commit MEASURED values.")
    L.append("")
    L.append("A.1 Round-trip cost (bps)")
    L.append(f"  per-leg = half_spread {inp.half_spread_bps} + slippage {inp.slippage_bps}"
             f" + IEX_adverse_sel {inp.adverse_selection_bps} = "
             f"{inp.half_spread_bps + inp.slippage_bps + inp.adverse_selection_bps}")
    L.append(f"  RT = 2*per_leg + impact = {res.rt_cost_bps:.1f} bps "
             f"(band 7-17; impact {res.impact_bps:.3f} bps -> negligible)")
    L.append("")
    L.append("A.2 Single-horizon edge of the TOP pick vs cost  (E[edge]=IC*sigma_xs*factor)")
    L.append(f"  sigma_xs={inp.sigma_xs_bps} bps  factor={inp.factor}  hurdle k={inp.k_hurdle}xRT")
    L.append("  IC     gross_edge   net(-RT)   clears k*RT?")
    for c in res.edge_table:
        L.append(f"  {c['ic']:<5}  {c['gross_edge_bps']:8.2f}  {c['net_edge_bps']:9.2f}    "
                 f"{'YES' if c['clears_hurdle'] else 'no'}")
    L.append("")
    L.append("A.2b Cost-clearing horizon  (sigma_cum(h)=sigma_xs*sqrt(h), iid-increments)")
    L.append("  required: ic*factor*sigma_xs*sqrt(h) >= k*RT")
    L.append("  IC     k       req_cum_disp   horizon(bars)   horizon(days, 78 bars/sess)")
    for r in res.horizon_table:
        L.append(f"  {r['ic']:<5}  {r['k']:<5}  {r['req_cum_dispersion_bps']:9.1f} bps  "
                 f"{r['horizon_bars']:11.1f}     {r['horizon_days']:.2f}")
    L.append("  NOTE: a single open->close horizon is 1 session = 78 bars (1.0 day).")
    L.append("  Clearing the 1.75x hurdle at the honest-band IC (0.01-0.03) needs a")
    L.append("  MULTI-DAY hold -- i.e. it is no longer intraday. (Corrects the doc's")
    L.append("  under-derived '~3.6%/2.5-day': 3.67% cum-dispersion / 2.76 days is the")
    L.append("  IC=0.03, k=1.75 cell below, now derived from the explicit scaling model.)")
    L.append("")
    L.append("A.4 Net Sharpe (Fundamental Law +/- cost drag)")
    breadth = effective_breadth_per_year(inp.independent_bets_per_day)
    L.append(f"  effective breadth = {inp.independent_bets_per_day}/day * 252 = {breadth:.0f} bets/yr"
             " (independent bets after overlap deflation, NOT names*rebalances)")
    L.append(f"  transferred gross IR (TC*IC*sqrt(breadth)), IC band {inp.ic_band}+0.05:")
    for ic in (*inp.ic_band, 0.05):
        L.append(f"    IC={ic}: {fundamental_law_gross_ir(ic, breadth, inp.transfer_coeff):.2f}")
    L.append(f"  cost drag (Sharpe), turnover {inp.turnover_fraction}, vol {inp.daily_return_vol}:")
    L.append(f"    PRIMARY open->close (1 round-trip/day):  {res.drag_open_close:.2f}")
    L.append(f"    rejected intra-session churn ({inp.rebalances_per_day:.0f}/day): {res.drag_churn:.2f}")
    L.append(f"  => NET SHARPE BAND at the PRIMARY open->close horizon: "
             f"{res.net_sharpe_band[0]} to {res.net_sharpe_band[1]} "
             f"(centered {'POSITIVE' if sum(res.net_sharpe_band)/2>0 else 'NEGATIVE'})")
    L.append("    (the churn variant's drag alone is catastrophic -> intra-session")
    L.append("     multi-rebalance is rejected; only a single open->close round-trip is")
    L.append("     even worth testing, and its net band is still centered negative.)")
    L.append("")
    L.append("A.3 Sensitivity grid (net single-horizon edge sign; IC x sigma_xs x RT)")
    n_pos = sum(1 for s in res.sensitivity if s["positive"])
    L.append(f"  {n_pos}/{len(res.sensitivity)} cells have positive net single-horizon edge.")
    L.append("  Positive cells (the ONLY regions where a single-bar intraday trade clears cost):")
    pos = [s for s in res.sensitivity if s["positive"]]
    if pos:
        for s in pos:
            L.append(f"    IC={s['ic']} sigma_xs={s['sigma_xs_bps']} RT={s['rt_bps']} "
                     f"-> net {s['net_edge_bps']:+.2f} bps")
    else:
        L.append("    (none in the honest IC<=0.05 band -- every single-horizon cell is net-negative)")
    L.append("")
    L.append("=" * 78)
    L.append(f"VERDICT: {res.verdict}")
    L.append("  Rationale: at the honest OOS-IC band (0.01-0.03) the single-(open->close)")
    L.append("  edge of the top pick is ~1 bp vs ~11 bps round-trip cost (underwater ~10x),")
    L.append("  the cost-clearing hold is MULTI-DAY (not intraday), and the Fundamental-Law")
    L.append("  net-Sharpe band is centered negative. This is a PRIOR/NO-GO HYPOTHESIS to be")
    L.append("  empirically tested in a cost-charged SHADOW harness (M1) -- NOT a license to")
    L.append("  trade. A live-capital GO requires M1 to clear the pre-registered bar")
    L.append("  (placebo-clean OOS IC + net Sharpe + DSR/PSR>=0.95) on MEASURED cost+dispersion.")
    L.append("")
    L.append("Reproduce:")
    L.append("  /Users/renhao/git/github/RenQuant/.venv/bin/python "
             "scripts/research_intraday_feasibility.py")
    return "\n".join(L)


def main(argv: Sequence[str] | None = None) -> int:
    res = run_feasibility()
    print(_fmt(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
