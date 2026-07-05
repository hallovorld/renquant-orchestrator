# 2026-07-04 contract_fixture unit test coverage

## What

Added `tests/test_contract_fixture.py` with 26 unit tests covering the full
public API of `src/renquant_orchestrator/contract_fixture.py`.

## Coverage

| Area | Tests | Notes |
|------|-------|-------|
| `fixture_data_manifest()` | 5 | dict shape, required keys, fingerprint prefix, retention_class, idempotency |
| `run_contract_fixture()` happy path | 9 | ok flag, training call trace, artifact_id, broker_type default, dry_run default, bundle path on disk, bundle keys, order_intents, backtest report |
| Parameter variations | 4 | explicit broker_name, code_commit propagation, dry_run=False, as_of propagation |
| Broker name mismatch | 3 | non-paper mismatch raises, matching passes, None uses default |
| Paper broker naming | 2 | default "paper-smoke", explicit name |
| Run-bundle persistence | 3 | JSON validity + run_id/schema_version, decision_trace sidecar, submitted_orders sidecar |

## Design choices

- All external subrepo deps (`renquant_strategy_104`, `renquant_execution`,
  `renquant_pipeline`) are monkeypatched via a shared `_patch_subrepo_deps`
  fixture so the suite is hermetic (no network, no real filesystem deps).
- Fake `_FakePaperBroker` implements the minimal broker interface
  (`connect`, `disconnect`, `set_price`, `place_order`).
- Runtime stages (`PanelScoringJob`, `SelectionJob`) are replaced with
  lightweight `Task` stubs that produce attributed order intents.
- Uses `tmp_path` for all output; no production paths touched.
