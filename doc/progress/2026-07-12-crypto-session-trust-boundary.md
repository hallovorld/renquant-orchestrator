# Crypto session scheduler trust-boundary hardening

**Date:** 2026-07-12
**PR:** orchestrator feat/crypto-session-scheduler-v2 (#497)
**Design:** crypto RFC §3.5, orchestrator PR #453

## What

Trust-boundary hardening for the crypto session scheduler (D-C11).
Addresses codex review items on PR #497.

### Changes

1. **`validate_signal_contract(snapshot)`** — new function validating
   fingerprint completeness (non-empty universe_hash, model_content_sha256,
   calibrator_content_sha256) and timezone-aware bar_watermark_utc. Called
   in `evaluate_tick` before date/watermark checks.

2. **`SignalArtifactRef.validate()`** — runtime validation that
   artifact_path exists on disk and schema_version matches the current
   version (1). Called in `evaluate_tick` after the None check, before
   digest verification.

3. **`StopCoverageReport.account_id`** — new required field identifying the
   trading account. Construction-time validation (non-empty). Included in
   session bundle output.

4. **`StopCoverageReport.validate()`** — runtime validation that
   environment is live/paper and timestamp_utc is timezone-aware. Called in
   `evaluate_tick` after the None check, before environment/staleness checks.

5. **Bundle schema v2** — `build_session_bundle` now emits
   `schema_version: 2` with `environment`, `quiet_interval_minutes`, and
   `account_id` in stop_coverage output.

## Why

The original implementation accepted any non-None values at the trust
boundary. These hardened checks ensure:
- Empty fingerprints fail-close (no silent pass-through)
- Artifact paths are verified to exist (no phantom references)
- Stop coverage reports carry account identity for audit trails
- Bundle schema is self-describing with environment context

## Status

- 68/68 tests pass (up from 50 in v1).
- New test classes: TestSignalContract, TestArtifactRefValidation,
  TestStopCoverageValidation.
- Source + tests updated on feat/crypto-session-scheduler-v2.
