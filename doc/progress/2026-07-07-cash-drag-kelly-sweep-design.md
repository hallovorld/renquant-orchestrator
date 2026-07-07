# 2026-07-07 — Cash drag Kelly fractional sweep design

**PR**: orchestrator design doc

## What

Screening sweep for `kelly.fractional` parameter: 5 levels (0.2–0.7)
plus A/A control. 18 sim runs total.

## Why

`fractional` was changed 0.5→0.3 on 06-11 as a coupled change with
`sigma_horizon 252→60`. The 0.3 value was set by arithmetic projection,
not backtest. Whether it is optimal under the new sigma is unknown.

Complements the merged concentration-cap sweep (#405) which covers
the orthogonal max_concentration/topup/trim dimensions.

## Scope

Design doc only. No code, no behavior changes.
