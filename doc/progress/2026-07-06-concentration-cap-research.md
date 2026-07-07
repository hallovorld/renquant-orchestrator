# 2026-07-06 — Concentration cap research proposal

**PR**: research design for asymmetric concentration management

## What

Design document proposing a parameter sweep to determine whether entry sizing
cap (`max_concentration`) should differ from drift tolerance, and whether
`top_up_threshold` is calibrated correctly at the current 12% cap level.

## Why

MU at 9.2% weight, model rank=0.617, er=+4.59% — but TopUp blocked because
`kelly_target(12%) - current(9.2%) = 2.8% < threshold(5%)`. The 12% cap was
set by operator mandate without A/B evidence. Prior research covered σ-horizon
(inert) and trim on/off (OFF wins), but never the cap level itself or the
entry/drift asymmetry.

## Scope

- Design doc only — no code changes in this PR
- Proposes: 3D parameter sweep (entry_cap × drift_cap × topup_threshold)
- Builds on existing findings: σ-horizon A/B (06-03), trim A/B (04-24)
- Execution requires 1 pipeline PR (drift_cap config) + 1 sweep script
