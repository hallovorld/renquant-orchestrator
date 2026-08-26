# The fix that moved gate 2 outside git can be undone by deploying it

STATUS:    delivered. One read-only detector + its `ops_audit` membership +
           20 tests. No src change, no behaviour change, nothing deployed, no
           live path written. It does not create the arming file and must not:
           that is an operator landing step by #1067's own design.

WHAT:      `ops/renquant105/rq105_arming_enactment_check.py` compares the two
           surfaces that are supposed to agree about rq105 gate 2:

             gate 1  pinned `intraday_decisioning.enabled`      the REVIEWED intent
             gate 2  the arming file, as the DEPLOYED wrapper reads it   the ENACTMENT

           A pinned config saying `enabled: true` while nothing arms gate 2 is
           a finding. Registered as `ops_audit` member `rq105-arming-enactment`
           in the same PR, per the rule the aggregator was founded on.

WHY/DIR:   orch#1067 (merged 2026-08-26) closed orch#1034 by moving gate 2 out
           of an uncommitted working-tree edit and into an operator-owned file
           **outside git**:

               $RQ_ROOT/data/rq105/intraday_decisioning.armed.json

           Outside-git is the right call — it is what makes an authorized
           activation survive the recovery `git checkout --` that nearly
           extinguished it on 2026-08-24 (#1044). It also means **merging
           #1067 cannot create the file**, and the state measured this morning
           is exactly the trap that opens:

           | surface | state `[VERIFIED — 2026-08-26 06:0x PDT]` |
           |---|---|
           | `data/rq105/intraday_decisioning.armed.json` | ABSENT |
           | `renquant-orchestrator-run` vs `origin/main` | 4 behind |
           | deployed wrapper | still the pre-#1067 hard export → loop armed |
           | pinned `intraday_decisioning.enabled` | `true` |
           | gate 3 kill-switch | absent |

           So the loop is armed today only because the deploy has not happened.
           The next `-run` sync flips the mechanism to one whose input does not
           exist, and the decision loop goes dark — **the silent deactivation
           #1067 exists to prevent, performed by the fix for it.** The ordering
           is the entire difference: create the file, then sync.

           The ordering itself is the operator's to get right, and has been
           reported (#1067, #1055). What this adds is the half an ordering
           instruction cannot supply: the disarm's only signal today is an
           ABSENCE — no `intraday decisioning ARMED` line in
           `session_scheduler_<date>.log` — and absences are what this system
           keeps failing to notice. After this, the first audit following the
           cutover says so in one line.

           **Why it compares gates and not two log files.** An arming verdict
           read from yesterday's log tells you about yesterday; the cutover's
           first casualty is today. Comparing gate 1 to gate 2 needs no history,
           fires on the first audit after the sync, and generalises past this
           cutover to any later cause — a deleted file, a malformed edit, a
           deliberate disarm nobody wrote down. In that last case the finding is
           still correct: the remedy is to flip gate 1 too, or to ack.

           **Why the deployed wrapper is an input, not an assumption.** Gate 2
           has had two mechanisms this month. Reading the arming file alone
           would report a finding *today*, when the running wrapper never
           consults that file and the loop is armed — a guard validating the
           wrong object. So the wrapper in the RUN checkout decides which
           mechanism is in force, and the validator is loaded **from that same
           checkout**: importing this repo's copy while judging that repo's
           wrapper is how a deploy lag becomes invisible.

           **The audit runs 35 minutes before the session it protects, from the
           same checkout** `[VERIFIED — installed plists, 2026-08-26]`:

               com.renquant.ops-audit           weekdays 05:50
               com.renquant.rq105-session-scheduler  weekdays 06:25

           both `ProgramArguments` rooted at `renquant-orchestrator-run`. Two
           consequences, and the second is the point. The sync that deploys this
           detector deploys the new wrapper with it, so the `unusable` branch is
           a correctness case rather than a state anyone should expect to see
           live. And on the first morning after that sync the audit reads the
           missing arming file at 05:50 — **before** the 06:25 session that
           would have been dark. This is not only a post-mortem.

           **Why a pre-#1067 wrapper is `unusable` and not `ok`.** With a hard
           export there is no reviewed surface recording gate 2's state at all,
           so it cannot be checked — only left unchecked. Exit 2 lands UNUSABLE
           in `ops_audit`, which is the honest reading, and it self-clears on
           the sync it is warning about.

EVIDENCE:
  artifact:      ops/renquant105/rq105_arming_enactment_check.py (new),
                 ops/ops_audit.py (one MEMBERS entry),
                 tests/test_rq105_arming_enactment_check.py (new, 20),
                 tests/test_ops_audit.py (contract pin)
  prod or exp:   neither — read-only detector. Two file reads plus an importlib
                 load of the deployed validator, by path (no `sys.path`
                 mutation, no `sys.modules` aliasing).
  existing data: run against the LIVE surfaces, both states:

                   pre-deploy (today)    exit 2 UNVERIFIABLE: "the deployed
                     wrapper … predates the arming-file gate (orch#1067) …
                     This clears when the run checkout syncs #1067 — and at
                     that moment …armed.json must already exist, or the sync
                     itself disarms the loop."

                   post-sync (simulated, --orch-root at a checkout carrying
                     #1067)   exit 1 FAIL: "the pinned config declares
                     intraday_decisioning.enabled=true, but gate 2 is NOT
                     armed — absent: …/intraday_decisioning.armed.json"

                 That pair is the whole claim: silent on the state that is
                 fine, loud on the state that is coming.
  best-known?:   yes, for the detection half. The better fix is upstream and is
                 not mine to make: the cutover should not be able to happen in
                 the wrong order at all. Options recorded on #1055 — a `-run`
                 drift detector, or a sync path that refuses when a deployed
                 wrapper would require an input that does not exist. Both are
                 preconditions; this is the backstop for when a precondition is
                 skipped, which is the class of thing this repo has been burned
                 by more than once.
  scope:         gate 2 only. Whether the loop SHOULD be armed is gate 1, and
                 gate 1 is the operator's. Whether the job ran at all is
                 `launchd-liveness`. Gate 3 is a mid-session halt, not an
                 arming, and is untouched.

VERIFICATION:
  tests/test_rq105_arming_enactment_check.py → 20 passed. Beyond the happy
  path, the two ways this check could itself lie are pinned:
    * `test_todays_predeploy_state_is_UNVERIFIABLE_not_a_finding` — today's
      real state must not be a finding;
    * `test_the_predeploy_state_is_not_reported_as_OK_either` — and must not
      be a pass;
    * `test_the_validator_is_read_from_the_DEPLOYED_checkout` — a deployed
      validator that disagrees with this checkout's wins;
    * `test_the_marker_order_is_what_disambiguates_the_two_mechanisms` — the
      post-#1067 wrapper contains the hard-export line too, inside the `if`,
      so matching the export first would misread the new gate as the old one,
      which is exactly the difference between exit 1 and exit 2;
    * `test_a_marker_that_survives_only_in_a_COMMENT_does_not_count` — both
      wrappers document the other mechanism in prose, and a reverted wrapper
      usually keeps the sentence, so comment lines are stripped before the
      markers are matched. Without that, a revert would read as the new gate
      and its legitimately absent file as a disarm;
    * five malformed gate-1 payloads (`"true"`, `1`, `{}`, missing section,
      non-JSON) are UNVERIFIABLE, never a quiet "gate 1 is off".
  tests/test_ops_audit.py → the membership contract re-derives this member's
  exit codes from its own AST; `test_no_member_writes` passes, and
  `test_the_detector_writes_nothing` asserts the same thing behaviourally by
  comparing mtimes across a run.
  Full suite: see the PR body.

NEXT:      not attempted here, and both are the operator's or need review —
           (1) create the arming file BEFORE the next `-run` sync; (2) the
           precondition options on #1055. Also worth noting: the current run
           checkout is 4 behind main, so this detector reaches the live audit
           only when `-run` syncs — the same sync it exists to survive.
