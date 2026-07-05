# 2026-07-04 Unit tests for daily orchestration module

## What

Added `tests/test_daily.py` with 60 unit tests covering every public class,
task, and helper in `src/renquant_orchestrator/daily.py`.

## Coverage

| Class / helper               | Tests |
|------------------------------|-------|
| `DailyRunContext`            | 2     |
| `ValidateDailyInputsTask`   | 15    |
| `TrainGbdtArtifactTask`     | 4     |
| `RunRuntimeInferenceTask`   | 3     |
| `ExecuteOrderIntentsTask`   | 5     |
| `RunBacktestCheckTask`      | 3     |
| `PersistDailyRunBundleTask` | 8     |
| `DailyRunJob`               | 2     |
| `DailyRunPipeline`          | 2     |
| `_pipeline_result`          | 2     |
| `_write_json`               | 4     |
| `_json_safe`                | 9     |
| **Total**                   | **60**|

## Approach

- Each task tested in isolation by monkeypatching external pipeline `run()`
  methods (`PanelGbdtTrainingPipeline`, `RuntimeInferencePipeline`,
  `BrokerExecutionPipeline`, `BacktestPipeline`).
- Uses `PaperBroker` from `renquant_execution` (same as existing tests).
- No real filesystem/network calls beyond `tmp_path` fixtures.
- Complements the existing integration-level `test_daily_run_pipeline.py`.

## Verification

All 60 new tests pass. Full suite (2766 tests) unaffected.
