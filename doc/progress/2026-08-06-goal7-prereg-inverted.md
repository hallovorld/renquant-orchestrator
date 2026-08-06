# GOAL-7: the preregistered evidence lane was built to gate a deployment that had already happened

**Date:** 2026-08-06
**Lane:** GOAL-7 (standalone momentum → shadow)

## The timeline, from the ledger's own fields `[VERIFIED — this session]`

```
2026-08-02T18:26:23Z   momentum_artifact_ledger.jsonl  row_index 0, prev_row_sha null
                       kind = momentum_residual_v0
                       cutoff_date = 2026-08-02
                       effective_train_cutoff_date = 2026-07-02  (21d embargo)
                       artifact_content_sha256 = a824c480cd9c564b…
                       -> the model's FIRST and, today, ONLY artifact

2026-08-04             strategy_config.json _zblend_fullbook_note:
                       "OPERATOR OVERRIDE 2026-08-04 (verbatim: 'z-blend进prod' /
                        '整本切换'): prod primary scorer switched to the
                        z(prod)+z(slow momentum) blend"
                       -> promoted into the PRODUCTION scorer

2026-08-05/06          Arm B accrual: 1 ledger row, 0 of 30 matured BULL_CALM
                       dates, STATE = GENESIS_ONLY_NO_CADENCE_YET
```

**Two days from first artifact to production primary scorer.** The artifact
serving live decisions today (`a824c480…`) is that same genesis row.

## What this does to GOAL-7's acceptance criterion

GOAL-7's stated goal is *"独立动量模型 → shadow"*. The model is in **prod**. So the
AC as written can no longer be met or failed — it has been overtaken.

More consequentially, **Arm B has inverted**. It was preregistered as the evidence
that would decide whether this model earned deployment; it now measures a model
that is already deciding live trades. Its 0/30 is no longer *"not yet ready to
deploy"* — it is *"deployed, and the evidence is still 30 observations away"*.
At a weekly cadence that remains a **2027** horizon.

## This is not a process violation, and saying so would be wrong

The promotion is recorded verbatim as an **operator override**, in the operator's
own words, in the config. Under the standing full-delegation arrangement that call
is the operator's to make, and they made it explicitly rather than by drift. No
agent bypassed a gate here.

What is worth naming is the **state that results**: a preregistered evidence lane
whose purpose has changed from gate to monitor, without the goal's AC being
restated to match. That is exactly the condition my own HARD rule exists for —
*no delivery claim without a measurable AC met* — and right now GOAL-7 has no AC
that is both current and checkable.

## The compounding effect, already measured

Two other findings this session are consequences of the same 08-04 promotion:

- **orch#863** — `shadow_blend_momentum`, built to shadow the z-blend, became
  byte-identical to prod (0 of 21 score-affecting keys differ) the moment the
  blend was promoted.
- **orch#864** — `momentum_residual_v0_shadow` now serves the same artifact as
  prod's `component[1]`, so its reported ρ=+0.75 is a self-comparison.

**One promotion, three diagnostics degraded** — the shadow lane, the shadow leg,
and the prereg — and none of them alarmed. All three were found by inspection
days later.

## What this does NOT establish

- **Not that the promotion was wrong.** The z-blend may well be the right prod
  scorer; nothing here measures its skill.
- **Not that the momentum model is bad or good.** Its only evidence is one
  artifact and a shadow ρ that orch#864 showed is not an independent comparison.
- **Not that a 21-day embargo + 08-02 cutoff is stale.** `effective_train_cutoff_date`
  of 2026-07-02 is the *designed* consequence of `cutoff_embargo_days = 21`, not
  drift, and I have not evaluated whether 21 days is the right embargo.

## Next

GOAL-7 needs a **restated acceptance criterion for a model that is already live**.
The prereg's Arm A/Arm B design answers "should we deploy"; the live question is
now "is it contributing, and what would make us take it out". Those need different
evidence, and the second one has no owner today.
