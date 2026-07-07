# 2026-07-07 — Parallelize concentration cap sweep

**PR**: orchestrator fix

## What went wrong

The concentration cap sweep (`scripts/run_concentration_cap_sweep.py`) was
designed to run 76 variants × 3 seeds **serially** on a 14-core machine.
Each variant takes ~2.5 hours → total wall-clock ~190 hours (~8 days).

This is inexcusable. The variants are independent — they share the same OHLCV
data and differ only in Kelly sizing config. There is zero data dependency
between them. Parallel execution was the obvious design from day one.

Additionally, OHLCV data (~142 symbols) was re-fetched inside `execute_variant`
on every call — 76 identical fetches of the same data.

## Root cause

Laziness and insufficient design review. I wrote the simplest possible loop
(`for variant in variants: execute(variant)`) without considering that this
script's entire purpose is a large-scale parameter sweep. A sweep that takes
8 days to complete is useless for iterating on cash-drag research.

## Fix

1. **Hoist OHLCV fetch**: new `prefetch_ohlcv()` loads data once, passes the
   bundle to all variant executions via `ohlcv_bundle` parameter.
2. **Add `--workers` flag**: defaults to `ncpu - 2` (= 12 on this machine).
   Uses `concurrent.futures.ProcessPoolExecutor`.
3. **Preserve serial fallback**: `--workers 1` runs the old serial loop
   (useful for debugging).
4. **Control arms unchanged**: incumbent + A/A still run serially first
   (they must complete before candidates can be evaluated).

## Expected improvement

- **Serial**: ~190 hours (8 days)
- **12 workers**: ~16 hours (~1 day) — 12× speedup
- OHLCV fetch: from 76× to 1× (~5 min saved per variant = ~6 hours total)

## Scope

`scripts/run_concentration_cap_sweep.py` only. No behavioral change to
backtest logic, verdict criteria, or result format.
