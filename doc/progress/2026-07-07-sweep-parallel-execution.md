# 2026-07-07 — Parallelize concentration cap sweep (v2)

**PR**: orchestrator fix — supersedes closed #414

## What

Parallelize the 75-variant × 3-seed concentration cap sweep using
`ThreadPoolExecutor` instead of the previous serial loop.

## Changes

1. **`prefetch_ohlcv()`** — loads OHLCV data (142 symbols) ONCE, shared
   by all variants. Previously each of the 76 `execute_variant()` calls
   loaded the same data independently.

2. **`--workers N`** CLI arg (default: `cpu_count - 2`). `--workers 1`
   preserves serial execution for debugging.

3. **`ThreadPoolExecutor`** for the grid variant loop. Threads share the
   pre-fetched OHLCV bundle in-process — no serialization overhead.

## Why ThreadPoolExecutor (not ProcessPoolExecutor)

Codex review of v1 (#414) correctly identified two issues:
- **Pickle failure**: ProcessPoolExecutor on macOS uses `spawn`, which
  requires picklable callables. The v1 nested worker function was not
  picklable.
- **Serialization overhead**: ProcessPoolExecutor would serialize the
  ~500MB OHLCV bundle into each child process.

ThreadPoolExecutor avoids both:
- All callables are module-level (picklable anyway for clean design).
- Threads share memory — zero serialization cost for the OHLCV bundle.
- Backtest work is dominated by numpy/pandas C extensions that release
  the GIL, so thread-level parallelism is effective.

## Expected speedup

- OHLCV fetch: 76× → 1× (eliminated redundant loads)
- Variant execution: serial → `cpu_count - 2` concurrent threads
- On 14-core machine: ~8 days → estimated ~12-18 hours
