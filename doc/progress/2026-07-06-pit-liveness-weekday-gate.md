# PIT liveness weekday gate (PR #401)

STATUS:   fixed (round 2 — rebased + scope narrowed after codex review)
WHAT:     `ops/pit/pit_liveness_check.py` switches its session-day gate from the real NYSE
          exchange calendar to a plain weekday check (`day.weekday() < 5`), since the PIT
          estimate snapshotter itself runs Mon-Fri regardless of NYSE market status (FMP
          analyst data updates on holidays). The NYSE-calendar gate was silently skipping
          liveness verification on market holidays like the observed July 4th (2026-07-03) —
          a snapshot failure on such a day would go undetected, and PIT data is unrecoverable
          (no backfill). `tests/test_pit_snapshotter_scheduling.py::test_holiday_weekday_is_still_checked`
          also mocks `_alert` so its intentional failure case doesn't send a real ntfy
          notification during test runs.
WHY-DIR:  originally opened alongside an unrelated "ntfy on paper order submission" commit
          (`b506de26`) on the same branch. That commit added a notification hook inside
          `_build_paper_submitter()` — but PR #400 (merged first, same branch lineage)
          deleted `_build_paper_submitter()` and all direct-broker-submission code from this
          repo entirely as a hard architecture-boundary violation (orchestrator must not
          implement broker adapters). The ntfy commit's target function no longer exists on
          main, so it has been dropped from this PR rather than reintroduced — any future
          paper-order notification needs its own design once real paper execution is rebuilt
          properly in `renquant-execution` with its own authorization path, not resurrected
          here. This PR's actual remaining scope is the PIT liveness fix only.
EVIDENCE: branch merged with `origin/main` (picks up #399's cadence fix and #400's
          broker-adapter removal); conflict in `intraday_session_scheduler.py` resolved by
          taking main's version entirely (grep-confirmed zero remaining references to
          `_build_paper_submitter`, `MODE_PAPER`, `TradingClient`, `submit_order`, or the ntfy
          hook). Full suite run after merge — see PR CI for final numbers.
NEXT:     PR title/body updated to drop "ntfy on paper orders" framing; scope is now PIT
          liveness weekday-gate only.
