# The ack check ignored `--as-of`, and the suite time-bombed at UTC midnight   (PR pending)

STATUS:    fix + 2 regression tests. One-line production change, no behaviour change
           for a run without `--as-of`.
WHAT:      `rq104_degradation_sentinel.main()` computed `today` from `--as-of` and
           passed it to `check_traceback_in_daily_log(today)` but called
           `check_launchd_exits()` with **no argument**, so ack expiry alone fell back
           to `dt.date.today()`.
WHY/DIR:   Found while diagnosing red CI on orch#641 and orch#650 — two unrelated
           branches failing the same test, in a file neither touches.
EVIDENCE:  `TZ=UTC pytest tests/test_rq104_degradation_sentinel.py` on **origin/main**
           at f59d4609 → `1 failed` (`TestAckLedger::test_acked_job_moves_to_info`);
           the same command in local time (PDT, still 2026-07-30) → `45 passed`
           [VERIFIED — both run this session]. With the fix: **47 passed under both**.
           Load-bearing: reverting the one-line change re-breaks 2 tests under UTC.
NEXT:      None. This unblocks every open orchestrator PR.

## What actually happened

`TestAckLedger`'s fixture acks at **2026-07-17**. `ACK_MAX_AGE_DAYS = 14`, so its
expiry is **2026-07-31**. At UTC midnight on the 31st the ack expired *correctly* — and
the test asserts it still suppresses, so it started failing.

The suite pins `AS_OF = "2026-07-16"` and passes `--as-of` on every `main()` call, so
every other check was evaluated at the pinned date. The ack check was not. **A suite
pinned to a fixed as-of date had one component reading the wall clock**, so its
fixtures aged out from under it.

The failure mode is the nastiest kind: it appeared on **every branch at once**, in a
file none of them modified, and it reproduced only in timezones at or past UTC. A
reviewer on the US west coast would have seen green locally and red in CI on someone
else's change, which is exactly how a shared defect gets misattributed to whichever PR
happens to be under review.

## It is also a production bug, not only a test one

`--as-of` exists so the sentinel can be re-run for a past date. With the ack check
reading `dt.date.today()`, such a re-run judged ack expiry by **today**, not the date
being reconstructed — so a historical run would report acks as expired that were live
at the time, and the reconstruction would not reproduce what the sentinel actually did
that day. The one-line fix makes `--as-of` mean the same thing to every check.

## Why the regression tests are shaped this way

- `test_the_ack_check_receives_the_pinned_as_of_date` asserts **at the seam** — that
  the ack check is handed the as-of date — rather than on an outcome. An outcome
  assertion would pass whenever the fixture's dates happened to sit inside the window
  *today*, i.e. it would be exactly the test that just failed us.
- `test_an_ack_fixture_cannot_age_out_of_the_window` scans this file's own
  `acked_at` literals and fails if any is `ACK_MAX_AGE_DAYS` or more before `AS_OF`.
  That closes the **class**: the next fixture written close to the window edge is
  caught when it is written, not on the morning it silently crosses.

## Live-surface impact

None. One line in a read-only sentinel plus tests. No config, artifact, state or
launchd change; no ack ledger edit — the expired ack expired on purpose and lifting it
is a separate, reviewed decision.
