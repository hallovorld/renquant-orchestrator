# 2026-07-07 — Rank floor calibration sweep design

**PR**: design + data for the #1 cash-drag lever

## What

Design doc for a 1D sweep over the VetoWeakBuys floor mechanism. Live data
shows the rank floor causes **81.6%** of all candidate blocks — 10× more
than any other gate. The `adaptive_quantile` mode already exists in code
(job_panel_scoring.py:1721) but has never been activated.

## Key data

- 80.7% avg cash, 81.6% of blocks from VetoWeakBuys
- Current floor ≈ 0.565 (mean+1σ), admits only 22.7% of candidates
- Passing candidates avg μ = 0.0343, failing avg μ = 0.0058
- The fix is already implemented in pipeline code (adaptive_quantile mode)

## Scope

- Design doc only — no code/behavior changes
- 6 variants × 3 seeds × 27-month OOS (~1-2h to run)
- No pipeline code changes needed (config-only sweep)
