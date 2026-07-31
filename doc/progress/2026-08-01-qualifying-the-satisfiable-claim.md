# Qualifying my own #677: the criterion is satisfiable only in a degenerate corner

**Bottom line `[本次实测 2026-08-01]`.** #677 concluded *"the regime criterion IS
satisfiable — `BEAR` clears it on 11 of 11 artifacts."* That conclusion rests entirely on
a regime whose statistics are **not those of a normal alpha**, and the claim has to be
narrowed.

| regime | n_dates | n_rows | mean_ic | **hit_rate** | placebo_ic | passed |
|---|---:|---:|---:|---:|---:|---:|
| BULL_CALM | **444** | **127 092** | 0.0220 | **0.508** | 0.0605 | **0 / 11** |
| BEAR | 55 | 15 320 | **0.3346** | **0.982** | 0.0158 | **11 / 11** |
| BULL_VOLATILE | 41 | 8 716 | 0.1116 | 0.732 | 0.1468 | 1 / 11 |
| CHOPPY | 41 | 11 972 | 0.0129 | 0.707 | 0.0798 | 0 / 11 |

## What is wrong with the original claim

`BEAR`'s per-date IC is positive on **98.2%** of its dates, at **15×** the IC of the
regime carrying **8× the rows**, and it is stable across all eleven artifacts (range
0.0050).

> **A 98.2% hit rate is not what ranking skill looks like — it is what a cross-section
> moving as one looks like.** In a bear regime, if names fall together and the model's
> score correlates with anything beta- or volatility-like, the ranking matches the
> outcome almost every day without carrying information about relative performance.

So the demonstration that the criterion *can* be satisfied comes from **the thinnest
slice in the panel** (55 dates, 12% of BULL_CALM's rows) under conditions that do not
generalise.

## The corrected statement

**Original (#677):** *"the criterion is satisfiable; therefore neither 'the gate is
mis-specified' nor 'the models are bad' holds."*

**Corrected:** the criterion is satisfied **in exactly one regime, and that regime is
degenerate**. For the regimes that carry the panel it has **never** been satisfied, and
`BEAR` does not demonstrate that it is reachable there. The mis-specification hypothesis
is therefore **not excluded** — it is only excluded for a criterion that never passes
*anywhere*, which is not the situation.

## What survives untouched

#677's other finding stands and is re-pinned here: **`BULL_CALM` fails the placebo leg,
not the skill floor.** Its `mean_ic` is positive (0.0220) and its placebo IC is **2.7×**
that — a 60-day-shifted label out-ranking the aligned one. That measurement is
independent of anything BEAR does.

Also unchanged: the concrete bar. Passing BULL_CALM by skill alone still requires
`real_ic ≥ 2 × placebo_ic` ≈ **0.121** against today's **0.022**.

## Method note

I found this by asking a question about **my own published claim** — *"BEAR passes; is
BEAR normal?"* — rather than by any check firing. **That is the second self-correction in
two rounds** (the other retracted #676's 7/14). Both were found by re-interrogating a
number I had already shipped, which is the only mechanism that has actually caught these.

Tests: 5, including a control that this qualification does **not** overturn the placebo
finding.
