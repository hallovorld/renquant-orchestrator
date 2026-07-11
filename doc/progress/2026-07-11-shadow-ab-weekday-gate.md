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

## Landing

Merging this PR changes only committed configuration and script source in
this repository. It has **no effect on any running host by itself.**
Installing/reloading `com.renquant.shadow-ab-daily.plist` on the live host
(`launchctl unload` + `launchctl load` of the updated plist) remains a
**separate, later, ask-first operator landing action** — the same
"landing actions ask-first" convention as every other machine-landing step,
not an implied or automatic effect of this PR merging.
