# 2026-07-07 — Design: resolve 104/105 cash drag

**PR**: design RFC (docs only, no behavior change)

## What

Evidence-first execution plan for cash-drag remediation across 104 and 105.
Four phases in strict order: fractional shares → concentration cap tuning
(data-driven, pending sweep) → parking sleeve (SGOV) → exposure knobs.

## Why

104 runs 54-76% cash. The measured binding constraint is whole-share
quantization on high-price names (BLK/AVGO/GS blocked at $0), not slot
count or concentration caps. Prior attempts mixed mechanical drag with
policy drag, making attribution impossible.

## Key decisions

1. Fractional shares first (sizing fidelity, the measured root cause)
2. Concentration cap changes only if the running 75-variant sweep shows
   a dominant configuration (7-criterion unanimity × 3 seeds)
3. Parking sleeve = SGOV-first (carry without adding benchmark beta)
4. 105 = compatibility + instrumentation only (no live deployment)
