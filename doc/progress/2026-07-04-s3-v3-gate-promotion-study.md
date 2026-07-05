# S3 v3 gate promotion study design

DATE: 2026-07-04

## What

Designed and preregistered the experiment needed to promote the v3 WF gate
(placebo difference test) from shadow-only to enforced. This removes one
gate-design confound in the D1 evidence path — it does not by itself unblock
D1 for the current production model (see Round 2 below).

## Key finding

Replay of 8 staging artifacts confirms v2 is structurally unsatisfiable: the
~0.04 embargo floor makes every model fail the absolute-IC ceiling by
construction. v3 (genuine_ic = aligned_real_ic − placebo_ic > 0.02) correctly
cancels the shared floor and would pass 8/8 artifacts.

## Next

Run the preregistered false-accept test and estimator-stability check (steps
1–4 in the study design), then promote v3 in the backtesting repo. Model
retraining with regime-specific edge remains a separate, independent blocker
for actual D1 clearance regardless of gate promotion (see Round 2).

## Round 2 (Codex review — causal overclaim + false-reject mislabeling)

Codex blocked on two issues, both fixed in the study-design doc:

1. **Causal overclaim.** The doc repeatedly framed v3 promotion as "the
   critical path to unblocking D1," but the companion D1 verdict assessment
   (`research/d1-verdict-assessment`) finds the current production model is
   model-blocked on regime-level genuine IC: BULL_CALM genuine_ic = 0.017
   (below the 0.02 bar, ~78% of trading time), CHOPPY genuine_ic ≈ 0. Even a
   correctly-repaired v3 gate would not clear D1 for this model. Narrowed
   every occurrence (BLOCKS line, Bottom line, Execution plan step 6, Pre-
   registration primary outcome) from "unblocks D1" to "removes one gate-
   design confound," and added an explicit step 7 + note stating model
   retraining is a separate, independent blocker out of scope for this study.
2. **False-reject/Type II mislabeling.** §2 subsampled a single
   already-positive model (XGB) over shrinking windows and labeled the
   result a "false-reject rate (Type II error)." That measures estimator
   variance on one model/date series, not a population-level false-reject
   rate — we have no population of genuinely-positive candidate models to
   sample from. Relabeled §2 as an "estimator stability check," reworded
   the acceptance criterion and pre-registration language to "instability
   signal" instead of "false-reject rate," and added an explicit limitation
   note that this check cannot establish or bound v3's true Type II rate.
