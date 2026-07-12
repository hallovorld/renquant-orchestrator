# Test Failures Post-#481 Merge Fix

Date: 2026-07-12
Status: COMPLETE

## Summary

3 test failures on main after #481 (stops-liveness pager) merged. All
caused by environment assumptions in subprocess-based tests.

## Fixes

1. **Pager integration tests** (2 tests): `_installer_env` overrides
   `HOME` to `tmp_path`, causing Python 3.9 to lose user site-packages
   (where pydantic lives). Fix: pass `PYTHONUSERBASE` so transitive deps
   remain importable in the subprocess. Also required: `git pull` on the
   pipeline sibling (pipeline #192 merged but checkout was behind).

2. **Shadow-AB timeout test** (1 test): the stub's `sleep 120 &` child
   survives SIGTERM because bash doesn't propagate signals to backgrounded
   jobs. The orphaned `sleep` holds pipes open, causing
   `subprocess.communicate()` to hang past the 30s timeout. Fix: trap
   SIGTERM in the stub and kill the background child explicitly.
