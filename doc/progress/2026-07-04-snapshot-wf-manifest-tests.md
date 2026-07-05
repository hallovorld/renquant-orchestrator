# Snapshot + WF manifest test coverage (2026-07-04)

## What

Added 54 unit tests for two under-tested modules:

- `tests/test_native_live_snapshots.py` (+37 tests) — _as_float, _position_symbol,
  _position_quantity, _normalize_position, _normalize_positions, _prices_from_payload,
  _load_json_object, _write_json, metadata injection for account + market snapshots
- `tests/test_build_wf_manifest.py` (+17 tests) — extract_cutoffs, build_train_cmd,
  manifest_row, build_manifest_payload, training_env

## Why

Both modules had 3-4 integration tests but zero pure-function unit tests. The
helpers contain normalization logic (symbol casing, quantity aliasing, price
extraction) and command construction that benefit from edge-case coverage.

## Test count

2278 → 2332 (+54). All passing.
