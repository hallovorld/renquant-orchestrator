# 2026-07-07 — Fix rq105 shadow-serving argparse crash

**PR**: orchestrator fix

## Problem

`shadow_realtime_serving` CLI crashes at argparse with:
```
error: the following arguments are required: --feature-snapshot-json
```

The shell script (`run_shadow_serving.sh`) never passes this arg because
no producer for the feature snapshot file exists.

## Fix

Make `--feature-snapshot-json` optional (`required=True` → `default=None`).
When absent, use batch_scores tickers as a bootstrap daily_features mapping
(observe-only mode — no feature provenance, but the pipeline doesn't crash
at argument parsing).

## Remaining issue

Even with the argparse fix, shadow-serving still exits 2 ("no scorer
wired"). The CLI requires an injected `ShadowScorer` with a
`feature_matrix_fn` that builds the alpha158 feature matrix from a
MarketSnapshot. This is Stage-3 pipeline wiring that can't be done in the
shell script — it needs a Python entry point that loads the pinned model
artifact and constructs the feature matrix builder.

This is NOT blocking 105's core functionality: the session-scheduler (the
real-time decisioning component) works independently. Shadow-serving is an
observe-only data collector for batch-vs-realtime comparison (#221).

## Scope

`src/renquant_orchestrator/shadow_realtime_serving.py` — argparse change only.
