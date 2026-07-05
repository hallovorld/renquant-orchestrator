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
- `_check_section_9_4()` returns `(authorized, is_paper)` tuple — `is_paper`
  is derived from the §9.4 file's `prereg_id`, not from any caller-supplied
  boolean
- `run_session()` evaluates §9.4 FIRST, derives `config.paper` from it, THEN
  evaluates the quintuple gate — so the evidence-floor relaxation and the
  execution backend are coupled through the same authoritative artifact
- `_run_live()` verifies `isinstance(port, PaperBroker)` before constructing
  the executor — fail-closed on mismatch

### `tests/test_paper_trading_enablement.py` (28 tests)
- Constant sanity checks (paper floor = 1, live floor = 5 unchanged)
- Paper mode accepts 1 session, accepts 5, rejects 0
- Live mode still rejects 1 session (default behavior unchanged)
- Paper mode still enforces: allowlist, loss budget, authorized_by, expiry,
  replay audits (safety structure preserved)
- `load_stage2_authorization` paper threading
- `resolve_stage2_arming` paper threading (gate 2 valid/invalid)
- `SessionRunnerConfig.paper` default and set
- Section 9.4 tuple return: paper prereg → (True, True), missing → (False, False),
  non-paper prereg → (True, False), not-authorized → (False, False),
  missing prereg_id → (False, False)
- Port/paper mismatch fail-closed + genuine PaperBroker passes

## Design: paper mode derived from §9.4, not from caller

Codex review round 2 identified that `paper` was a free boolean on the config,
decoupled from the actual execution backend. A caller could set `paper=True`
(accepting K=1 threshold) while pointing `port_factory` at a real broker.

Round 3 fix: `paper` is now DERIVED from the §9.4 authorization file's
`prereg_id`. The ordering is:

1. Read §9.4 → if `prereg_id == PAPER_PREREG_ID`, set `config.paper = True`
2. Evaluate quintuple gate (uses derived `paper` for K threshold)
3. If armed + §9.4 authorized → `_run_live()`
4. `_run_live()` verifies `isinstance(port, PaperBroker)` — fail-closed

This means:
- The operator controls paper mode by writing the §9.4 file with `PAPER_PREREG_ID`
- No separate CLI flag or config field is needed for paper vs live
- The evidence-floor relaxation is mechanically tied to the authorization artifact
- A port-type mismatch is caught at runtime before any order

## Safety invariants preserved

1. **Default behavior unchanged**: `paper=False` everywhere by default;
   `MIN_SHADOW_SESSIONS_CLEAN = 5` for live mode
2. **Full gate structure preserved**: paper mode still requires authorization
   file, allowlist, loss budget, expiry, replay audits, kill switch absent
3. **Coupled source of truth**: `paper` derived from §9.4 prereg_id, not
   a free boolean — impossible to decouple from the authorization artifact
4. **Runtime port verification**: `isinstance(port, PaperBroker)` in `_run_live()`
   prevents a misconfigured paper flag from reaching a real broker
5. **No production paths written**: code-only changes
6. **No branch protection bypassed**

## Test results

2712 passed, 2 skipped, 0 failures (full suite)
