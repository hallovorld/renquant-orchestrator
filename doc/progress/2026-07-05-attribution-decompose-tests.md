# Attribution decomposition test coverage + zero-price bug fix

**Date:** 2026-07-05
**PR:** (this PR)
**Sprint item:** 107 attribution engine test coverage

## What changed

1. **37 new tests** for `attribution/decompose.py` covering:
   - Full identity sum-check verification
   - All 5 leg computations independently verified
   - All 8 censoring reasons tested
   - Spread proxy estimation
   - Open-MTM position handling
   - Exit-unmatched edge case
   - Diagnostic field population
   - assert_identity enforcement
   - Edge cases (zero prices, large gains, negative returns)

2. **Bug fix:** zero reference/benchmark prices caused `TypeError` in
   decompose_round_trip. `ref_entry_px=0.0` passes the `is None` check
   but `_ret()` returns `None` (division guard), then signal leg tries
   `None - float`. Fixed by treating `0` as missing in the ref/bench
   reason checks. Unlikely in production (no stock trades at $0) but
   the decomposition code should be correct by construction.

## Test count

2255 -> 2292 (+37)

## Round 2 (Codex review — benchmark-side zero-price asymmetry)

The zero-price censoring fix above made `ref_reason` symmetric
(`ref_entry == 0` and `ref_exit == 0` both censor), but `bench_reason`
was left asymmetric: `spy_entry in (None, 0)` was checked, but
`spy_exit` only checked `is None`, not `== 0`. A zero SPY exit price
therefore fed straight into `_ret()`, producing a spurious -100%
benchmark return (`market`/`signal` legs computed a real dollar value
instead of being censored) — the exact defect class the round-1 fix
was meant to eliminate, just on the other side of the same check.

Fixed: `bench_reason` now checks `spy_exit in (None, 0)`, matching
`spy_entry`'s existing check and mirroring `ref_reason`'s symmetric
form. Added `test_zero_spy_entry_censors_market_signal` and
`test_zero_spy_exit_censors_market_signal` to `TestCensoringNoBenchmark`
— confirmed the new spy-exit test fails against the pre-fix code
(computes `-2000.0` instead of censoring to `None`) and passes after.

Test count: 2292 -> 2294 (+2). Full suite: 2291/2293 pass (2
pre-existing, unrelated failures in `test_bundle_consistency_ci_gate.py`
reproduce identically on clean `origin/main`).
