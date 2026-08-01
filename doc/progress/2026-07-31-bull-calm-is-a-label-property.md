# The criterion is satisfiable in ONE regime — and BULL_CALM fails its placebo leg, not its skill floor

**Bottom line `[本次实测 2026-07-31]`.** orch#673 ended with a question I set myself:
*"is `BULL_CALM`'s regime sanity criterion satisfiable by any model at all?"* It is —
**`BEAR` clears it on 11 of 11 artifacts**, with a placebo IC at **4%** of its real IC.
~~So both hypotheses #673 named are wrong.~~ **WITHDRAWN — see orch#680, merged.** That
demonstration comes from **55 dates in the panel's smallest regime**, which is
insufficient evidence of generalisability to the regimes that carry the panel, so the
exclusion does not follow. What survives is the decomposition below: in `BULL_CALM` and
`CHOPPY` a **60-day-shifted label out-ranks the aligned one**.

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

## What that means, stated carefully — CORRECTED after orch#680

~~**Not "the gate is mis-specified."** BEAR passes it comfortably, every time, with the
same code and the same shift.~~ **WITHDRAWN.** One regime passing on 55 dates does not
exclude mis-specification; it excludes only the strictly weaker claim that the criterion
passes *nowhere*. orch#680 (merged) states this: *"#677's exclusion of the
mis-specification hypothesis does not stand."*

**Not "the models are bad"** — this half survives, and it is a decomposition fact rather
than an inference: `BULL_CALM`'s `mean_ic` is positive on every artifact (0.0211–0.0234)
and the failing conjunct is the **placebo ceiling**, not the skill floor.

~~> **It is a regime-local label property.** In BULL_CALM the cross-section is persistent
> enough that a label from 60 days ago still ranks it.~~ **WITHDRAWN — that is a
mechanism, and nothing here measures it.** A persistent cross-section would produce this
profile; so would other things. The measured statement is narrower and is all that is
claimed:

> **In `BULL_CALM` a 60-day-shifted label out-ranks the aligned one — median
> `placebo / real` = 2.15 — so the criterion fails on the placebo leg while the skill
> floor is met.** Why the shifted label ranks that well is **not established here**.

**Why these are struck rather than deleted.** This PR was open while orch#680 corrected
it and merged, so for a period `main` carried a document saying this one's conclusion did
not stand while this one still asserted it. That is the seventh instance on this
programme of a claim outliving its own correction, and the second where the correction
and the claim sit in different artifacts.

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

---

## Guard added 2026-07-31 — the withdrawn sentences cannot return unmarked

`tests/test_regime_sanity_decomposed.py` now carries the corrected scope in its module
docstring, and the satisfiability test is renamed
`test_the_criterion_IS_satisfiable_SOMEWHERE` so the executable artifact stops asserting
the width the document retracted. A test named after a conclusion is a claim too.
