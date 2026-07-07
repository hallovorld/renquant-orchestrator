# Cash drag: Kelly-fractional exploratory screening sweep

**Status**: EXPLORATORY HYPOTHESIS SCREEN — downstream follow-up research, not
a primary cash-drag design. For cross-agent review of scope/framing only.
**Scope**: the Kelly `fractional` sizing-aggression multiplier only
(`kelly.fractional` config key). This is a screening step, not a decision-grade
verdict — see "Where this sits in the cash-drag program" below.

## Terminology — read this first

This document studies **`kelly.fractional`**, a Kelly-criterion sizing-aggression
multiplier (`f* = mu/sigma^2`, scaled by `fractional`). This is a **completely
different intervention** from **fractional-share execution** (buying non-integer
share quantities to remove whole-share rounding loss), which is the mechanical
Phase-1 fix prioritized in `doc/design/2026-07-07-104-105-cash-drag-resolution.md`
(the "#406 program"). The two share the English word "fractional" and nothing
else — one is a sizing-policy knob, the other is a broker-execution capability.
Every use of "fractional" below refers to `kelly.fractional` unless explicitly
qualified as "fractional-share execution."

## Where this sits in the cash-drag program

The #406 program establishes this execution order for cash-drag work:

1. **Phase 1 (mechanical, first)**: fractional-share execution — fixes
   whole-share quantization loss on high-price names. This is the measured
   binding constraint (BLK/AVGO repeatedly rounded to 0 shares).
2. **Phase 2 (mechanical, second)**: parking sleeve (SGOV-first) for residual
   idle cash after Phase 1.
3. **Phase 3 (policy, only after re-measuring on the new baseline)**: exposure
   and sizing-policy knobs — `top_n`, `qp_cash_drag_lambda`, `max_concentration`,
   and this document's `kelly.fractional` — retested only once the mechanical
   drag is removed, so exposure changes aren't confounded with plumbing fixes.

**This document is Phase-3, downstream, exploratory research.** It does not
compete with, replace, or "together" complete the #406 program's execution
order alongside the concentration-cap sweep (#405). Both `kelly.fractional`
and concentration-cap are Phase-3 exposure-policy levers; neither should be
read as advancing the primary cash-drag decision ahead of Phase 1/2. This
sweep's purpose is narrowly to screen whether `kelly.fractional` is worth a
focused, properly-designed follow-up study once Phase 1/2 land and a new
baseline is measured — not to answer the cash-drag question now.

## Problem statement

Strategy 104 holds ~62% cash (38% invested, 6 of 8 positions, 07-06). The
#406 program identifies whole-share quantization as the primary, measured
binding constraint (Phase 1). This document is a narrower, secondary
question: once Phase 1/2 land, is `kelly.fractional` (currently 0.3,
last changed by arithmetic projection rather than backtest) also worth
revisiting as a Phase-3 exposure lever?

## Why this deserves a follow-up screen — and why it is a screen, not a design

`fractional` was changed from 0.5 to 0.3 on 2026-06-11 as a **coupled**
change with `sigma_horizon_days` (252 → 60). The rationale was:

> sigma_horizon 252→60 makes sigma ~2× smaller → f*=mu/σ² ~4× larger.
> Paired fractional 0.5→0.3 to keep total deployment sane (~56% vs ~96%).

**This coupling is the reason this document cannot be a primary design.**
The 0.3 value was chosen by arithmetic projection to keep the *pair*
`(sigma_horizon, fractional)` sane — it was never validated by backtest, and
the two parameters interact by construction. A rigorous test of whether 0.3
is optimal requires a factorial `kelly.fractional × sigma_horizon_days`
interaction study, not a 1D sweep holding `sigma_horizon` fixed.

**What this document actually proposes is a cheaper, 1D screen**: hold
`sigma_horizon_days` fixed and sweep only `kelly.fractional`, to get a fast
signal on whether the coupled pair is even in the right neighborhood. This
is explicitly a lower-confidence, exploratory step — it cannot itself
validate or reject the 0.3 value, only flag whether further (factorial)
investigation is warranted. If this screen finds a material signal in either
direction, the required next step is the full `kelly.fractional ×
sigma_horizon_days` interaction study, not a promotion decision off this
screen alone.

## Hypotheses

- **H0 (null)**: `fractional=0.3` is already near-optimal given
  `sigma_horizon=60`. Changing it does not materially improve
  risk-adjusted returns or reduce cash drag.
- **H1**: `fractional=0.3` is too conservative. A higher value (0.4–0.7)
  improves deployment without degrading Sharpe or MaxDD beyond tolerance.
- **H2**: `fractional=0.3` is too aggressive. Lower values would improve
  risk-adjusted returns (unlikely given 62% cash, but must test).

## Screen design

### Grid

One dimension, 5 levels (including incumbent). This is deliberately a cheap
1D screen, not the factorial `kelly.fractional × sigma_horizon_days` study
the coupling above implies is ultimately required:

| Variant | fractional | Role | Rationale |
|---|---|---|---|
| F0 | 0.3 | incumbent | Current production |
| F1 | 0.2 | candidate | Test if current is too aggressive |
| F2 | 0.4 | candidate | Modest increase |
| F3 | 0.5 | candidate | Pre-06-11 value (half-Kelly at old sigma) |
| F4 | 0.7 | candidate | Aggressive |
| AA | 0.3 | aa_resplit | Noise floor (seed offset +1000) |

6 variants × 3 seeds {42, 43, 44} = 18 sim runs. ~1.5-3h.

### Screening thresholds (not a promotion gate)

These reuse the concentration-cap sweep's (#405) materiality bands for
measurement consistency, but the verdict here is "does this warrant a
follow-up factorial study," not "promote this value to production":

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

A candidate clearing these bands means "worth a proper factorial
`kelly.fractional × sigma_horizon_days` study," not "ready to change
production `fractional`."

### What this screen does NOT answer

1. **The interaction with `sigma_horizon_days`** — this is the central
   limitation, not a footnote. `fractional` and `sigma_horizon_days` were
   changed as a coupled pair; this 1D screen holds `sigma_horizon_days`
   fixed, so it cannot validate or reject the pair's joint optimality. A
   material signal here only justifies running the full interaction study.
2. Interaction between `kelly.fractional` and the concentration-cap
   dimensions (#405) — both are Phase-3 exposure levers per the #406
   program; a cross-sweep would only make sense after Phase 1/2 land and
   both screens are re-run on the new baseline.
3. Whether the `sigma_horizon_days` change itself was correct — out of
   scope; it was changed for dimensional correctness, independent of this
   screen.
4. The optimal combined configuration — this requires the factorial study
   in point 1, run only if this screen and #405 both show material Phase-3
   signal on the Phase 1/2 baseline.

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

This is downstream, exploratory follow-up work — it does not gate or compete
with the #406 program's Phase 1 (fractional-share execution) or Phase 2
(parking sleeve). It should be executed after Phase 1/2 land and a new
baseline is measured, so any signal here is attributable to
`kelly.fractional` rather than confounded with the mechanical fixes.

1. This PR: design/framing doc only (for review of scope, not for
   scheduling ahead of Phase 1/2).
2. Once Phase 1/2 (fractional-share execution, parking sleeve) have landed
   and a new baseline is measured: build the runner PR (structurally
   following the #405 pattern for consistency, run on the new baseline).
3. Execute the screen, write a results memo explicitly labeled as an
   exploratory screen, not a promotion recommendation.
4. Cross-reference with #405's concentration-cap screen results — both are
   Phase-3 candidate levers, read together only as candidates for further
   study, not as a joint answer to the cash-drag question.
5. If either screen shows a material signal: run the full factorial
   `kelly.fractional × sigma_horizon_days` interaction study (for this
   screen) and/or the corresponding cross-sweep (for #405) — this is the
   actual decision-grade follow-up, not this screen itself.
