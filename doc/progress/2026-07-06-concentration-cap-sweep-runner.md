# 2026-07-06 — Concentration cap sweep runner

**PR**: sweep script for #403 research design

## What

`scripts/run_concentration_cap_sweep.py` — 2D parameter sweep over
`max_concentration × top_up_threshold` using the existing 27-month OOS sim
infrastructure. 15 variants × 3 seeds = 45 sim runs.

## Grid

- entry_cap: {8%, 10%, 12%, 15%, 20%}
- topup_threshold: {2%, 3%, 5%}
- trim: OFF (fixed — 04-24 A/B confirmed)

## Status

Script ready for execution. Dry-run validated. Estimated wall clock ~2-4h
(serial, OMP_NUM_THREADS=1 for torch safety).
