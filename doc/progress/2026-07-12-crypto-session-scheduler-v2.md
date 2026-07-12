# D-C11 v2: crypto session scheduler — codex review fixes

**Date:** 2026-07-12
**PR:** supersedes #497
**Review:** codex review on #497 (5 items)

## What

Addressed all 5 items from codex's review of PR #497:

1. **Watermark validation** — `validate_watermark()` rejects snapshots whose
   `bar_watermark_utc > session_date 00:00 UTC` (catches future-bar leakage)
2. **Digest verification** — `validate_digest()` compares snapshot digest
   against an expected artifact-path digest; entries fail-closed on mismatch
3. **Shadow mode gate** — `config.mode != "live"` blocks entries (shadow
   produces observation records only, never real orders)
4. **Configured quiet interval** — `SessionWindow.for_date()` accepts
   `quiet_minutes` from `CryptoSessionConfig.quiet_interval_minutes`
5. **Stop coverage** — `stop_coverage_ok` parameter gates entries; fail-closed
   when None or False

## Gate chain (7 gates)

1. Triple gate (config + env + kill switch)
2. Mode must be `live`
3. Quiet interval (`[D 00:00, D + quiet_minutes) UTC`)
4. Signal snapshot present + session date match
5. Watermark validation (no future bars)
6. Digest verification (fail-closed on missing expected_digest)
7. Stop coverage ready (fail-closed on None/False)

## Tests

39 tests covering all review items explicitly:
- `TestWatermarkValidation` (4 tests)
- `TestDigestVerification` (4 tests)
- `TestShadowModeNonAdmission` (2 tests)
- `TestConfiguredQuietInterval` (2 tests)
- `TestStopCoverage` (2 tests)
- Plus existing 25 tests for v1 functionality
