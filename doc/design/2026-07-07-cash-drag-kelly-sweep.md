# Cash drag: Kelly fractional screening sweep

**Status**: DESIGN — for cross-agent review
**Scope**: Kelly `fractional` parameter only. Screening step, not final answer.
**Relationship to #405**: The merged concentration-cap sweep (#405) tests
`max_concentration × drift_buffer × top_up_threshold` (75 variants). This
sweep tests the **orthogonal** dimension: `kelly.fractional`, which controls
the sizing aggression multiplier. Neither sweep alone answers the cash-drag
question — both results together do.

## Problem statement

Strategy 104 holds ~62% cash (38% invested, 6 of 8 positions, 07-06).
Multiple parameters affect deployment. The concentration-cap sweep (#405)
covers the cap/trim/topup space. This design covers the remaining major
parameter: `kelly.fractional`.

## Why fractional needs its own sweep

`fractional` was changed from 0.5 to 0.3 on 2026-06-11 as a **coupled**
change with `sigma_horizon_days` (252 → 60). The rationale was:

> sigma_horizon 252→60 makes sigma ~2× smaller → f*=mu/σ² ~4× larger.
> Paired fractional 0.5→0.3 to keep total deployment sane (~56% vs ~96%).

This coupling means we cannot evaluate `fractional` in isolation — we need
to understand the interaction with the sigma change. The 0.3 value was
chosen by arithmetic projection ("keep deployment sane"), not by backtest.
Whether 0.3 is actually optimal under `sigma_horizon=60` is unknown.

**This sweep is a screening step**: it tells us whether fractional is a
material lever and, if so, what range to explore in a focused follow-up
(potentially interacted with concentration-cap results from #405).

## Hypotheses

- **H0 (null)**: `fractional=0.3` is already near-optimal given
  `sigma_horizon=60`. Changing it does not materially improve
  risk-adjusted returns or reduce cash drag.
- **H1**: `fractional=0.3` is too conservative. A higher value (0.4–0.7)
  improves deployment without degrading Sharpe or MaxDD beyond tolerance.
- **H2**: `fractional=0.3` is too aggressive. Lower values would improve
  risk-adjusted returns (unlikely given 62% cash, but must test).

## Design

### Grid

One dimension, 5 levels (including incumbent):

| Variant | fractional | Role | Rationale |
|---|---|---|---|
| F0 | 0.3 | incumbent | Current production |
| F1 | 0.2 | candidate | Test if current is too aggressive |
| F2 | 0.4 | candidate | Modest increase |
| F3 | 0.5 | candidate | Pre-06-11 value (half-Kelly at old sigma) |
| F4 | 0.7 | candidate | Aggressive |
| AA | 0.3 | aa_resplit | Noise floor (seed offset +1000) |

6 variants × 3 seeds {42, 43, 44} = 18 sim runs. ~1.5-3h.

### Decision criteria

Same as concentration-cap sweep (#405) for consistency:

| Criterion | Threshold |
|---|---|
| Sharpe | ≥ incumbent − 0.02 (materiality band) |
| Max DD | ≤ 1.10 × incumbent |
| Per-regime Sharpe | No regime >0.02 degradation |
| Turnover | ≤ 1.25 × incumbent |
| A/A delta | |Sharpe lift| ≤ 0.10 |

Additionally report:
- Mean cash % (the quantity we are trying to reduce)
- APY, Calmar
- Per-regime breakdown (BULL_CALM, BEAR, BULL_VOLATILE)

### What this sweep does NOT answer

1. Interaction between fractional and max_concentration/topup_threshold
   → requires a cross-sweep after both screening passes complete
2. Whether the sigma_horizon change itself was correct
   → out of scope; sigma_horizon was changed for dimensional correctness
3. The optimal combined configuration
   → Phase 2 work, dependent on both this result and #405's result

### Controls

- **A/A**: incumbent config with seed offset {1042, 1043, 1044}.
  Must show ≤0.10 absolute Sharpe lift vs primary incumbent run.
- **Seeds**: frozen {42, 43, 44}, unanimity verdict rule.

## Backtest setup

- Period: 2024-01-02 to 2026-03-28
- WF manifest: `artifacts/sim/walkforward_manifest_v2_20260602.json`
- Base config: `strategy_config.sim_kelly_ab_admoff.json`
- Initial cash: $100,000

## Execution plan

1. This PR: design doc only (for review)
2. After design accepted: runner PR (follows #405 pattern)
3. Execute sweep, write results memo
4. Cross-reference with #405 concentration-cap results
5. If warranted: Phase 2 interaction grid on the top parameters
