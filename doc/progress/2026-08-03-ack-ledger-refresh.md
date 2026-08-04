# Ack-ledger refresh — the expired cohort re-affirmed with diagnoses, one row retired

**Date:** 2026-08-03 · `renquant-orchestrator` · GOAL-1 / ops-audit burn-down #769 item 8

STATUS:    ledger + test pins; no machine action (the audit is invoked by the
           installed ops-audit job).
WHAT:      4 rows RE-AFFIRMED (fresh diagnoses, staggered expiries, resolvable
           citations), 1 retired, 1 bare ref fixed.
WHY:       The scheduled audit measured: 5/10 expired since 07-31, 9 rows
           with wrong-event expiry clocks, 1 unresolvable bare "#75", two
           expiry cliffs.  [VERIFIED — ack_ledger_audit 2026-08-03]

| row | action | expiry | note |
|---|---|---|---|
| retrain-panel104 | re-affirm | 08-12 | two-era diagnosis (era A parity RESOLVED; era B chronic gate REJECT ACTIVE); decision surface backtesting#101; a stamped RFC#210 fallback promotion ALSO clears it. 08-12 = first weekday after the 08-09 run |
| weekly-wf-promote | re-affirm | 08-13 | same root, staggered one day |
| monthly-meta-label-retrain | re-affirm | 08-16 | bare "task #75" → renquant-orchestrator#771 |
| rq104-degradation-sentinel | re-affirm | 08-17 | self-referential detection row, semantics unchanged |
| rq104-liveness | RETIRE | — | EXPIRED_CONDITION_MET: the firing it waited on passed |

Two measured traps caught during the work, both documented in the commits:
1. **Expiries beyond the acked_at+14 backstop are dead letters** — the first
   stagger (08-18..20) measured as all capped at 08-17; restaggered within
   the backstop (ramp 1@08-12 → 9@08-17, no new cliff).
2. **The audit clock is the committer's LOCAL date** (%cI date part), not
   UTC — an 08-04 UTC guess measured lag −1; 08-03 measures lag 0.

Checkability moved: narrative-only rows 6 → 2 (the two genuinely unbindable
ones); bare-refs-without-qualified-ref 1 → 0. Suite 5494 passed / 0 failed.

## Revert

git revert both commits; the audit then re-reports the expired cohort — the
designed reminder returns.
