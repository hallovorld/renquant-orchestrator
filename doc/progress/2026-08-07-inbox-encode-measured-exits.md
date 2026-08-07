# 2026-08-07 — Three "undocumented" exit codes were documented all along

STATUS:   READY FOR REVIEW. No new tests needed — the existing
          `test_designed_exit_codes_are_still_true_of_their_sources` re-greps
          every cited source, so each new row is measured by the suite that
          already runs. 27 inbox tests pass
          `[VERIFIED — python3 -m pytest tests/test_agent_inbox.py -q]`.

WHAT:     Encodes four measured exit contracts into `DESIGNED_EXIT_CODES`:
          `rq104-silent-refusal` 1, `rq104-degradation-sentinel` 1 and 3,
          `rq105-liveness` 1. All four are ACTIONABLE — each means "I found
          something", not "nothing to do".

WHY/DIR:  The inbox's UNKNOWN bucket exists to drive exactly this work, and it
          did. Measured 2026-08-07
          `[VERIFIED — rq104_silent_refusal_sentinel.py:357,
          sentinel_receipt.py:46, rq104_degradation_sentinel.py,
          rq105_liveness_check.py:496, read directly this session]`:

          | job | code | contract | where |
          |---|---:|---|---|
          | `rq104-silent-refusal` | 1 | `return 1 if findings else 0` | `rq104_silent_refusal_sentinel.py:357` |
          | `rq104-degradation-sentinel` | 1 | `EXIT_ALARMS = 1` | `sentinel_receipt.py:46` |
          | `rq104-degradation-sentinel` | 3 | `EXIT_INTERNAL = 3` | `rq104_degradation_sentinel.py` |
          | `rq105-liveness` | 1 | collector issues → "rq105 DOWN" alert | `rq105_liveness_check.py:496` |

          UNKNOWN drops **10 → 7**; designed-but-actionable rises **4 → 7**
          `[VERIFIED — python3 ops/agent_inbox.py --json, len(launchd_unknown)
          and len(launchd_designed_actionable), before this commit's parent
          a9d7b795 vs. after b4599472]`.

## A CLAIM OF MINE THIS RETRACTS

I reported two of these as **contract mismatches** — "`rq104-degradation-sentinel`
exits 1 but its source documents `EXIT_INTERNAL=3`", "`rq104-silent-refusal`
exits 1 but documents 4/5" — and carried them in the loop prompt as real
follow-ups. **Both are wrong. There was no mismatch.**

What actually happened is that my probes could not see the contracts:

* I grepped for `EXIT_[A-Z_]+ = <n>` **inside the sentinel**, but `EXIT_ALARMS`
  is defined in `sentinel_receipt.py` and imported. Searching the consumer for a
  constant declared in the provider finds nothing and looks like absence.
* I grepped for bare `exit <n>` literals, which cannot match
  `return 1 if findings else 0`.
* For `rq104-silent-refusal` I read the WRAPPER's `exit 4` / `exit 5` and took
  them for the job's contract. The wrapper's last line is `exit "$RC"` — it
  **passes the module's code through**; 4 and 5 are its own prereq/commit
  failures and never reach a normal run.

**"I could not find the contract" is not "there is no contract."** The
difference is one more read, and the earlier claim was published without it.
Same family as reading `alert_incidents.state` as a severity — a partial view of
a real mechanism, reported as a defect in it.

EVIDENCE:
artifact:      `ops/agent_inbox.py`
prod or exp:   **neither** — a read-only reporting tool; no job, config, or live
               surface changes.
existing data: the four source files cited above, read directly this session.
best-known?:   yes for these four. Seven codes remain UNKNOWN and are honestly
               labelled so.
scope:         one dict; no logic change.

NEXT:     The seven still-UNKNOWN exits (`monthly-calibrator-refresh`,
          `retrain-panel104`, `weekly-apy104`=2, `rq104-scorer-identity`,
          `agent-pr-loop`, `shadow-ab-daily`=3, `weekly-wf-promote`)
          `[VERIFIED — python3 ops/agent_inbox.py --json,
          launchd_unknown, this session]` — several live in the umbrella's
          `scripts/`, so their contracts must be read there rather than
          assumed absent, which is the mistake this PR corrects. Do not
          encode a row without a source + probe the test can re-grep.

## NOT ESTABLISHED

1. **That the four newly-encoded jobs are currently healthy.** They are exiting
   nonzero *by design*, which now means the inbox files them as WORK — the
   opposite of dismissing them. What each one found is undiagnosed.
2. **That ACTIONABLE is right for all four.** Each says "I found something", so
   actionable is the conservative reading; if one turns out to be routine, the
   row should move, not the bucket.

## REVERT

Delete the three job entries added to `DESIGNED_EXIT_CODES`
(`rq104-silent-refusal`, `rq104-degradation-sentinel`, `rq105-liveness`) and
their leading comment. No other file changes.
