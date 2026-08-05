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

## Review round 2 — the two ways it WAS still a silencer

Codex verified the wrapper's step order against `daily_104.sh` (prod Step 3
returns before the Step 5 lanes, so the ordering premise holds) and then found
two real holes:

1. **"Cannot read the evidence" was folded into "there is no evidence."**
   `_tag_record` returned `None` for any `sqlite3.Error`, so a corrupt or
   unreadable `runs.alpaca.db` after a REAL session would downgrade a genuinely
   failed lane from actionable `MISSING` to quiet `NOT_YET_RUN`. The session
   check is now **three-valued** — `started` / `not_started` / `unknown` — and
   `unknown` NEVER downgrades: the lane stays `MISSING` and the detail says the
   prod DB could not be read.
2. **I erased the pre-session detection case.** A vanished pinned profile is a
   CONFIG defect that is true whether or not anything ran, and my updated test
   wrote a prod row first, hiding that. A missing profile now has its own
   actionable state, `PROFILE_ABSENT`, checked BEFORE the session state and
   never downgraded by it — asserted against all three session states.

Codex also noted, and this is recorded rather than fixed: the prod row is
written LATE in `RunnerAdapter.commit()`, after state save and order
application, so a session that died mid-flight can leave no prod row. That is
precisely why `unknown` exists and why a lane with its OWN evidence (a record,
or a fail-closed marker) is judged on that first. And `NOT_YET_RUN` still exits
0, so Step 6 does not page differently — the wrapper's success branch still
collapses "not run" and "all accounted for" into one rc, distinguished only in
the printed line.

## Review round 3 — existence is not enough

Codex re-pushed the edge cases (prod DB with no table, a prod row for a
different date, an empty prod DB file, an unreadable LANE db while prod ran) and
confirmed each behaves correctly, then found the last hole:

**An EXISTING but UNPARSEABLE pinned profile was still silenced until the
session ran.** `profile_absent()` checked only `exists()`; `lane_is_dormant()`
swallows a JSON error and returns False; so `classify()` fell through to the
session check and reported the quiet `NOT_YET_RUN`. And it is not hypothetical —
codex traced it: the wrapper gates these lanes on **file existence alone**
(`daily_104.sh`) and then hands the path to the runner, whose loader
**hard-parses** it with `json.loads` (`renquant_strategy_104/config.py`).

`profile_absent` is now `profile_defect`, returning a REASON: absent, unreadable,
invalid JSON, or not a JSON object. It is checked before dormancy and before the
session state and is never downgraded by either. The state is renamed
`PROFILE_DEFECT` to match what it now covers. A test asserts a valid profile —
including a dormant one — is not a defect, so the check cannot become a
false-positive generator.

## Review round 4 — dormancy was short-circuiting before evidence

The last hole, and it was in the ORIGINAL sentinel, not in this change:
`classify()` returned `DORMANT` **before looking at the lane's row or log**.
But the fast lanes still EXECUTE daily (`daily_104.sh` Steps 5c/5e) — the
pending-first-artifact marker only declares that the fast artifact is not
published yet; it does not make every later failure benign. Codex reproduced a
dormant lane with BOTH a zero-candidate row and a `panel_scorer_load_failed`
marker reporting as plain quiet `DORMANT`, with no mention of either.

Dormancy is now judged **against** the evidence:

- dormant + no evidence → plainly quiet, unchanged;
- dormant + fail-closed marker → still quiet (a lane missing its declared-pending
  component is *expected* to fail closed) but the line **says so**, with the
  record id. A quiet state that hides its evidence is how a reader stops being
  able to tell quiet from broken;
- dormant + a record that actually **SCORED** → **actionable**. Scoring
  contradicts "the artifact is not published yet", so the declaration is STALE —
  and a stale dormancy declaration is precisely how a lane goes dark without
  anyone noticing.

A test pins that the ordinary dormant case stays quiet and silent, so this does
not become a noise generator.

Suites: 34 in this file · 5622 passed, 2 skipped repo-wide.
