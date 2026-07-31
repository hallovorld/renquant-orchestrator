# Decomposing the gate answers the question #670 left open

**Bottom line.** #670 measured **0 unaided passes in 11 artifacts** and said the
distinction between *"the gate is right and the candidates are bad"* and *"the gate is
mis-specified"* could not be made while every admission is manual. Decomposing the
verdict into its sub-criteria makes it: **three sub-gates reject 11 of 11**, and **two of
them reject the same regime every single time.**

## The matrix `[本次实测 2026-07-31]`

| sub-criterion | fails |
|---|---:|
| `sanity` | **11/11** |
| `sanity_regime_ic` | **11/11** |
| `trade_monotonicity` | **11/11** |
| `wf` | 10/11 *(only the deployed artifact passes)* |
| `trade_contract` | **0/11** |

`trade_contract` passing 11/11 is the control that matters: the artifacts **are** being
evaluated, not merely erroring out, so the three 11/11 rows are verdicts and not crashes.

## The structural signature

| criterion | failing regimes | artifacts |
|---|---|---:|
| `sanity_regime_ic` | `BULL_CALM` | **11/11** |
| `sanity_regime_ic` | `CHOPPY` | **11/11** |
| `sanity_regime_ic` | `BULL_VOLATILE` | 10/11 |
| `trade_monotonicity` | `BULL_CALM` | **11/11** |

> **`BULL_CALM` fails two independent sub-criteria on every artifact without
> exception.** Eleven vintages trained across a month, all failing the same regime on
> two different criteria, is a property of the criterion or of that regime's
> population — not eleven independently bad models.

## What this licenses, and what it does not

**Licensed:** a criterion that rejects **100%** of the population it judges carries no
information about which candidate is better. It can reject; it **cannot rank**. That is
why the only path to production has been the operator override #670 documented — the
gate offers no gradient to improve along.

**Not licensed:** the conclusion that the gate is *wrong*. A 100%-reject gate can be
perfectly correct if all eleven candidates genuinely are bad in `BULL_CALM`. What the
measurement establishes is that **the gate cannot tell us which**, and that a month of
retraining moved none of these rows.

**Population caveat, stated rather than buried:** all 11 artifacts are the **same
recipe** (`alpha158_fund`). "11/11" is over a narrow population, and nothing here
generalises to a different recipe.

**Not reported:** I also tried to extract each artifact's `shuf_ic` against the enforced
`|shuf_ic| < 0.005` leakage bar. My extraction keyed on the wrong field and returned
**zero rows**, so there is no shuffled-IC result in this document. A zero-row extraction
is not a zero-count finding.

Tests: 5, including the `trade_contract` anti-vacuity control. Filed against
`renquant-backtesting#90`.
