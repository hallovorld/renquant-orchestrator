# The regime criterion is satisfiable — and BULL_CALM fails it for neither reason I offered

**Bottom line `[本次实测 2026-07-31]`.** orch#673 ended with a question I set myself:
*"is `BULL_CALM`'s regime sanity criterion satisfiable by any model at all?"* It is —
**`BEAR` clears it on 11 of 11 artifacts**, with a placebo IC at **4%** of its real IC.
So both hypotheses #673 named are wrong. In `BULL_CALM` and `CHOPPY` a **60-day-shifted
label out-ranks the aligned one**, and that is a property of the labels, not of the model.

## The decomposition

The enforced conjunct is
`passed = mean_ic ≥ min_mean_ic AND |placebo_ic| ≤ max(0.005, 0.5·|aligned_real_ic|)`,
with `min_mean_ic = max(0.0, 0.25·|real_ic|)`.

| regime | placebo leg passes | median `placebo / real` |
|---|---:|---:|
| **BEAR** | **11 / 11** | **0.04** |
| BULL_CALM | **0 / 11** | **2.15** |
| CHOPPY | **0 / 11** | **6.61** |

`BULL_CALM`'s `mean_ic` is **positive on every artifact** (0.0211–0.0234), so it is **not
failing the skill floor** — it fails the placebo ceiling. The shifted label is doing
2.15× the ranking work the aligned label does.

## What that means, stated carefully

**Not "the gate is mis-specified."** BEAR passes it comfortably, every time, with the
same code and the same shift.

**Not "the models are bad."** Their IC in BULL_CALM is positive and stable across a
month of retrains.

> **It is a regime-local label property.** In BULL_CALM the cross-section is persistent
> enough that a label from 60 days ago still ranks it — and the criterion, correctly,
> refuses to certify skill it cannot separate from that persistence.

## The bar a model would have to clear by skill alone

The ceiling is `0.5·|aligned_real_ic|`, so passing against the observed placebo requires
`real_ic ≥ 2 × placebo_ic`. On the newest artifact that is **≈ 0.119** against today's
**0.025** — roughly **4×** the current real IC in that regime `[DERIVED from the frozen
CSV]`. That is the concrete, checkable target, and it replaces "the gate rejects
everything" with a number.

## Why this matters for GOAL-6

`BULL_CALM` carries **399–449 evaluation dates**, by far the largest regime in the panel.
A criterion that cannot certify the model's largest regime is what produces the 0-for-11
unaided pass rate #670 measured — and now the reason is specific enough to act on:
either raise real IC there by ~4×, or change what the placebo is being compared against.

**Neither is done here.** Changing an enforced gate constant is a capital-path decision
and needs its own preregistration.

Tests: 5, including the control that a passing regime must exist or the two hypotheses
stay indistinguishable.
