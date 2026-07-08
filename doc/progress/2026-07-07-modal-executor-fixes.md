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

## Test
- 3228 passed, 2 skipped
- Smoke test (2-variant) running on Modal at time of PR
