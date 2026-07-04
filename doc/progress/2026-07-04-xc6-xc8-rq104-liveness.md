# XC-6 + XC-8: rq104 liveness checker + shared liveness common

Date: 2026-07-04
Campaign: Group D hygiene (compliance fix campaign)
Status: DELIVERED

## What

1. **`ops/liveness_common.py`** (XC-8): extracted the duplicated `_session_calendar`,
   `_is_session_day`, `_alert` trio into a shared module used by all liveness checkers.
2. **`ops/renquant104/rq104_liveness_check.py`** (XC-6): new liveness checker for the
   two rq104 launchd jobs (risk_budget, scorer_identity). Checks wrapper log presence
   and scorer identity verdict line. Session-day gated.
3. **`ops/renquant104/com.renquant.rq104-liveness.plist`**: launchd plist for daily
   18:00 execution (not installed — landing action, needs operator ask-first).
4. **9 tests** covering both the shared module and the rq104 checker.

## Addresses

- XC-6 (P1): rq104 has no liveness checker — silent launchd lapse undetectable
- XC-8 (P2): liveness common dedup (pit + rq105 can migrate to this shared module later)

## Round 2 (codex review)

Fixed a real implementation bug: `_check_scorer_identity_verdict`'s fallback branch read
`"identity OK" not in text.lower()` — comparing a lower-cased haystack against a
mixed-case needle, so the substring could never match. In practice this meant ANY log
lacking the exact `scorer_identity_check:` marker was always flagged as a crashed/missing
verdict, even when it carried a genuine plain "identity ok"-style success line. Fixed to
`"identity ok" not in text.lower()`.

The existing test suite didn't catch this: `test_all_logs_present_ok` only used the
explicit marker, and `test_empty_log_detected` also writes an empty `risk_budget` log, so
its zero-byte wrapper-log failure masked whether the verdict-line fallback itself passed.
Added `test_fallback_verdict_recognized_without_explicit_marker`, which isolates the
fallback path (both logs present and non-empty, scorer_identity log carrying only the
plain "identity OK" line) — confirmed this test fails against the pre-fix code and passes
after.

Also fixed `test_alert_missing_notify_does_not_crash`'s vacuous `... or True` assertion,
which made the test unable to fail regardless of behavior. Replaced with real checks
(`"unavailable" in err`, plus the title/body are preserved in the warning) — confirmed by
temporarily breaking the warning-emission code and observing the test now fails.

10/10 liveness tests pass; 1901/1901 full repo suite, zero regressions.
