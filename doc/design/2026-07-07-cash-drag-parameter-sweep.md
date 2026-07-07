# Cash drag parameter sweep — experiment design

**Status**: EXPERIMENT DESIGN — no conclusions pre-assumed
**Goal**: Identify which parameter(s) are the binding constraint for 62% cash
through backtest evidence, not arithmetic projection

## Problem statement

Strategy 104 holds 62% cash (38% invested) with 6 of 8 possible positions.
We do NOT know why. Multiple parameters interact to determine deployment.
We will run a controlled backtest experiment to find out.

## Candidate parameters

8 parameters could plausibly affect cash deployment. Each is a hypothesis:

| # | Parameter | Current value | Hypothesis | Needs testing |
|---|---|---|---|---|
| H1 | kelly.fractional | 0.3 | Sizing too conservative | YES — coupled with sigma_horizon change (0.5→0.3 when 252→60) |
| H2 | kelly.max_concentration | 0.12 | Per-name cap too tight | YES — may or may not be binding |
| H3 | kelly.top_up_threshold | 0.05 | Gap threshold prevents top-ups | YES — arithmetic says 3 names blocked |
| H4 | panel_scoring.buy_floor | adaptive_mean_std k=1.0 | Kills too many candidates | MAYBE — 6+ pass daily but effect on breadth unknown |
| H5 | kelly.base_rate | 0.273 | Base sizing multiplier | YES — unclear origin/sensitivity |
| H6 | kelly.sigma_horizon_days | 60 | Vol window affects sizing | CAREFUL — changed for dimensional correctness |
| H7 | regime.max_position_pct | 0.12 | Regime cap redundant with max_conc | MAYBE — may be bound elsewhere |
| H8 | regime.qp_turnover_max | 0.15 | Turnover cap prevents buying | MAYBE — unclear if binding |

**Key coupling to understand**: H1 and H6 were changed TOGETHER on 06-11.
`sigma_horizon 252→60` makes sigma ~2x smaller → f*=mu/sigma^2 ~4x larger.
`fractional 0.5→0.3` was the compensating reduction. Testing H1 without
understanding this coupling is dangerous.

## Experimental design

### Phase 1: One-At-a-Time (OAT) sensitivity

Change exactly ONE parameter per variant from incumbent. This isolates the
marginal effect of each parameter without interaction confounds.

| Variant | Changed parameter | Value | All others |
|---|---|---|---|
| V0 (incumbent) | — | — | production config |
| V1 | fractional | 0.4 | incumbent |
| V2 | fractional | 0.5 | incumbent |
| V3 | fractional | 0.7 | incumbent |
| V4 | max_concentration | 0.15 | incumbent |
| V5 | max_concentration | 0.20 | incumbent |
| V6 | top_up_threshold | 0.02 | incumbent |
| V7 | buy_floor | adaptive_quantile q=0.70 | incumbent |
| V8 | qp_turnover_max | 0.25 | incumbent |
| AA | — (incumbent config) | seed-offset | A/A control |

10 variants × 3 seeds {42, 43, 44} = 30 sim runs. ~3-5h.

### Phase 2: Interaction grid (conditional on Phase 1 results)

Take the top 2-3 parameters that showed significant effect in Phase 1.
Run a focused 2D or 3D grid to check for interaction effects.

Grid size TBD after Phase 1 data.

### Decision criteria

For each variant vs incumbent, report:

| Metric | Requirement to consider "better" |
|---|---|
| Sharpe ratio | ≥ incumbent (no degradation) |
| Max drawdown | ≤ 1.2 × incumbent |
| Cash % (mean) | Lower than incumbent (the goal) |
| APY | Report but not a gate |
| Turnover | ≤ 2.0 × incumbent |
| n_trades | Report for context |

All criteria must hold unanimously across 3 seeds.
A/A control must show ≤ 2σ deviation from incumbent (validates noise floor).

### What we will NOT do

- Pre-assume which parameter is "the answer"
- Recommend changes without backtest evidence
- Change multiple parameters simultaneously in Phase 1
- Ignore the fractional↔sigma_horizon coupling

## Seeds

Frozen: {42, 43, 44}. A/A offset: {1042, 1043, 1044}.

## Backtest period

Same as production validation: 2024-01-02 to 2026-03-28.
WF manifest: artifacts/sim/walkforward_manifest_v2_20260602.json.
