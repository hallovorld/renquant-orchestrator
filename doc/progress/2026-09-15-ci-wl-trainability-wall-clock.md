# 2026-09-15 — CI: the watchlist-trainability tests read the wall clock; seven went red on 2026-09-13 on every orchestrator PR

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     `undeclared_untrainable(rq_root=None, *, today=None)` and `main --today`
          add an as-of seam so tests pin a fixed date instead of reading
          `dt.date.today()`; the default stays the wall clock, unchanged for
          the live weekly job.
WHY/DIR:  same shape as #1119's A4-T1 wall-clock read, one file over — a
          hardcoded 2026-08-23 declaration fixture crossed the module's
          21-day freshness limit on 2026-09-13, so seven tests plus the
          exit-code test go red on every orchestrator PR regardless of diff.
EVIDENCE: see §4(b) below.
  artifact:      ops/watchlist_trainability_check.py + tests/test_watchlist_trainability_check.py (19 passed on this branch).
  prod or exp:   prod-adjacent CI fix only, no data/config regen; the live job still reads the wall clock by default.
  existing data: #1122's CI run (34763396670) 1 failed pre-09-13; #1124's run (35031735785) 8 failed/7170 passed post-09-13 — exactly this module's seven tests plus the unrelated A4-T1 test.
  best-known?:   yes — anti-vacuity: origin/main's module+test file run in isolation today = 8 failed, 11 passed, matching CI exactly.
  scope:         ops/watchlist_trainability_check.py and its test file only.
NEXT:     merge after review; unblocks CI on every open orchestrator PR
          alongside #1119.

## Conclusion

`tests/test_watchlist_trainability_check.py` builds a declaration fixture
stamped `2026-08-23` and then calls `undeclared_untrainable(root)` /
`main(["--rq-root", ...])`, which read `dt.date.today()` for the
declaration's age. The module refuses a declaration older than 21 days (a
WEEKLY producer that stopped must not keep authorising silence — correct
for the job). On 2026-09-13 the fixture crossed that limit and seven tests
began failing with `InputMissing: 2026-08-23.expected_non_trainable.json is
23d old (limit 21d ...)`, plus the exit-code test (`assert 2 == 1`), on
every orchestrator PR since — the same shape as #1119's A4-T1 wall-clock
read, one file over.

`[VERIFIED]` #1122's CI run on 2026-09-13 (34763396670): `1 failed`
(the A4-T1 test only). #1124's run today (35031735785): `8 failed, 7170
passed` — the seven trainability tests + A4-T1. Nothing in #1124 touches
this module.

## Change

- `undeclared_untrainable(rq_root=None, *, today=None)`: the as-of date is
  a seam, threaded into `_declared` (which already accepted `today`) and
  into the `declaration_age_days` evidence. Default is still the wall
  clock, which is what the scheduled job wants.
- `main` gains `--today` (ISO) for the same reason.
- Tests: `AS_OF = 2026-08-24` is hoisted to the top with the explanation;
  every check runs as of that date (13 call sites + 3 `main` calls).

## Evidence (§4(b))

- This branch, run today: `19 passed`. `[VERIFIED]`
- Anti-vacuity: `origin/main`'s module + test file run in isolation today:
  `8 failed, 11 passed` — exactly the eight in #1124's CI. `[VERIFIED]`
- The live job is unaffected: the real declaration is refreshed weekly
  (`logs/weekly_tournament_retrain/2026-09-13.expected_non_trainable.json`)
  and the default remains the wall clock.

## Not in scope

The A4-T1 red (`test_bash_wrapper_end_to_end_records_the_verdict`) is
#1119's; with both merged the orchestrator suite is green again.
