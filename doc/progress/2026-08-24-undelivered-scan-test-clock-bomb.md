# A test that aged files from the wall clock while asserting against a fixed as_of

STATUS:    delivered. Test-only, one helper. No src change, no behaviour change,
           nothing deployed, no live path touched. Unblocks every open PR in
           this repo — the failure is unrelated to any of their diffs.

WHAT:      `tests/test_undelivered_alert_scan.py::_log` aged its fixture files
           from `time.time()` while every assertion asks the scanner for a
           FIXED `AS_OF = 2026-07-29`. The ageing anchor now IS `AS_OF`, so the
           arithmetic is hermetic. Also drops the `import time` this made
           unused.

WHY/DIR:   Mixing a moving anchor with a fixed one makes a test a time bomb:
           the fixture's date walks forward every day while the cutoff
           (`as_of − MAX_LOG_AGE_DAYS`) stays put, so a case written as
           "40 days old, comfortably stale" eventually lands on the wrong side
           of the boundary. Nothing about the code under test changes; the
           suite simply starts failing on a date nobody chose.

           It detonated on **2026-08-24** and straddled a timezone doing it,
           which is why it looked like a mystery rather than a rot:

           | environment | today | fixture mtime (age_days=40) | cutoff | result |
           |---|---|---|---|---|
           | workstation (PDT) | 2026-08-23 | 2026-07-14 | 2026-07-15 | ignored → PASS |
           | CI runner (UTC)   | 2026-08-24 | 2026-07-15 | 2026-07-15 | kept → **FAIL** |

           One day of clock and one zone of offset separated green from red, so
           the failure was invisible locally while red on every runner.

EVIDENCE:
  artifact:      tests/test_undelivered_alert_scan.py (the `_log` helper only)
  prod or exp:   neither — test fixture; `undelivered_alert_scan` itself is
                 untouched, and its behaviour was never wrong
  existing data: observed on orch#1026 and orch#1027, both **docs-only** PRs
                 whose diffs contain no Python at all, each with two red `test`
                 checks on `test_stale_logs_are_ignored`. A docs-only PR cannot
                 break a scanner test; that mismatch is what pointed at the
                 clock rather than at the diffs.
  best-known?:   yes. Anchoring to `AS_OF` is the smallest change that removes
                 the drift entirely rather than postponing it — bumping
                 `age_days` or `MAX_LOG_AGE_DAYS` would buy weeks and rot again.
                 After the fix the fixture dates are FIXED and both sit far from
                 the boundary rather than adjacent to it:
                   age_days=40 → 2026-06-19 (26d before the 2026-07-15 cutoff)
                   age_days=3  → 2026-07-26 (11d after it)
  scope:         this one test helper. No other test in the file ages fixtures,
                 and no production code reads `_log`.

VERIFICATION:
  tests/test_undelivered_alert_scan.py → 26 passed.
  Re-run under three zones to prove the zone-dependence is gone, since that is
  the half that made it look local-only:
    TZ=UTC                 → 26 passed
    TZ=America/Los_Angeles → 26 passed
    TZ=Asia/Tokyo          → 26 passed
  Full suite: see the PR body (run after the change).

NEXT:      none for this defect. Worth a separate look, not attempted here:
           this class of test — a fixed `as_of` compared against a now-relative
           fixture — is greppable, and if the pattern exists elsewhere those
           tests are dormant bombs with their own dates already set.
