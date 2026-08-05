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

## Why the big number does not become a big number

**`clip` is a MONOTONE transform, and Spearman is invariant to monotone
transforms** — except through the ties they create. Clipping perturbs ranks only
at the two ends; the interior keeps its order. "53 % of rows clipped" sounds
catastrophic for a rank statistic and is not.

The ceiling is measurable too, and the test pins it: force **every** value into
just two tie groups on a perfectly monotone relation and the IC falls
**1.000 → 0.866**, a 0.134 cost. That is the worst this transform can do here;
the live panel, whose interior stays distinct, pays ≤0.005.

*(My first version of that test guessed ">0.9" and failed at 0.866. The measured
value is pinned instead of the guess.)*

## Consequences for the record

- **orch#817 downgraded** from P0 to a correctness/consistency issue, retitled.
- **The caveats I posted on orch#805 / #744 are narrowed.** BEAR `+0.335` and
  BULL_CALM `−0.029` are separated by ~70× the perturbation; they are **not**
  plausibly clip artefacts, and my "should not be quoted" is withdrawn.
- **What still deserves fixing**, for consistency rather than magnitude: the real
  arm is unclipped while the placebo arm is clipped, so `genuine_ic` subtracts
  differently-transformed quantities. Small here; gratuitous everywhere.
- **The units observation stands**: `fwd_60d_excess` is standardised (sd 0.998)
  while `fwd_60d_excess_raw` is the return (sd 0.185). A ±0.5 clip is a 1.19 %
  winsorisation on the raw column and 0.501 SD on the standardised one — which
  still looks like a clip written for the other column.

## Scope

Fixed panel predictors, **not** a served scorer's `mu`. A model whose scores
concentrate differently against the clipped tails could move more. The ≤0.005
figure is a statement about this instrument's sensitivity, not about that model's
numbers, and the script says so in its own output.

Suites: 7 new tests, incl. both extremes of the monotone property and one bound
to the live corpus that fails if the clip ever starts mattering · 5687 passed,
2 skipped.
