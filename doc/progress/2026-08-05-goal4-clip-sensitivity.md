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

## What settles it — DONE, on the served scorer

`[VERIFIED — this session]` Loaded `artifacts/prod/panel-ltr.alpha158_fund.json`
through the pipeline's own registry, scored the gate's fallback corpus over the
stamp's own window (`2023-12-26 … 2026-05-05`), and computed the per-date IC
twice:

| | |
|---|---|
| rows / dates | 164,869 / **591** — exactly the stamp's `sanity_n_oos_dates` |
| mean per-date IC, unclipped | **+0.06106** |
| mean per-date IC, clipped | **+0.06627** |
| **paired mean Δ** | **+0.00521** |

So on the **served scorer**, the clip moves the mean per-date IC by **+0.0052**.
orch#817's severity is settled on the right object: **not P0**, a ±0.005
perturbation cannot turn BEAR `+0.335` into BULL_CALM `−0.029`.

### The gap I could not explain, stated rather than glossed

My unclipped level is **+0.0611**; the artifact stamps `real_ic = 0.04656`. The
**date count matches exactly**, so the window is right and the level is not.
Undistinguished causes: a different `min_names` floor, universe filtering the
gate applies, or a manifest-scoped panel rather than the fallback corpus.

**Why the conclusion survives it**: the quantity is a **paired within-slice
difference** — same scorer, same rows, same dates, label transformed two ways. A
constant offset does not move a paired delta. A materially different *row set*
would, and the level gap is exactly the evidence that possibility is open. The
tool prints this caveat with every served run.

## Scope, finally correct

The panel-feature probes (≤0.005) describe three named instruments. The served
measurement (+0.0052) describes the artifact whose evidence was at issue. Only
the second can speak to orch#805/#807/#809, and it now does.

Suites: 11 tests, incl. both tie extremes, the served-mode caveat and a
CLI-reachability check · full suite green.
