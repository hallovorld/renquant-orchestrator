# GOAL-6 — the gate's recipe projection is blind by construction, and the fix everyone would reach for is also wrong

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-6 (evaluation path)

## Bottom line

Over the 30 stamped `panel-ltr.alpha158_fund*` artifacts, deduplicated by booster bytes to
**12 distinct boosters** `[本次实测 2026-08-01]`:

| | |
|---|--:|
| artifact fields present | **40** |
| constant across all 12 | 23 |
| **varying across all 12** | **17** |

`run_wf_gate._recipe_projection` hashes six artifact fields — `kind`, `feature_cols`,
`feature_norm_kind`, `label_col`, `lookahead_days`, `params`. **All six are in the constant
set.** So the recipe fingerprint `sha256:cfdd6cb8e950da0f` is identical across all 12 **by
construction**, and a gate built on it cannot distinguish them however often it runs. That
17 other fields *do* vary is what makes this a blind spot rather than a correct invariant.

## The evidence that exists and is not read

Among the 17 varying fields:

| field | distinct values | range |
|---|--:|---|
| `oos_mean_ic` | **12** | 0.04246 … 0.05676 |
| `oos_per_fold_ic` | **12** | — |
| `oos_std_ic` | **12** | 0.03781 … 0.04835 |
| `eval_ic` | **12** | 0.04539 … 0.07430 |

**Every booster carries its own out-of-sample IC, and the admission path reads none of it.**

## And why "just promote on `oos_mean_ic`" is the wrong fix

That evidence is **3 folds** per artifact. Best minus worst is
`0.05676 − 0.04246 = 0.01429`, which is **0.51–0.65 standard errors** at n = 3 across the
observed `oos_std_ic` range.

**The per-artifact evidence exists, is ignored, and cannot rank these boosters anyway.** A
gate rewired to promote on `oos_mean_ic` would be ranking on noise — worse than one that
admits it is only checking the recipe. Publishing the first half without the second would
invite exactly that change, so both are asserted by tests.

## A false finding this tool exists to prevent

The artifact's own `config_fingerprint` (`sha256:f8fb2259b…`) **never** equals the stamp's
`candidate_recipe_fingerprint` (`sha256:cfdd6cb8e…`) on any of the 30. That is **correct
behaviour, not a defect**: the first hashes the config — its `config_fingerprint_fields`
carries the watchlist — while the second hashes the model recipe. I checked both
definitions before drawing the conclusion; comparing them would have published a mismatch
that is by design. Two names containing "fingerprint" are not one object, and the report
carries this as a `not_a_finding` field so the next reader does not re-derive it.

`feature_source_contract_keys` is computed inside the gate rather than being an artifact
field, so it is declared as unchecked rather than silently omitted — omitting it without
saying so would overstate the projection's coverage.

## How this joins tonight's other measurements

- `renquant-pipeline`#244: **53 of 53** stamped artifacts carry
  `candidate_artifact_used=false` — every pass is recipe-level.
- orch#712: the same 12 boosters disagree on **35.7%** of the real top decile (median over
  20 sessions), up to 67% in the tail.
- This: the projection is invariant **by construction**, and the discriminating evidence
  sits unread one key away — but is itself too weak to rank on.

Together they say the ensemble/promotion premise fails for a reason none of the three shows
alone: **nothing validates which member serves, the evidence to do so is recorded but
ignored, and that evidence is under-powered even if it were read.**

## Not claimed

That the projection is wrong for its stated purpose — validating a recipe across historical
folds is what it says it does. That any booster is better. That more folds would settle it;
that is a design question this does not answer.

## Tests

11, including both halves of the finding and the false one it forecloses. Suite:
**5195 passed, 2 skipped**, run before the push.
