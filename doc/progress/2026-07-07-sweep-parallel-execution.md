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

## Round 2 (codex review)

STATUS: fixed
WHAT: `_run_one()`, the per-variant worker submitted to `ProcessPoolExecutor`,
was defined as a function nested inside `main()`, closing over `subrepo_root`,
`strat_dir`, `args`, `inc_turnover`, and `ohlcv_bundle` rather than taking them
as explicit parameters.
WHY-DIR: macOS (and Windows) default `multiprocessing` to the `spawn` start
method, which requires the submitted callable to be resolvable by qualified
name in the freshly-started child process — a nested function's
`__qualname__` contains `<locals>` and pickle cannot reconstruct it. CI
almost certainly runs on Linux, where the default start method is `fork`
(the child inherits the parent's memory directly, so a closure works by
accident) — meaning the `--workers > 1` path was silently broken on the
actual target machine (macOS, per this repo's dev environment) even though
CI stayed green.
EVIDENCE: renamed the worker to module-level `_run_variant_worker()`, taking
every dependency (`subrepo_root`, `strategy_dir_path`, `start`, `end`,
`initial_cash`, `manifest_path`, `incumbent_turnover_annualized`,
`ohlcv_bundle`) as an explicit keyword argument — no closure capture.
Verified directly in this repo's own dev environment (confirmed via
`multiprocessing.get_start_method()` → `spawn` on this Darwin/arm64 machine,
i.e. this genuinely is the platform codex was worried about, not a
theoretical concern): `pickle.dumps(_run_variant_worker)` succeeds, and a new
end-to-end test submits the real worker through a real
`ProcessPoolExecutor(mp_context=multiprocessing.get_context("spawn"))` and
confirms dispatch + result retrieval complete (surfacing the expected
`FileNotFoundError` from a deliberately-missing config path, not a
`PicklingError`). All 4 new tests in `TestParallelWorkerPicklability`
confirmed to fail against the pre-fix nested closure
(`AttributeError: module has no attribute '_run_variant_worker'`) and pass
after. Full suite: 3030/3035 (5 pre-existing failures from a missing
`cvxpy` dependency in this environment, confirmed identical on the
unmodified pre-fix checkout — unrelated to this change).

Investigated the secondary design concern (the OHLCV bundle is re-serialized
into every task submitted to the pool, once per candidate variant, since
`ProcessPoolExecutor.submit` pickles all arguments per-call). Could not
measure the real bundle size in this environment (no live market-data
checkout / real `strategy_config.sim_kelly_ab_admoff.json` present here), so
did not implement a `ProcessPoolExecutor(initializer=...)`-based per-worker
cache — that would trade the current, easy-to-reason-about explicit-argument
design for a global-state pattern, and is only worth that tradeoff if
serialization overhead is actually significant next to each variant's real
cost (a full 3-seed walk-forward backtest, likely tens of seconds to minutes
each). Left as an explicit, named follow-up rather than silently deferred:
if a real profiling run of the 75-variant grid shows OHLCV
pickling/unpickling is a meaningful fraction of total wall-clock, move the
bundle into a `ProcessPoolExecutor(initializer=..., initargs=(...))`-set
per-process global instead of a per-task argument.
NEXT: none for the picklability fix (blocking). OHLCV-reserialization
optimization remains a candidate follow-up, not implemented here.
