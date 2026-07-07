# 2026-07-07 — Cash drag parameter sweep (experiment design)

**PR**: orchestrator

## What

OAT (one-at-a-time) parameter sweep to identify the binding constraint
for 62% cash through backtest evidence, not arithmetic projection.

9 candidate variants + 1 A/A control, each changing exactly ONE parameter.
Frozen seeds {42,43,44}. ~30 sim runs.

## Why

Earlier analyses jumped to conclusions without backtest validation:
- First claimed VetoWeakBuys was #1 (wrong — enough candidates pass)
- Then claimed Kelly fractional was #1 (plausible but unverified)
- Neither had backtest evidence

This sweep tests ALL major hypotheses simultaneously and lets the data
decide which parameter actually matters.

## Parameters tested

H1: kelly.fractional (0.4, 0.5, 0.7)
H2: kelly.max_concentration (0.15, 0.20)
H3: kelly.top_up_threshold (0.02)
H4: buy_floor mode (adaptive_quantile q=0.70)
H8: qp_turnover_max (0.25)

## Scope

Experiment infrastructure + design doc. No behavior changes.
