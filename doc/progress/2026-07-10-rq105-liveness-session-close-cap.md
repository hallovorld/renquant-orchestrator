STATUS:   fixed
WHAT:     `ops/renquant105/rq105_liveness_check.py`'s `_data_output_fresh()` (row_event_time
          basis, used only by `intraday_quote_logger`) now compares the last row's age against
          `min(wall-clock now, today's NYSE session close)` instead of raw wall-clock now. The
          check itself runs at 14:00 PT, ~1hr after the 13:00 PT NYSE close (per the plists),
          and the quote logger correctly stops sampling at close — so the old unconditional
          10-minute-vs-now bound was structurally guaranteed to read "stale" every single
          trading day, not only on a genuine lapse. `check_collector_data_outputs()` now
          resolves the session's close once via the existing `_session_calendar()` primitive
          and passes it through to every `_data_output_fresh()` call (the two file_mtime-basis
          collectors ignore the new argument). The "row timestamp ahead of now" clock-skew
          check is unaffected — it still compares against true wall-clock now, not the capped
          reference, and a genuinely-early-stopped logger (e.g. crashed mid-session) still
          fails, since the cap only raises the bar it's judged against when checked long after
          a *correct* close, it never lowers it.
WHY/DIR:  triggered by two live ntfy alerts: `intraday_quote_logger: ... last complete row
          age=1:00:28 exceeds 0:10:00 bound` and `intraday_pairing_logger: ... last complete
          row date='2026-07-08' != today '2026-07-10' (stale)`. Investigated both against the
          live umbrella tree read-only (never written to). The pairing-logger alert is NOT a
          logger bug: `runs.alpaca.db` (read-only query) confirms zero admitted/submitted buy
          trades on 2026-07-08 and literally zero trades of any kind on 2026-07-09 despite 35
          successful pipeline runs that day with populated `candidate_scores` — the pairing
          logger correctly reports "0 sessions" because there was nothing to pair, a symptom
          of the already-tracked chronic veto-floor issue (the same motivation behind
          strategy-104#53's breadth-lever shadow A/B), not something this PR touches. The
          quote-logger alert IS a genuine liveness-check calibration bug, confirmed by reading
          `rq105_liveness_check.py`'s own `main()` (session-day gating only, no time-of-day
          gating) and the plists (postclose loggers fire 13:15 PT, liveness fires 14:00 PT) —
          this fires deterministically every trading day given the current schedule, not
          intermittently.
EVIDENCE: `tests/test_rq105_liveness.py` (new, 5 cases) exercises the exact failure scenario
          (row 2h old vs raw now → stale; same row vs a session-close reference only 5min
          later → ok), the during-session no-op case, the "still fails when genuinely stale
          even after the cap" case, and confirms the future/clock-skew check still uses real
          now. Meaningfulness verified via stash-revert: reverting only the source fix made
          4/5 new tests fail (the 5th, no-session-close-arg default behavior, correctly still
          passed). `tests/test_rq105_collector_scheduling.py`'s existing 44 cases (including
          `check_collector_data_outputs`'s row-hash-anchoring tests) all still pass unchanged.
          Full suite: 3357 passed, 1 pre-existing unrelated failure
          (`test_parking_sleeve_cli_computes_allocation`, a hardcoded-sibling-path artifact of
          running from an isolated worktree, reproduces the same way on main).
NEXT:     none for this PR — scope is the quote-logger liveness false-positive only. The
          pairing-logger's "0 admits" reflects the chronic veto-floor problem already being
          worked via strategy-104#53 and the Governor RFC cascade; not re-litigated here.
