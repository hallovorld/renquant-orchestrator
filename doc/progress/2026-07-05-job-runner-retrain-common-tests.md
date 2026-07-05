# job_runner + retrain_common test coverage

**Date:** 2026-07-05
**Status:** Ready for review

## Summary

Adds 41 unit tests for two previously untested modules: `job_runner.py`
(16 tests) and `retrain_common.py` (25 tests).

## Tests added

### `test_job_runner.py` (16 tests)
- `_clean_args`: strips leading `--`, passes through, None/empty, separator-not-first
- `_run_module_main`: calls main + returns rc, None→0, raises if no main attr
- `run_scheduled_job`: unknown id raises, three CLI dispatch paths
  (daily_contract_fixture, daily_live_runner_bridge, live_runner_bridge),
  module job dispatch, separator forwarding, registry non-empty

### `test_retrain_common.py` (25 tests)
- `subrepo_srcs`: correct paths for all 9 subrepos, count check
- `subrepo_pythonpath`: PYTHONPATH composition, default env vars, no-override,
  strategy_config set/unset, strict paths raises, preserves existing PYTHONPATH
- `run_subprocess`: dry_run records command, dry_run does not execute
- `read_json_object`: valid object, missing file, too-small, invalid JSON,
  array-not-object, nested object
- `resolve_path`: absolute unchanged, relative joined
- `staging_path`: suffix replacement
- `validate_repo_dir`: present dirs pass, missing raises, custom required list

## Test results

41 passed, 0 failures
