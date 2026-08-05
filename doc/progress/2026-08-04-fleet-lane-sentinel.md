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

## Round 4: run it against its own incident, and fix what that exposed

Running the sentinel after RCS was repaired exposed a real semantic defect:
the lane had fail-closed at 21:02, was fixed, and re-ran healthy at 22:02 —
but the session log still carried the earlier marker, so the marker-first rule
kept alarming on an ALREADY-REPAIRED lane. A watcher that cannot see a repair
trains its reader to ignore it.

Now RECORD-FIRST: the per-run DB record (latest-wins) decides current state;
the log marker's job is the case the record cannot express — a lane that
refused before writing any record. A healthy latest record with an earlier
marker reports `RECORDED` **with the earlier failure named in the detail**,
never hidden. Re-run after the change: all 5 lanes accounted for, exit 0, with
RCS carrying the earlier-failure note.

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

## Round 3 (codex): no plist, no cadence guess — couple to daily completion

Codex refused round 2 for two correct reasons: a manifest entry without a
plist still leaves the job absent from LaunchAgents (a drift reminder is not a
watcher), and the schedule rationale was internally contradictory — it cited
"daily run starts 13:55 PT" and "Step 5-5e finished at 21:14 PT" and then
picked 15:30, conflating a MANUAL 20:18 run's clock with the scheduled run's.

Rather than re-measure a cadence, the trigger is now the right one: the
sentinel runs as the DAILY WRAPPER's last step, immediately after the Step-5e
legs it inspects. There is nothing to schedule (the daily job is already
installed and reviewed), nothing to guess, and no window in which the checker
inspects a still-running fleet. The launchd entry and its pending-install
state are removed; `PENDING_INSTALL` returns to empty, and a test now asserts
this sentinel must NOT acquire a launchd job, with the reason recorded.

The daily-wrapper invocation is the companion RenQuant PR (the wrapper logic
stays here, on the orchestrator's side of the boundary; the umbrella only
calls it).

## Round 2 (codex): the scheduled surface is part of the claim

The first version landed the checker alone and called scheduling a follow-up.
Codex refused that correctly: a checker nobody runs IS the deployed-but-dark
gap this sentinel exists to close, and the PR's own title claims the fleet
"gets a watcher". So the operational half is here too, on the orchestrator's
side of the daily-orchestration boundary:

- `ops/renquant104/fleet_lane_sentinel_daily.sh` — the scheduled wrapper,
  following the `momentum_train_weekly.sh` evidence contract (exec-redirect
  FIRST so a pre-exec death cannot vanish; every exit path writes a terminal
  marker). It passes the SESSION DATE explicitly (never the checker's own
  default — a wrapper firing after midnight UTC must still classify the
  session it was scheduled for), propagates rc=1 as an alarm, and the page
  carries the offending `[FAIL_CLOSED]`/`[MISSING]` lines themselves so the
  operator does not need the log to know which lane and why.
- `ops/launchd_manifest.json` — the job declared on the REVIEWED surface at
  daily 15:30 PT, with the schedule rationale recorded honestly: the first
  measured fleet-leg wall time (2026-08-04, ~55 min Step 5 → Step 5e under CPU
  contention) is the basis, and the comment says outright that a lane still
  running reads MISSING and pages, so the cadence must be re-measured against
  the fleet's steady state.
- The bootstrap itself is a machine action under the one-grant-per-batch rule,
  so the entry carries a dated `_pending_install` key and the test suite's
  `PENDING_INSTALL` named set gains exactly this job — both must be deleted in
  the SAME change that installs the plist, and until then the drift scan
  alarming on a declared-but-uninstalled job is the DESIGNED reminder.

Tests for the scheduled surface: session-date passthrough, rc=1 propagation +
paging with the lane lines, exec-redirect ordering + terminal markers, and the
manifest declaration with a bounded single pending key. Suite: 31 passed
(sentinel + run-surface drift together).
