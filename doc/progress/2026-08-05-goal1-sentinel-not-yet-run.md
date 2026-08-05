# 2026-08-05 — GOAL-1: the fleet sentinel could not tell "has not run" from "has failed"

## The reproduction, with my own eyes

At **03:45 PT on 2026-08-05** — about nine hours before the daily run — I ran the
fleet sentinel and it printed `[VERIFIED — this session]`:

```
[MISSING] RC  (alpaca_shadow_blend):        no runs-DB record for this session …
[MISSING] RSs (alpaca_shadow_blend_mom):    no runs-DB record for this session …
[MISSING] RCS (alpaca_shadow_blend_rb_mom): no runs-DB record for this session …

FLEET SENTINEL: 3 actionable lane state(s) on 2026-08-05
```

Exit 1, three alarms, on a day where **nothing had run at all**. That is exactly
the GOAL-1 defect shape: a state in which a crash and a not-yet-started day are
indistinguishable to the reader. A watcher that cries wolf every morning is a
watcher the operator learns to skip — which is how the real alarm gets missed.

It happens to be quiet in production today only because the sentinel runs as
Step 6 of the daily wrapper, *after* the lanes. Any manual or early invocation —
exactly what an operator does when they are worried — produces the false alarm.

## The fix

A new state, **`NOT_YET_RUN`**, and one piece of evidence to reach it: the PROD
lane's own runs-DB row. Prod runs FIRST in the wrapper and every fleet lane is a
later step, so **no prod row means no session**, and a lane that was never asked
to run has not failed.

### Why this is not a silencer

That distinction is the whole risk of this change, so it is nailed down three
ways:

- **It can only fire when PROD is also absent.** If prod ran and a lane did not,
  the lane is still `MISSING` and still actionable. A test asserts exactly this.
- **A lane's own row is not a session.** `session_started` reads the PROD tag,
  never the lane's; a test writes a lane row and asserts it still reports False.
- **A lane that DID record a fail-closed run is judged on its own evidence** and
  is never downgraded, even with no prod row. Test included.
- **Dormancy still wins**, because it is a config fact independent of whether
  anything ran.

And the all-clear now **says which all-clear it is**: on a date with no session
it prints "the daily session has NOT RUN … nothing to account for yet" rather
than "all 5 lanes accounted for". A silent all-clear on a day nothing ran would
be the same ambiguity one level up.

## A second bug, found by writing the test

The test for the new state passed against the **live** data directory while
monkeypatching the module's constants. Cause: `classify`, `patrol` and
`session_started` bound `DATA`/`LOGS`/`PINNED_CONFIGS` as **parameter defaults at
import time**, so `main()` always read the real tree and a redirected run
silently measured production. Directories now resolve at CALL time, pinned by a
test.

A watcher that reads production when you point it somewhere else is worse than
one that errors.

## Contract change, stated plainly

Two existing tests asserted `MISSING` for a lane with no record and **no prod
row**. Under the new contract that is `NOT_YET_RUN`. Both were updated to write
a prod row first, so they keep testing what they meant: *a lane that did not
record on a day the session ran is an alarm.*

## Measured after

- `2026-08-05` (nothing run yet): exit **0**, "the daily session has NOT RUN".
- `2026-08-04` (a real session): exit **0**, "all 5 lanes accounted for" —
  unchanged.

Suites: 23 in this file · 5611 passed, 2 skipped repo-wide.
