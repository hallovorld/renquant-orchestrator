# fix: make shadow-ab tests hermetic against dirty sibling repos

**Date**: 2026-07-12
**PR**: fix/shadow-ab-test-hermetic-precheck

## Problem

6 of 15 `test_shadow_ab_daily_script.py` tests failed locally when sibling
repos (renquant-artifacts, renquant-pipeline) had untracked files. The
tests used REAL sibling checkouts in the manifest for their import closure,
and `verify_run_manifest` (the precheck) rejected them as DIRTY before the
actual test logic ran. CI passed because CI checkouts are always clean.

## Fix

- Added `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY=1` env var bypass to the
  shell script's precheck block (test-only affordance; production plist
  never sets it).
- Tests that don't test the precheck itself (calendar gate, market
  snapshot, timeout, strategy-dir) now set the skip flag.
- `TestRunManifestVerification` and `test_dirty_manifest_on_non_session_date`
  continue to exercise the real precheck path.

## Result

Local: 3693 passed, 2 failed (pre-existing env-specific: hung-session
watchdog + twin-parity drift), down from 8 failed.
