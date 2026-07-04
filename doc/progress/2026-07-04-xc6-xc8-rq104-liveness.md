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
