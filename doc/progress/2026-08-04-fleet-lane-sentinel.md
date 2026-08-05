# 2026-08-04 — GOAL-1: the fleet e2e lanes get a watcher

## The gap, measured tonight

The shadow-scorer sentinel patrols IN-PROCESS `shadow_models[]` entries (clf
leg, momentum v0, momentum fast). The GOAL-9 FLEET lanes are a different
animal — full e2e runs with their own broker tag, state file and runs DB,
executed as daily Step 5/5b/5c/5d/5e — and **nothing watched them**.

On their first evening the RCS lane fail-closed on an invalid component kind,
clearing 83 candidates, and that was discovered ONLY because a human read the
log. From the outside, a lane that fail-closes every session is
indistinguishable from a lane that runs fine: same rail, same non-fatal exit,
same silence.

## What it does

`ops/renquant104/fleet_lane_sentinel.py`, per session date, classifies each of
the five lanes:

| state | meaning | actionable |
|---|---|---|
| `RECORDED` | decision record exists (trade or honest no-trade) | no |
| `DORMANT` | the PINNED profile declares a `*_pending_first_artifact` component | no |
| `FAIL_CLOSED` | lane log carries a scorer fail-closed marker, or the record scored ZERO candidates (the measured RCS shape) | **yes** |
| `MISSING` | no record and the lane is not dormant | **yes** |

Two design rules the tests enforce:
- **Dormancy comes only from the pinned config.** A lane cannot be silenced by
  editing the sentinel; a test greps the module for mute-list names
  (`MUTED`/`SKIP_LANES`/…) and fails if one appears.
- **An absent profile is NOT dormant.** A vanished profile classifies as
  `MISSING` — calling it "declared dormant" would be exactly the silence this
  sentinel exists to remove.

## Verification

First live run, `--date 2026-08-04`, exit 1:

```
[RECORDED] RC  (alpaca_shadow_blend):      candidates=82 buys=1
[RECORDED] RSs (alpaca_shadow_blend_mom):  candidates=83 buys=1
[DORMANT]  Rf  … pinned profile declares a pending-first-artifact component
[DORMANT]  RCf … pinned profile declares a pending-first-artifact component
[FAIL_CLOSED] RCS (alpaca_shadow_blend_rb_mom): lane log carries a scorer
              fail-closed marker; record n_candidates=0
FLEET SENTINEL: 1 actionable lane state(s) on 2026-08-04
```

It reproduced tonight's real defect on its first run, and stayed quiet on the
two lanes whose dormancy is declared. Suite: 9 passed (healthy, the RCS
zero-candidate shape, log-marker-over-normal-record, missing, dormant,
absent-profile-is-not-dormant, no-mute-list, registry completeness, patrol
partitioning).

## Not yet scheduled

This PR lands the checker only. Scheduling (a launchd entry, or a step in the
daily wrapper after Step 5e) is a separate reviewed change — deploying an
unscheduled checker is the "deployed but dark" trap, so it is named here as
the explicit next step rather than assumed.
