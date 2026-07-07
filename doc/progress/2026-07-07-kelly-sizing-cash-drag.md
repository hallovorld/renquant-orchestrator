# 2026-07-07 — Kelly sizing is the binding constraint for cash drag

**PR**: orchestrator design doc

## What

Corrected cash-drag root-cause analysis. 62% cash is NOT caused by
VetoWeakBuys filtering (enough candidates pass — 6+ daily). The binding
constraint is Kelly `fractional: 0.3` → avg kelly_target = 6.9% → even
8 full slots deploy only 55.6%.

## Why (correction)

Earlier analysis (PR #408) incorrectly identified VetoWeakBuys rank floor
as the #1 cash-drag lever based on block counts (81.6% of blocks). But
block counts measure candidate scarcity, not deployment shortfall. The
actual buy funnel on 07-06 shows 6 candidates passing all gates with
only 2 open slots — the bottleneck is SIZING, not FILTERING.

## Key findings

- `fractional: 0.3` → half-Kelly would be 0.5 (institutional standard)
- 0.3 → 0.5 = deployment from 41.7% → 68.7% (+27pp)
- At frac≥0.5, `max_concentration=12%` becomes the binding cap
- `top_up_threshold=5%` blocks 3 positions from top-up (gap 2-3%)

## Proposed

2D sweep: fractional × max_concentration (12 variants × 3 seeds)
then secondary 1D sweep on top_up_threshold at winning point.

## Scope

Design doc only. No behavior changes.
