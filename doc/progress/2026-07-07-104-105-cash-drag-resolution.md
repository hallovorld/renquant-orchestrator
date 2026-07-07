# 104 / 105 cash-drag resolution — progress record

STATUS: design PR artifact. Docs only. No live behavior change in this PR.
DATE: 2026-07-07
ARTIFACT: `doc/design/2026-07-07-104-105-cash-drag-resolution.md`

WHAT:
This design narrows the cash-drag conversation into an implementation order instead of another
open-ended option list.

KEY DECISIONS:
1. 104 primary fix = fractional shares.
2. 104 secondary fix = parking sleeve, but SGOV-first.
3. 104 lane-A exposure knobs (`top_n`, `qp_cash_drag_lambda`, etc.) move only AFTER the
   mechanical drag is removed and re-measured.
4. 105 is not a live deployment-optimization target yet; only compatibility and measurement prep
   are justified now.

WHY:
- 104 has a real deployment problem: the 2026-06-29 live-book record showed only `$827 / $8,730`
  deployed on that run; the 2026-07-02 canonical KPI scorecard measured deployed fraction
  `0.2468`, trailing-5 mean `0.2051`, and average cash weight `76.1%` across the last 10
  canonical sessions.
- The 2026-06-29 readonly `8/3 -> 10/4` replay showed slot-raising is not the root fix: it added
  only `~$427`, admitted weak marginal exposure, and still rounded AVGO/BLK/GS to zero shares.
- Repeated BLK / AVGO drops on 2026-07-01 and 2026-07-02 confirm the same whole-share sizing
  artifact.
- 105 is in a different state: the architecture RFC keeps Stage 1 operations-only and frozen, and
  the recommitted 2026-06-27 phase-minus-1 evidence records a standing soft NO-GO on intraday
  directional alpha at realistic IC / cost assumptions.

PRACTICAL CONSEQUENCE:
- We should not burn another cycle leading with `top_n`/penalty/gate-loosening experiments.
- We should not use a SPY sleeve as the default "cash fix"; that changes portfolio beta, not just
  carry.
- We should not turn 105 into a deployment project before 105 itself has an economic green light.

NEXT AFTER MERGE:
1. Start the cross-repo 104 fractional-shares implementation chain.
2. Keep parking-sleeve implementation SGOV-first and shadow-first.
3. Re-open exposure-policy experiments only after the new baseline is measured.
4. Limit 105 near-term work to compatibility / instrumentation unless a separate authorization
   artifact expands scope.
