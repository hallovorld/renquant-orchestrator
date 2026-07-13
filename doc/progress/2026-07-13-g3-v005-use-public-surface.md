# fix(V-005): use pipeline public surface instead of kernel internals

**Date**: 2026-07-13
**PR**: orchestrator fix/v005-use-public-surface (#513)
**Depends on**: pipeline #197 (`fix/v005-public-surface`, unmerged as of
this pass — validated locally against its actual branch content, see
"Cross-repo validation" below)

## Change

`native_context_hydration.py`'s 5 `from renquant_pipeline.kernel.*`
imports are now split by ownership, per codex's round-2 review of this PR:

1. `LocalStore`, `HoldingState`, `RegimeState` → `renquant_pipeline.public`
   (pipeline#197's lazy re-export surface — unchanged from round 1, codex
   confirmed this part was fine).
2. `_last_completed_nyse_session` (pipeline-private helper) →
   `renquant_common.market_calendar.last_completed_session` — the
   canonical shared calendar contract already exists; `_required_closed_session`
   now catches `CalendarUnavailableError`/`ValueError` from that call and
   falls back to the same weekday approximation the private helper's
   broad `except Exception → None` used to trigger.
3. `LoadUniverseJob`/`UniverseContext` (pipeline execution internals) →
   **removed the direct construction entirely**. The universe-load block
   now calls `renquant_pipeline.public.load_universe(config=..., strategy_dir=...,
   broker_name=..., held_tickers=..., as_of_date=...) -> UniverseLoadResult`,
   a new narrow operation added to pipeline#197 in this same pass. It runs
   the real `LoadUniverseJob` chain internally and returns only
   `models`/`rejections` — the Job/Context objects and their lifecycle
   never cross the repo boundary.
4. `train_gbdt.py` is untouched (out of scope per codex — separate
   wrong-repo training-ownership issue, not part of V-005's import-boundary
   fix).

Added consumer-contract tests in `tests/test_native_context_hydration.py`:
end-to-end `hydrate_pipeline_context` run against real `models/<ticker>`
artifact fixtures proving `load_universe` admits/rejects tickers
correctly; an AST-based static check that the module never imports
`kernel.pipeline.job_universe`; and two tests proving
`_required_closed_session` actually calls
`market_calendar.last_completed_session` (spy) and falls back correctly
when it raises `CalendarUnavailableError`.

## Cross-repo validation

pipeline#197 is unmerged, and CI's sibling checkout step pulls
`hallovorld/renquant-pipeline`'s default branch, so GitHub Actions on this
PR will stay red until #197 merges to pipeline `main` — expected for a
dependent PR, not a new bug. Locally, both repos were checked out as
isolated git worktrees; the orchestrator worktree's `PYTHONPATH` pointed
`renquant_pipeline` at the actual pipeline#197 worktree's `src/` (not a
guess at its shape), confirming `renquant_pipeline.public.load_universe`
imports and behaves as this PR expects. Full orchestrator suite: 3881
passed, 5 skipped (pre-existing, unrelated) against that pairing; the 14
tests that fail in this scratch-worktree layout (`test_shadow_ab_daily_script.py`,
`test_cli.py::test_parking_sleeve_cli_computes_allocation`) do so
identically on the pre-change commit too — they assume sibling repos are
git checkouts at literal relative paths next to this repo, which the
isolated worktree layout doesn't provide; unrelated to this change.

## Motivation

V-005 (architecture audit): orchestrator's direct imports from pipeline
kernel internals create fragile coupling, and constructing
`LoadUniverseJob`/`UniverseContext` directly would have promoted a
pipeline execution internal to a permanent cross-repo contract. The
public surface (types) + `load_universe` (operation) decouple
orchestrator from kernel module layout and Job/Context lifecycle changes.
