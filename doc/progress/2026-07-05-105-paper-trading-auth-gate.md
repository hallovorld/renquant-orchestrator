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

## Round 2 (Codex review — capital-safety desync + operator-entrypoint gap)

Codex held this PR on two issues:

1. **No real operator entrypoint** — `SessionRunnerConfig.paper` was only ever
   constructed in tests; `scripts/rq105_smoke_test.py` is explicitly
   read-only wiring verification, not a real session invocation. Confirmed
   by an exhaustive repo-wide search: no CLI/config/bridge path exists that
   would ever set `paper=True` in an actual run. Since building a genuine
   operator-facing CLI flag is substantial new work beyond this PR's two
   findings, narrowed the PR body/scope explicitly to "internal plumbing
   only, not yet operator-usable" per Codex's explicit fallback, with the
   real entrypoint tracked as separate follow-up work.

2. **The relaxed floor was keyed off a free boolean, not the actual execution
   backend (the important one — a real capital-safety gap).** `_evaluate_arming()`
   passed `self.config.paper` straight into `resolve_stage2_arming()` to
   relax the shadow-session floor from 5 to 1, but nothing checked that
   `port_factory()` — called later, inside `_run_live()` — actually
   constructs a `PaperBroker`. A caller could set `paper=True` (accepting
   the relaxed evidence bar) while still pointing at a real live-submitting
   port, and nothing would catch the mismatch before order submission.

   Fixed with a last-line, fail-closed check: `_run_live()` now verifies
   `isinstance(port, PaperBroker)` immediately after `port = self.port_factory()`
   and *before* constructing `LiveTickExecutor` — any mismatch raises
   `RuntimeError` rather than proceeding. This doesn't change WHEN the
   evidence floor is relaxed (still at arming time, from the config flag),
   but it makes it structurally impossible for a `paper=True` misconfiguration
   to ever reach a real order submission: the declared intent (`config.paper`)
   is now independently verified against the actual constructed backend
   before any capital is at risk.

   Also fixed `_check_section_9_4()`, which previously accepted *any* truthy
   `prereg_id` string — meaning `PAPER_PREREG_ID`'s claimed paper-specific
   authorization semantics were undocumented in practice. Now requires an
   exact match against `PAPER_PREREG_ID` when `config.paper` is set (non-paper
   mode keeps the original, more permissive any-truthy-string contract).

### New tests (4)

- `test_paper_rejects_mismatched_truthy_prereg_id` / `test_non_paper_accepts_any_truthy_prereg_id`
  — pins the `_check_section_9_4()` fix, confirmed to genuinely fail
  against the pre-fix code (`git stash` comparison: old code returned
  `True` for a mismatched-but-truthy prereg_id).
- `test_paper_true_with_non_paper_port_fails_closed` — constructs a
  `paper=True` config with a `port_factory` returning a non-`PaperBroker`
  stand-in and confirms `_run_live()` raises `RuntimeError` with a message
  naming the mismatch. Confirmed via `git stash` that pre-fix code does
  NOT raise this error — it proceeds past port construction and crashes
  later with an unrelated `AttributeError` deep in `begin_session()`'s
  reconciliation step (a real behavioral difference, proving the new
  check fires before reaching that point).
- `test_paper_true_with_real_paper_broker_does_not_raise_the_coupling_check`
  — confirms a genuine `PaperBroker` port does NOT trip the new mismatch
  check (uses a thin test-only `PaperBroker` subclass adding `open_orders()`,
  since `PaperBroker` not implementing the full `BrokerPort` protocol is a
  separate, pre-existing gap unrelated to this fix — noted but not fixed
  here, out of scope for this PR).

Full suite: 2649 passed, 3 skipped, 2 failures (`test_bundle_consistency_ci_gate.py`
— confirmed pre-existing and unrelated, reproduces identically on clean
`origin/main`). `[VERIFIED — pytest + git stash comparison, this session]`
