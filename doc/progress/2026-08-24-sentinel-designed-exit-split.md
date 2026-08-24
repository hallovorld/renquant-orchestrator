# Nine jobs, one alarm, no way to tell "I found something" from "I crashed"

STATUS:   delivered. One function in the sentinel + one helper + a test file.
          Read-only checker; no job, config, launchd plist or live path
          touched. The alarm's WORDING and TIERING change; nothing else does.

WHAT:     `check_launchd_exits` rendered every nonzero-exit job as a bare
          `<label> (last exit N)`. Reading it required knowing, from memory,
          which numbers mean a job REPORTING and which mean a job BROKEN. It
          now classifies each against `agent_inbox.DESIGNED_EXIT_CODES`:

          | class | rendering |
          |---|---|
          | designed, `actionable=False` | leaves the alarm → INFO |
          | designed, `actionable=True`  | LOUD, **with its meaning + contract path** |
          | not in the map               | LOUD, "NO DOCUMENTED MEANING … needs a human" |

WHY/DIR:  orch#1011. `com.renquant.weekly-wf-promote` exited 2 on 2026-08-08
          and again on 2026-08-15. The alarm fired both times, the way it
          fires every day, and the dead promote chain sat inside a list of a
          dozen expected nonzeros for **14 days** — found by noticing a stale
          artifact, not by the alarm.

          Alarm fatigue here is not a volume problem, it is a TYPE problem:
          `exit 1` from ops-audit ("I have findings") and `exit 2` from
          weekly-wf-promote ("I am dead") were the same string to the reader.

EVIDENCE:
  artifact:      ops/renquant104/rq104_degradation_sentinel.py
                 (`designed_exit_meaning` + the split in `check_launchd_exits`)
                 and tests/test_sentinel_designed_exit_split.py.
  prod or exp:   neither — the sentinel is read-only by construction
                 (`_open_db_readonly`, `launchctl list`). It never acks,
                 writes or mutates a job.
  existing data: measured against REAL `launchctl list` state, 2026-08-24. The
                 alarm named **9 jobs identically**. Split, they are three
                 different things [VERIFIED]:
                   UNKNOWN — needs a human (3):
                     monthly-calibrator-refresh 1, rq104-dawn-preflight 1,
                     shadow-ab-daily 3 (ack expired 9d ago)
                   DESIGNED and actionable — the meaning IS the problem (4):
                     rq104-silent-refusal 1, rq104-model-freshness 3,
                     run-surface-drift 1, rq104-risk-budget 1
                   DESIGNED status report — does not belong in an alarm (2):
                     ops-audit 1, rq105-shadow-serving 4
                 After the change the same state renders as 7 loud (each
                 carrying WHAT it means) + 2 infos [VERIFIED].
  best-known?:   yes, because of where the map lives. It is
                 `agent_inbox.DESIGNED_EXIT_CODES`, IMPORTED — not copied.
                 That map is kept honest by `tests/test_agent_inbox.py`, which
                 re-greps every source file it cites and fails when a
                 wrapper's contract moves. A private second copy here would
                 rot by exactly the mechanism this split exists to defeat.
  scope:         the launchd-exit alarm only. The ack ledger, its expiry
                 rules, and the `ACK DOES NOT COVER THIS EXIT` /
                 `ACK UNUSABLE` / `ACK EXPIRED` paths are untouched — the
                 split runs BEFORE them and two control tests pin that they
                 still behave as reviewed.

VERIFICATION:
  Mutation-verified against the state that actually ran for 14 days. New
  tests vs the UNPATCHED sentinel: **7 failed, 3 passed**. The 3 that pass
  both ways are the ack controls — they MUST NOT flip, and do not.
  Patched: 10 passed.
  Every suite sharing this function: 186 passed
  (test_sentinel_designed_exit_split, test_sentinel_ack_exit_codes,
   test_ack_expiry, test_ack_names_the_exit_code, test_ack_ledger_audit,
   test_rq104_degradation_sentinel, test_agent_inbox) [VERIFIED 2026-08-24].

  The load-bearing test is `test_losing_the_map_makes_the_alarm_LOUDER`.
  Consulting another module at alarm time buys a failure mode: if the import
  breaks, does the monitor go quiet? It must not. `designed_exit_meaning`
  returns None on ANY import failure, so every code becomes UNKNOWN and the
  alarm degrades to exactly its pre-split behaviour — noisier, never quieter.

  Dates: the test file anchors every date to a FIXED `AS_OF` and passes it to
  `check_launchd_exits(today=...)`. Aging a fixture from the wall clock while
  asserting against a fixed date is a bomb with its date already set; one
  detonated across this repo on 2026-08-24
  (doc/progress/2026-08-24-undelivered-scan-test-clock-bomb.md).

NEXT:     `weekly-wf-promote` — the job this issue is about — deliberately
          stays UNKNOWN, pinned by a test. Its wrapper lives in the sibling
          umbrella repo, which this repo's CI does not check out, so the
          contract cannot be MEASURED here and must not buy quiet. Closing
          that gap needs cross-repo source verification; not attempted here.
