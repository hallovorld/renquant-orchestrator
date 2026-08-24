# S3-P3: the shadow lane produces its own snapshot — the not-wired era ends

STATUS:   delivered. Two-part change: run_shadow_serving.sh invokes
          build_feature_snapshot.sh before its availability check, and the
          skip taxonomy is updated (producer-refused replaces not-wired).
WHAT:     since 2026-08-12 every session logged `SKIP not-wired: no producer
          exists`. With #1032 merged the producer exists; this PR closes the
          gap INSIDE the wrapper, so the daily flow needs no human step:
          scheduler → producer (from the prior session's prod served matrix)
          → serving replay.

          The load-bearing half is the CLASSIFICATION of what the producer
          did. #1032 gave it a two-valued exit contract; the wrapper must not
          collapse it back. Exactly ONE outcome is calm:

          | producer outcome        | wrapper verdict | ntfy | exit |
          |---|---|---|---|
          | rc=0, snapshot present  | proceed to serve | —   | 0    |
          | rc=3                    | producer-refused | no  | 4    |
          | **rc=0, NO snapshot**   | **producer-lied**| yes | 5    |
          | any other rc (1, 127…)  | producer-broken  | yes | 5    |

          A refusal is the producer WORKING (fail-closed provenance: stale or
          ambiguous served matrix, schema drift) — calm skip, reason logged,
          pointer to the producer's own log. Everything else is OUR breakage
          and pages. `rc=0` means "snapshot written", so rc=0 with no file is
          a producer FALSELY REPORTING SUCCESS — the loudest case, because
          nothing downstream would notice; it is emphatically not a refusal.
          Code 5 is deliberately absent from `ops/agent_inbox.py`'s
          DESIGNED_EXIT_CODES so the inbox treats it as UNKNOWN by
          construction rather than as a designed skip.
WHY/DIR:  this starts the S3-a/S3-b shadow window of the #1026 ladder: from
          the first post-merge session, paired intraday-vs-batch rows accrue
          automatically. ≥10 clean sessions is the gate before S3-c — which
          remains an explicit operator ask.
EVIDENCE:
  artifact:      the wrapper change + tests/test_shadow_serving_skips_leave_
                 evidence.py (updated messages + a new positive-path test that
                 builds a real served matrix in a fake root and asserts the
                 wrapper produced its own snapshot).
  prod or exp:   exp — no launchd change, no config; the deployed behaviour
                 changes only after merge + orch-run sync.
  existing data: mutation-verified the RIGHT way after doing it wrong once
                 (a stash swept the tests along with the wrapper, proving
                 nothing): NEW tests vs the UNWIRED wrapper = 3 failed —
                 exactly the refusal-message, distinguishability, and
                 positive-path tests; wired = 6 passed [VERIFIED].
                 Each row of the taxonomy above has its own named test:
                 rc=3 → `..._leaves_a_line_AND_the_distinct_exit_code`,
                 rc=1 → `..._BREAKAGE_is_not_reported_as_a_refusal`,
                 rc=0-no-file → `test_rc0_without_a_snapshot_is_breakage_
                 not_a_refusal`, rc=127 → `..._unexpected_producer_code_...`.
                 45 passed (wrapper + agent_inbox) [VERIFIED 2026-08-24].
  own defects:   TWO revisions of this PR collapsed the contract, both caught
                 by codex, both the same shape as the bug #1032 existed to
                 fix. (1) `PRODUCER_RC` was captured and never branched on, so
                 EVERY nonzero rc read as a refusal. (2) after fixing that,
                 rc=0-without-output was still merged into the refusal branch,
                 so a producer lying about success stayed silent. Recreating a
                 fixed failure ONE LAYER UP is evidently the default outcome
                 of wiring a two-valued contract into a caller that has only
                 ever had one calm path — the exit taxonomy above is written
                 into the doc so the next caller inherits it explicitly.
  best-known?:   yes — checkout-relative invocation ($(dirname $0)) so the
                 deployed run checkout calls its own producer.
  scope:        one wrapper + its test file + one stale description string in
                ops/agent_inbox.py (code 4 still said "not wired yet (no
                feature-snapshot producer)", which this PR makes false). No
                entry loop (S3-P4); the ntfy policy is unchanged in intent —
                refusals stay calm, real failures page — but the SET of things
                classified as "real failure" grows by the two breakage rows.
REVIEW:    codex (haorensjtu-dev).
