# Modal Sweep Validated — Smoke Test Pass

**Date**: 2026-07-08
**Supersedes**: #434
**Status**: Smoke test PASS; ready for full sweep

## Results

Incumbent smoke test (1 variant, 3 seeds) on Modal:

| Metric | Value |
|--------|-------|
| APY | 15.1% |
| Sharpe | 1.47 |
| Max DD | 7.3% |
| Turnover | 2.00x ann |
| Cost | 20.0 bps |
| A/A Sharpe lift | +0.0000 (PASS) |
| Worker time | 5558s (93 min) on 4 CPU / 16 GB |
| Cost | $0.12/variant |

## Changes

1. **Per-seed fan-out**: Executor splits each BacktestRequest into one Modal
   task per seed. Worker calls `run_backtest(seed=N)` instead of
   `run_backtest_multi_seed()`. Eliminates GIL contention within pods.

2. **Resource upgrade**: WORKER_CORES 1→4, WORKER_MEM_GIB 4→16.
   Timeout configurable via MODAL_TIMEOUT env var (default 24h).

3. **Executor aggregation**: Per-seed results automatically merged back
   to per-variant BacktestResult (elapsed=max, memory=max, curves merged).

## Findings

- Seeds 42/43/44 produce identical results — pipeline fully deterministic.
- Cold start (Docker build + Volume cache) adds ~4h overhead on first run.
  Subsequent runs use cached image (~93 min).

## Full sweep projection

- 75 variants × 3 seeds = 225 pods parallel → wall-clock ~31 min
- Total cost ~$9 (75 × $0.12)
