# 2026-07-07 Modal cloud executor runtime fixes

## What

Fixed 7 issues preventing the Modal cloud executor from running backtest
variants remotely. The executor now successfully dispatches to Modal workers
with correct code, data, and artifact paths.

## Changes

### modal_app.py — worker at module scope
- Moved `run_variant_remote` from a nested `@app.function` in executor to a
  module-level `@app.function` in `modal_app.py`. Eliminates `serialized=True`
  pickle serialization that caused `DeserializationError` (remote container
  lacks the `renquant_orchestrator` package).
- Added `/data/app` to `sys.path` so `from sim.runner import ...` resolves
  correctly (previously only added subdirs like `/data/app/sim`).
- Added `cvxpy`, `pydantic`, `ngboost`, `lightgbm` to container image
  (indirect deps of `kernel/`, `adapters/`, `training_panel/`).

### bundle.py — complete dependency set
- Added `adapters/` and `training_panel/` to bundled strategy-dir packages
  (required by `sim/runner.py` and `kernel/walk_forward/loader.py`).

### sync_data.py — Volume path fix
- Fixed `put_file` remote path from `/data/{rel_path}` to `/{rel_path}`,
  eliminating double `/data/data/...` on the Volume (mount point already
  provides `/data`).

### run_sweep_modal.py — artifact staging
- Artifacts now staged directly into `bundle_dir/kernel/artifacts/...` instead
  of a separate Volume label. Avoids symlink-based path mapping that was
  rejected by `manifest_uri_resolver`'s anti-escape check.
- Fixed `manifest_path` variable reference (`args.manifest_path`).

### modal_executor.py — cleanup
- Removed 170-line `_remote_worker` function (moved to `modal_app.py`).
- Removed unused imports.
- Simplified `execute_batch` to import and call global `run_variant_remote`.

## Issues fixed (in order of discovery)
1. `DeserializationError` — `serialized=True` pickle fails without local module
2. Volume double `/data` path — `put_file` semantics are Volume-relative
3. `No module named 'sim'` — `sys.path` missing parent dir
4. `No module named 'adapters'` — not in bundle
5. `cvxpy`/`pydantic` missing from image — indirect pip deps
6. Symlink escape rejected — `manifest_uri_resolver` security check
7. `No module named 'training_panel'` — not in bundle + `ngboost`/`lightgbm`

## Round 2 — Codex review: restore configurable timeout/retries (blocking)

**Finding**: moving `run_variant_remote` to module scope (round 1) required
its `timeout`/`retries` to become `@app.function` decorator-time constants,
but `ModalExecutor.__init__` and the CLI's `--timeout` flag still accepted
per-call values that `execute_batch()` silently never threaded through —
callers could request a custom timeout/retry policy and it would appear
accepted while the remote run always used the hard-coded `timeout=3600,
retries=1` defaults.

**Investigated rather than assumed**: checked the installed `modal` SDK
(1.2.6) directly — `modal.Function` has no `with_options()`/`options()`
method, and `App.function()`'s `timeout`/`retries` are plain decorator
kwargs. There is genuinely no per-call override for a module-scope
function in this SDK version; the constraint that broke configurability in
round 1 is real, not an oversight.

**Fix**: `modal_app.py` now reads `WORKER_TIMEOUT_SECONDS`/`WORKER_RETRIES`
from `RENQUANT_MODAL_TIMEOUT_SECONDS`/`RENQUANT_MODAL_RETRIES` env vars
(defaulting to the prior 3600/1) at module import time, and
`ModalExecutor.execute_batch()` sets those env vars from
`self._timeout`/`self._retries` immediately before its only import of
`modal_app`. Since decoration happens at that first import, the caller's
requested values now genuinely reach the decorator. A second `ModalExecutor`
in the same process requesting *different* values would silently reuse the
first import's baked-in decoration (Python's `sys.modules` import caching) —
`execute_batch()` now detects this and raises `RuntimeError` rather than
silently reusing stale values; each distinct timeout/retries combination
needs its own process, which matches how this CLI is actually invoked (one
process per sweep run).

**Verification**: 4 new tests in `tests/test_cloud_modal.py`
(`TestModalTimeoutRetriesConfigurability`) prove the env var reaches the
actual `@app.function` decorator kwargs (via a lightweight in-process
`modal` SDK stub — `modal` is not a project dependency, only needed at real
cloud runtime), that defaults are preserved when unset, and that a
conflicting same-process reimport raises instead of silently dropping the
request. 3/4 confirmed to fail against the pre-fix code via `git stash`
(the 4th, unaffected-defaults case, correctly still passes pre-fix — proving
only the non-default path was ever broken). Full suite: 3242 passed, 3
skipped, 1 pre-existing unrelated failure (`test_parking_sleeve_cli_computes_allocation`).

**Smoke-test evidence — still outstanding, not fabricated**: Codex also asked
for 2-variant Modal smoke evidence before treating the runtime as validated
for the full 75-variant sweep. Modal credentials are configured on this
machine (`~/.modal.toml`), so a real smoke run is technically possible, but
it means spending real money on cloud compute and image-build time — a
different category of action than this round's code fix, and not something
this round's authorization covers. Left honestly unresolved rather than run
without clearer sign-off or faked with a placeholder result; the PR's own
test-plan checkbox for this item remains unchecked.

## Test
- 3242 passed, 3 skipped, 1 pre-existing unrelated failure
- Smoke test (2-variant) still outstanding — see round 2 note above
