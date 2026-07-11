# 2026-07-11 — weekday-gate the shadow-ab launchd schedule

The experiment plist fired daily including weekends; a Saturday session
re-observes Friday's close — a paired duplicate world contributing zero
information to the D6-§2a series (caught before the first weekend firing
mattered: today's Saturday run is harmless — paired, same-world — just
noise). Gated to Mon–Fri like com.renquant.daily104.plist.

## Round 2 (Codex review)

Codex correctly flagged that the launchd weekday filter alone is
insufficient: the D6 experiment unit is a trading *session*, not a calendar
weekday — an NYSE full-closure holiday that lands on a weekday (Independence
Day, Thanksgiving, Christmas, ...) still passes a Mon-Fri filter and would
re-observe the prior close as another spurious zero-information "paired"
world.

Fix: `scripts/shadow_ab_daily.sh` is now the authoritative gate. Right after
`PYTHONPATH` is exported and before any run-manifest verification, price
snapshot, or paired-session record, the script calls
`renquant_common.market_calendar.is_session(SESSION_DATE)` — the single
canonical NYSE session-calendar primitive already shared across the
multi-repo stack (backed by `pandas_market_calendars`, never a hand-rolled
holiday list or an umbrella-path heuristic). On a non-session date (weekend
or full-closure holiday) it logs a distinct `SKIP:` line (to both the
session log and fd3) and exits 0 cleanly — no run bundle, price snapshot, or
paired-session record is written. Early-close/half-day sessions are real
sessions and are *not* skipped: `is_session()` already returns `True` for
them. The launchd Mon-Fri `StartCalendarInterval` filter is kept, but is now
explicitly framed as a cost optimization only (fewer wasted weekend launchd
wake-ups) — the script's own gate is what makes the paired-session series
correct.

Tests added to `tests/test_shadow_ab_daily_script.py`
(`TestSessionCalendarGate`), using real 2026 NYSE calendar dates verified
against `pandas_market_calendars`:

* 2026-07-04 (Saturday) → skipped, no observation written.
* 2026-11-26 (Thanksgiving Day, a Thursday — a real NYSE full-closure
  holiday with no schedule row at all) → skipped, no observation written.
* 2026-11-27 (day after Thanksgiving, a Friday — a real NYSE early-close/
  half-day session, `market_close` 18:00 UTC vs the normal 21:00 UTC) → NOT
  skipped, proceeds normally.
* 2026-07-10 (Friday, a normal trading day) → NOT skipped; the existing
  test cases in this file already exercise fuller progression on this same
  date.

## Round 3 (Codex review — P0 integrity ordering)

Codex flagged the round-2 gate placement itself as a P0 fail-closed
regression: the session-calendar check ran (and imported
`renquant_common.market_calendar` from an unverified sibling checkout)
*before* the run-manifest / pin-identity precheck (`verify_run_manifest`). A
dirty or wrong-commit sibling checkout could therefore return a false "not a
session" and make the scheduler silently `SKIP` a real trading day — an
identity-fingerprint hole, not just a scheduling nicety.

Fix: pure reordering, no logic changes. `scripts/shadow_ab_daily.sh` now runs
the run-manifest / pin-identity precheck (`verify_run_manifest`) FIRST,
immediately after `PYTHONPATH` is assembled from the manifest — before any
pinned-repo code (including `renquant_common.market_calendar`) is ever
imported. The trading-session calendar gate runs SECOND, only once every
pinned checkout has been confirmed clean and at its pinned commit. All exit
codes, comments' internal logic, and gate behavior are unchanged; only the
order of the two existing blocks moved, plus updated comments (module header
and each block's own preamble) describing the new order.

Added `test_dirty_manifest_on_non_session_date_fails_closed_not_skip` to
`TestSessionCalendarGate`: pairs a real non-session date (2026-07-04,
Saturday) with a dirty pinned repo (same `_build_manifest(dirty=...)`
fixture `TestRunManifestVerification` already uses) and asserts the
run-manifest identity failure (`PRECHECK`, exit 3) wins — never a `SKIP`.
Confirmed the 4 existing `TestSessionCalendarGate` cases (Saturday,
Thanksgiving, day-after-Thanksgiving half-day, normal Friday) still pass
unchanged after the reorder.

## Landing

Merging this PR changes only committed configuration and script source in
this repository. It has **no effect on any running host by itself.**
Installing/reloading `com.renquant.shadow-ab-daily.plist` on the live host
(`launchctl unload` + `launchctl load` of the updated plist) remains a
**separate, later, ask-first operator landing action** — the same
"landing actions ask-first" convention as every other machine-landing step,
not an implied or automatic effect of this PR merging.
