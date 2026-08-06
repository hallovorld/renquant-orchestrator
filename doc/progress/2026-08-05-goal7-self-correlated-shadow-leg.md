# GOAL-7: the momentum model is in PROD, and its shadow diagnostic now measures it against itself

STATUS:   delivered.
WHAT:     ships `ops/renquant104/shadow_leg_independence_probe.py` + 13 tests, which flags any
          shadow leg whose `(kind, artifact_path)` matches a live primary scoring component; live
          run finds 1 self-comparison (`momentum_residual_v0_shadow` serves the same artifact as
          prod's `component[1]`), exit 1.
WHY/DIR:  GOAL-7 ("独立动量模型 → shadow") — the momentum model is actually in PROD (2026-08-04
          operator override, 'z-blend进prod'), so its shadow leg's reported ρ=+0.75 is inflated by
          construction (correlated against a primary that contains it), not evidence the leg
          outperforms the clf shadow leg's ρ=+0.28.
EVIDENCE: today's live log shows both `momentum_residual` invocations (prod component[1] and the
          shadow leg) serving the identical ledger tail row (cutoff 2026-08-02, artifact
          a824c480cd9c...); the probe's live run reports exactly 1 self-comparison for this same
          leg. `[VERIFIED — this session, live decision log + probe run this session]`
NEXT:     `momentum_residual_v0_shadow` should be retired or re-pointed — a
          `renquant-strategy-104` config change (repo boundary), not actioned here; orch#863 shows
          the same 08-04 promotion degraded a second diagnostic the same way.

**Date:** 2026-08-05
**Lane:** GOAL-7 (standalone momentum → shadow)

## Bottom line — the anchor's headline is wrong

The GOAL-7 anchor reads *"独立动量模型**→shadow**"*. Measured `[VERIFIED — this session]`:

**the momentum model is in PRODUCTION.** `strategy_config.json` has
`ranking.panel_scoring.kind = blend` with

```
comp0  panel_ltr          artifacts/prod/panel-ltr.alpha158_fund.json
comp1  momentum_residual  artifacts/momentum/momentum_artifact_ledger.jsonl
```

and today's live run confirms it executing:

```
14:07:11 kernel.panel_pipeline.blend_scorer: load_blend_scorer:
         component[1] momentum_residual verified (ledger tail row 0,
         cutoff 2026-08-02, artifact a824c480cd9c564b8cb, fp momentum-v0-fd65161a20b29314)
```

The cause is recorded in prod's own config, in the operator's words:
`OPERATOR OVERRIDE 2026-08-04 (verbatim: 'z-blend进prod' / '整本切换')`.

## The consequence nothing flagged

The daily decision line reports two shadow legs:

```
SHADOW[topdecile_clf_blend_leg]     top10∩prim=2/10  ρ=+0.28  n=94
SHADOW[momentum_residual_v0_shadow] top10∩prim=6/10  ρ=+0.75  n=84
```

Read naively: the momentum leg agrees far more strongly with prod. But
`momentum_residual_v0_shadow` serves
`artifacts/momentum/momentum_artifact_ledger.jsonl` — **the same path as prod's
`component[1]`** — and today's log shows both invocations serving the same
artifact digest:

```
2 × momentum_residual: serving verified ledger tail row 0 (cutoff 2026-08-02, artifact a824c480cd9c…)
```

**That ρ=+0.75 is the momentum model correlated against a primary that contains
the momentum model.** It is inflated by construction. The 0.75-vs-0.28 gap is not
evidence that one leg is better — part of it is arithmetic.

## The bug I wrote and caught in the same session

My first identity check compared `(kind, artifact_path, expected_config_fingerprint)`.
It returned **`False`** for `momentum_residual_v0_shadow` — *independent* — and I
was about to accept that.

The reason is that **components declare `expected_config_fingerprint` and shadow
legs do not.** So the comparison was testing *which fields happen to be filled
in*, not which model runs, and it returned "independent" for the exact leg the
check exists to catch. A guard whose subject is not the object you assume passes
forever.

Identity is now `(kind, artifact_path)`, and a test pins that adding the
fingerprint back would break it.

## What this does NOT establish

- **Not that the promotion was wrong.** Moving the z-blend into prod may be
  entirely correct; it was an explicit operator decision. What is missing is the
  step that should have retired or re-pointed the shadow leg of the promoted model.
- **Not that the momentum model is bad**, and not that the clf leg's ρ=+0.28 is
  meaningful. The finding is only that **the two numbers must not be ranked
  against each other**, because one of them is not a comparison between two
  different things.
- Arm B's preregistered evidence lane remains **0 of 30 matured BULL_CALM dates**
  (measured 2026-08-05, `GENESIS_ONLY_NO_CADENCE_YET`). That clock is unchanged
  by any of this.

## Delivered

`ops/renquant104/shadow_leg_independence_probe.py` + 13 tests. Flags any shadow
leg whose `(kind, artifact_path)` matches a primary scoring component. Handles
the non-blend case (a config scoring from a single `artifact_path` is treated as
one component, so self-comparison stays detectable there too), treats a leg with
no declared artifact as its own state rather than independent, and refuses
(exit 2) on a missing `panel_scoring` rather than reporting every leg as
independent from a primary it could not read.

Live: **1 self-comparison** (`momentum_residual_v0_shadow`), exit 1.

## Next

1. `momentum_residual_v0_shadow` should be retired or re-pointed — it is a
   `renquant-strategy-104` config change (repo boundary), not actioned here.
2. Same shape as orch#863 (`_mom` lane became a copy of prod on the same
   promotion). One 08-04 promotion silently degraded **two** diagnostics; both
   were found five rounds later by looking at correlations, not by an alarm.
