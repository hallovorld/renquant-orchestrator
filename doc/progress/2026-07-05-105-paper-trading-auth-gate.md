# 105 Paper Trading Authorization Gate

**Date:** 2026-07-05
**PR:** feat/105-paper-auth-gate
**Status:** Ready for review

## Summary

Adds a paper-mode authorization pathway to the 105 intraday Stage-2 arming
gate. Paper trading carries zero capital risk, so the shadow-session evidence
floor is lowered from 5 to 1 while preserving the full safety gate structure
(authorization file, canary allowlist, loss budget, kill switch, expiry).

## Changes

### `intraday_live_executor.py`
- Added `MIN_SHADOW_SESSIONS_CLEAN_PAPER = 1` constant
- Added `paper: bool = False` parameter to `Stage2Authorization.from_payload()`
- Shadow-session validation uses `MIN_SHADOW_SESSIONS_CLEAN_PAPER` when
  `paper=True`, `MIN_SHADOW_SESSIONS_CLEAN` (5) otherwise
- `load_stage2_authorization()` and `resolve_stage2_arming()` accept and
  thread through the `paper` parameter

### `intraday_session_runner.py`
- Added `PAPER_PREREG_ID = "rq105-paper-canary-prereg-v1"` constant for
  paper-mode section 9.4 authorization files
- Added `paper: bool = False` field to `SessionRunnerConfig`
- `_evaluate_arming()` passes `paper` through to `resolve_stage2_arming()`

### `tests/test_paper_trading_enablement.py` (23 tests)
- Constant sanity checks (paper floor = 1, live floor = 5 unchanged)
- Paper mode accepts 1 session, accepts 5, rejects 0
- Live mode still rejects 1 session (default behavior unchanged)
- Paper mode still enforces: allowlist, loss budget, authorized_by, expiry,
  replay audits (safety structure preserved)
- `load_stage2_authorization` paper threading
- `resolve_stage2_arming` paper threading (gate 2 valid/invalid)
- `SessionRunnerConfig.paper` default and set
- Section 9.4 with `PAPER_PREREG_ID` accepted / missing file fails

## Safety invariants preserved

1. **Default behavior unchanged**: `paper=False` everywhere by default;
   `MIN_SHADOW_SESSIONS_CLEAN = 5` for live mode
2. **Full gate structure preserved**: paper mode still requires authorization
   file, allowlist, loss budget, expiry, replay audits, kill switch absent
3. **No production paths written**: code-only changes
4. **No branch protection bypassed**

## Test results

2647 passed, 3 skipped, 0 failures (full suite)
