# GOAL-4 — same-recipe boosters disagree on ~60% of the top decile

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-4 (ensemble) / GOAL-6 (eval path)

## The gap this closes

orch#692 measured that 30 prod artifacts share **one** admission fingerprint while holding
**12 distinct boosters** — and deliberately stopped:

> *"A booster digest mismatch means DIFFERENT LEARNED MODELS. It does not follow that
> their predictions differ materially — nothing is scored here."*

That was the right restraint and it left the load-bearing question open: **is the gate's
inability to tell these apart costly, or merely untidy?**

## Measured `[本次实测 2026-07-31]`

All 12 distinct boosters scored on **one common input**, N = 2000 rows, 172 features,
seed 20260731:

| vs the served booster | min | median | max |
|---|---:|---:|---:|
| Spearman rank correlation | **0.4814** | **0.5980** | 0.8313 |
| top-decile overlap | **29.0%** | **40.0%** | 49.0% |

**Two artifacts the gate treats as the same recipe disagree on roughly 60% of the top
decile.**

So GOAL-4's premise divides the way #692 suggested, and now with a number on the second
half: **diversity is not the blocker — attribution is**, and the cost of not having it is
about 60% of the names at the sharp end.

It also sharpens orch#692's promotion series: the 10 staged candidates that were **never
promoted** are not near-copies of the incumbent. Their Spearman against it runs 0.48–0.83.

## The caveat, and the direction of what it leaves out

**The input is synthetic** — standard normal in the **post-normalisation** feature space.
That is defensible rather than arbitrary: the artifacts normalise upstream, and
`feature_norm_kind` is `global_z` on **158** of 172 features and `robust_z` on **5**. But
**9 are `identity`**, unnormalised, and for those a standard normal is simply the wrong
distribution.

**The remaining bias has a knowable direction.** Real cross-sectional feature vectors are
strongly correlated; these draws are independent. Correlated inputs generally push tree
models toward **agreeing**, so the real-panel overlap is plausibly **higher** than 40%.

That makes this number a **bound on how far apart these models can get**, not an estimate
of how far apart they are on a trading day. Naming the direction of a bias is not the same
as correcting for it, and **no correction is applied**.

**What would replace this:** scoring all 12 on a real served panel. That needs the
172-feature panel rebuilt through the pipeline's feature engineering, which a read-only
probe does not do — and which is the same missing artefact behind task #17 (serving
feature vectors are never persisted).

## Tests

11. Deduplication **by digest**, so a corpus with copies scores each *model* once —
otherwise a duplicated model weights the summary, the same collapse #692 measures. A
booster compared to **itself** scores exactly 1.0 (without which the metric is
meaningless); genuinely different models **do** diverge (without which the probe cannot
detect what it exists for); the probe is **deterministic** for a fixed seed, because a
number nobody can re-derive is an assertion with a citation attached; a **feature-set
mismatch refuses to score**, since one matrix would silently compare different functions
of different inputs; fewer than two boosters exits **1**, because "nothing to compare" must
never read as "they agree"; the served artifact must be **named, never guessed**; and the
report is asserted to state that the input is synthetic **and to name the direction of the
bias**.

Suite: **5074 passed, 2 skipped** — run before the push.

## A process note

The first run of the probe reported `rc=0` — from `tail`, not from the tool, because the
invocation piped output before reading `$?`. Re-run without the pipe: **`rc=1`**, which is
correct. That is the "never swallow an exit code in a pipe" rule, broken again in the same
session it was written down.
