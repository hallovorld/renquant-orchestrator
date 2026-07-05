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
