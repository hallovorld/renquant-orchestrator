# env_files test coverage

**Date:** 2026-07-05
**Status:** Ready for review

## Summary

Adds 13 unit tests for `src/renquant_orchestrator/env_files.py`, which had
zero direct test coverage. The module provides `.env` file reading helpers
used by operator-facing command preflights.

## Tests added (`tests/test_env_files.py`)

### `read_env_file` (9 tests)
- None path returns empty dict
- Missing file with `missing_ok=True` returns empty dict
- Missing file with `missing_ok=False` raises `FileNotFoundError`
- Comments and blank lines skipped
- `export ` prefix stripped
- Single and double quotes stripped from values
- Splits on first `=` only (values containing `=` preserved)
- Lines without `=` skipped
- Empty key skipped

### `load_env_file` (4 tests)
- Sets `os.environ` from file
- `override=False` does not overwrite existing env vars
- `override=True` does overwrite
- Missing file raises `FileNotFoundError`

## Test results

13 passed, 0 failures
