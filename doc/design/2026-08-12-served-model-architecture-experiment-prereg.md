# served-model architecture (solo-xgb vs the served z-blend) — EXPLORATORY SCOPING, not a preregistration

STATUS: **NOT a preregistration. This document authorizes nothing and decides
nothing.** Earlier revisions were titled and presented as a FROZEN experiment
preregistration and as the orch#799 "decider". They could not be either, for two
reasons that are properties of the data and the process, not of the drafting:

**1 — the window was not frozen.** The declared 125-fold window was contingent on
an execution-time three-cutoff feasibility probe, after which the window could be
trimmed and `n_BEAR` restated. So the actual sample, the episode partition, and
therefore the power were **unknown at approval time**. A preregistration whose
sample is settled during execution is not a preregistration; it is a plan to
decide the sample after seeing what is available.

**2 — the evidence cannot carry a production-architecture reversal.** The
regime-conditional arm rests on **eight historical BEAR episodes**. Eight
dependence-structured episodes with a percentile bootstrap rule is exploratory
evidence. It is not a defensible basis for reverting the served architecture, and
no dependence-aware confirmatory power analysis has been done that would make it
one.

**This document must not be executed as a production decider.** Any future
experiment in this line needs a NEW, complete, independently reviewable
preregistration that (a) commits the FULL non-outcome feasibility verification
first — all cutoffs, the exact PIT inputs and version, the generator, and an
immutable backtesting pin — and then freezes the actual resulting window; and
(b) establishes dependence-aware power for whatever regime partition it intends
to use. **It inherits nothing from this document.**

## What was deleted, and why deletion rather than fencing

The normative body stood here: hypothesis, arms, window, metric, a
"pre-registered decision rule (FROZEN — executable)", an actionable-outcome
section mapping results to production changes, and a build/process section.

**It is deleted, not fenced.** The sibling PR in this line (orch#975) spent four
review rounds trying to keep an equivalent body as clearly-marked background, and
normative text survived inside the fence every single time — "this document
freezes them", "If it can, implement", "Acceptance (when implemented)". A
divider does not neutralise sentences that contradict it. And since a future
prereg inherits nothing from here, a rule sketch it may not inherit is a hazard,
not background.

The full text remains in this branch's git history.

## What is worth carrying forward

Recorded as findings, not specification:

- The served architecture question is real and unresolved: the weekly promote
  chain refuses structurally while the served primary is a blend and the retrain
  emits a solo xgb leg (orch#799, and the measured feasibility blocker in
  orch#975).
- **Regime-conditional evidence in this system is episode-limited.** Eight BEAR
  episodes is the binding constraint on any BEAR-conditional claim here, and it
  will not improve quickly — this is the same shape as the 60-day-label /
  21-day-cadence overlap that limited orch#975 to `n_eff = 15`. Any future design
  in this line should establish its effective sample **before** choosing a
  decision rule, not after.
- A feasibility verification that runs at execution time cannot be a
  precondition of approval. If the window depends on it, it belongs in the PR
  that freezes the window, completed.

## The window artifact is deleted too

`doc/research/data/2026-08-12-served-model-experiment/` (a README calling itself
"the frozen window definition" and a 125-fold `fold_manifest.json` stamped
`"experiment": "… (orch#799 decider)"`) is removed with the rest.

It is the artifact of a freeze that did not hold. Leaving it committed while this
document says nothing is frozen would move the contradiction one level out, and
worse, it would invite a future run to reuse a window whose feasibility was never
verified — the exact ordering error recorded above. A future preregistration must
regenerate the window **after** completing the full non-outcome feasibility
verification, not inherit this one. It remains in git history.
