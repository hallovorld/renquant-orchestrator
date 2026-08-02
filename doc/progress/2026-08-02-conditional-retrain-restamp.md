# GOAL-1: conditional-retrain104's day-one EXPIRED_CONDITION_UNMET finding — diagnosed and re-stamped

STATUS: complete.
WHAT: the ack row is re-stamped (acked_at 2026-08-02) with the measured current
diagnosis, replacing an obsolete May-era reason (IAC/RenQuant#495); pin tests
updated to the re-measured ledger (n_expired 6→5; 08-15 fires 6→5; the one
fresh row is this re-stamp; union assertion covers fresh rows).
WHY/DIR: #752's new audit semantics fired EXPIRED_CONDITION_UNMET on this row
on day one. Following the finding to ground truth was the point of building it.
EVIDENCE:
  artifact:      ops/renquant104/sentinel_acks.json (one row) +
                 tests/test_ack_ledger_audit.py (three pins)
  prod or exp:   prod — the ops alarm-disposition ledger
  existing data: the job's own daily logs: runs daily and logs cleanly; on
                 2026-07-31 a REAL VIX anomaly (−7.26% vs the 5% threshold)
                 fired the gated weekly-promote chain, which FAILED within 5
                 seconds — the same chronic never-completed WF-promote root the
                 weekly-wf-promote row acks open-endedly. So the clearing
                 condition WAS tested on 07-31 and failed honestly; the old
                 reason described a different, May-era failure. `[VERIFIED —
                 logs/conditional_retrain_104/2026-07-31.log +
                 2026-07-28.log, read 2026-08-02]`
  best-known?:   yes — replaces an obsolete reason with the measured one; the
                 clears_when condition is unchanged (it is the right one) and
                 clears exactly when the shared WF-promote root clears
  scope:         one ledger row + three test pins; 171/171 across the six
                 sentinel/ack suites `[VERIFIED — pytest, 2026-08-02]`.
                 Investigation note: an early "the job is dead since May"
                 hypothesis was an artifact of an eza ls-alias mangling
                 `ls -t`; plain ls showed daily logs through 07-31 — recorded
                 so nobody re-walks that false trail.
NEXT: nothing on this row until the WF-promote root clears (its own track).
AC6 gate-design rule: N/A — ops ledger + tests only.
