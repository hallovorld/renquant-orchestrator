# 2026-08-05 — GOAL-4: I set a P0 from a row fraction and never measured the effect

## What I did wrong

orch#817 was filed as **P0** on two correct numbers: **53.10 %** of
`fwd_60d_excess` rows exceed `|0.5|`, and clipping collapses distinct values
**726,100 → 340,527**. I then wrote that the magnitudes in orch#805 / #807 / #809
"should not be quoted".

**I never measured the consequence.** The severity came from the fraction of
affected rows, which is not the quantity a rank statistic depends on.

## The measurement `[VERIFIED — this session]`

Gate's own corpus, validation slice `date > 2024-04-10`: 143,841 rows, 520 dates.
Mean per-date Spearman IC, clipped vs unclipped label, three fixed panel
predictors:

| predictor | unclipped | clipped | mean Δ | max \|Δ\| |
|---|---|---|---|---|
| `KMID` | +0.01040 | +0.01039 | **−0.00001** | 0.047 |
| `KLEN` | +0.04962 | +0.05425 | **+0.00463** | 0.051 |
| `ROC60` | +0.01924 | +0.02405 | **+0.00481** | 0.058 |

## Why a big row-fraction need not become a big IC change

**`clip` is a MONOTONE transform, and Spearman is invariant to monotone
transforms** — except through the ties they create. Clipping perturbs ranks only
where it creates ties.

### No ceiling is claimed `[codex on orch#822]`

An earlier version of this document said the 0.134 two-tie-group case was "the
ceiling on what clipping can cost". **The very next test in the same file
contradicts it**: a distribution whose values all land on one side of the bound
collapses to ONE tie group and loses the correlation entirely — the worst case is
**1.0**. How much is lost depends on how the values sit against the bound, which
is exactly why the served scorer must be measured rather than extrapolated to.

*(That test also began as a guess — ">0.9" — and failed at 0.866. The measured
value is pinned instead of the guess.)*

## What this does NOT settle — and what I wrongly used it to settle

These are **three fixed panel predictors, not a served scorer's `mu`**. The
evidence at issue in orch#805 / #807 / #809 is scorer-based IC.

I used this measurement to downgrade orch#817 off P0 and to narrow the caveats on
those issues. **Both moves are withdrawn**: using instrument probes to retire a
severity question about scorer evidence substitutes one measurement for another.
orch#817's severity is restored to **unresolved**, and the caveats are restored
to "the size of the effect on these numbers is not established".

Three severity moves on one issue in one night — flagged, downgraded, restored —
is one too many, and the fault each time was the same: acting before the right
quantity was measured.

## What actually settles it

Score the served artifact over the same validation slice and compute the per-date
IC twice, clipped and unclipped. That is the outstanding work; this script is the
harness it can reuse, and its own output now states that these numbers cannot
settle a severity question.

Suites: 9 tests, incl. both extremes of the tie behaviour (two groups → 0.866,
one group → total loss) and one bound to the live corpus · 5687 passed,
2 skipped.
