# GOAL-4 — the boosters really do disagree, and my own synthetic number was ~1.7× too high

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-4 (multi-model ensemble)

## Bottom line

orch#698 measured that same-recipe boosters are not the same function — on a **synthetic
probe**, and it said in its own title that it licensed no production inference. This is the
production measurement it deferred, and it **corrects #698's headline**.

12 distinct boosters (one config fingerprint `sha256:f8fb2259b`, 172 features each,
`eval_ic` 0.0454–0.0743) scored on the live `alpha158_291_fundamental_dataset` panel over
its last 20 sessions, 2026-04-07 → 2026-05-04, 144–153 names/date `[本次实测 2026-08-01]`:

| | |
|---|--:|
| per-date median pairwise Spearman | **0.854** |
| per-date median top-decile overlap | **0.643** |
| **median top-decile disagreement** | **35.7%** |
| worst pair, worst date (2026-04-13) | **67% replaced** |

**#698 reported ~60% on the synthetic probe. Real data says 35.7% median.** The synthetic
figure overstated the typical case by ~1.7×, although the real *range* reaches it. The
direction #698 claimed survives; **its magnitude is withdrawn as a description of
production**, and a test asserts the real median stays below 0.50 so a later edit cannot
silently restore the old number.

## Where this points, joined with tonight's other measurement

`renquant-pipeline`#244 measured that **53 of 53** stamped artifacts carry
`candidate_artifact_used=false`: every "WF gate passed" is a statement about the *recipe*,
and 51 of 53 share one fingerprint. Put together:

> **The gate that admits capital cannot distinguish models that replace a third of the
> traded top decile — two thirds in the tail.**

That reframes the ensemble premise. The problem is not that candidate members are too
similar to be worth blending; they are not similar. It is that **nothing validates which
member is serving.**

## Assumptions, stated rather than buried

`transform_feature_frame` is **imported** from
`renquant_pipeline.kernel.panel_pipeline.feature_transform`, never restated. It is called
with `source_space="panel"` because the input is the prebuilt alpha158 panel — **my
choice** `[假设]`. The artifact's own `feature_source_contract` field turns out to be a
*documentation dict*, not a selector; passing it directly raised, which is how I found
out. The live path would use `"raw"` and could give different numbers.

## Not claimed

That any booster is better than another — no label or forward return is touched here.
That 35.7% is a stable long-run figure: 20 consecutive sessions at the panel's frontier is
not a history. That blending would help — disagreement is a *precondition* for an ensemble
to be worth anything, never evidence that one works.

## Tests

11. The load-bearing ones: boosters are keyed on the **booster bytes**, not the config
fingerprint (keying on the fingerprint would collapse all 12 into 1, and that collapse is
the defect under measurement); every date is accounted for as scored **or** explicitly
skipped-thin; and both the assumption and the not-claimed lists travel inside the emitted
report rather than living only in prose. Suite: **5195 passed, 2 skipped**, run before the
push.
