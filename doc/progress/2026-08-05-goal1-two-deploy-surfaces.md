# 2026-08-05 — GOAL-1: the ops tools deploy from a surface nobody was tracking

## The measurement

The daily wrapper runs the fleet sentinel from a checkout the pin lockfile does
not govern `[VERIFIED — this session]`:

```
scripts/daily_104.sh:977
FLEET_SENTINEL="${RQ_ORCH_RUN_DIR:-/Users/renhao/git/github/renquant-orchestrator-run}/ops/renquant104/fleet_lane_sentinel_daily.sh"
```

**21 launchd plists** point at `renquant-orchestrator-run`. Everything under
`ops/` executes from there: the fleet sentinel, the rq105 liveness probe, the
ack-ledger audit, the silent-refusal sentinel.

`subrepos.lock.json` — the surface orch#808 was written against — governs
`RenQuant/.subrepo_runtime/repos/*`, the **libraries** the pipeline imports. It
never touches the run checkout.

### Why that matters for GOAL-1 specifically

Measured before the incident below: the run checkout at `3b65bef` carried **0**
occurrences of `NOT_YET_RUN` / `EvidenceUnreadable` / `PROFILE_DEFECT`, while
`main` carried **14**. So every sentinel hardening merged tonight
(orch#811 / #812 / #813) — including the fix for a sentinel that folded "cannot
read the evidence" into "no evidence" — **was merged and not running**, and a
grant on orch#808 alone would not have changed that while reading as "deployed".

That is *merged is not deployed* with an extra layer: two surfaces, one tracked.

## The incident that exposed it

I advanced that run checkout **without authorisation** at 06:46 PT today, by
running `git checkout main && git pull` in a shell whose `cd` had leaked out of a
compound command into the run checkout. Full report, blast radius and the exact
revert command: **orch#818**. Nothing uncommitted was clobbered; the pre-incident
sha is intact; I have not touched it since, and the keep-or-restore decision is
the operator's.

I found the two-surface gap *while investigating my own mistake*. The gap was
real before the mistake and would still be real if it had not happened.

## What this adds to the record

- orch#808 is retitled and corrected to name **both** surfaces, with a table of
  what each governs and how each advances.
- The run checkout is **not** in `ops/launchd_manifest.json` `[VERIFIED — grep]`,
  so the daily run-surface drift scan does not watch the thing 21 jobs execute.
  That is the next reliability gap to close, and it is a design question (what
  "correct" means for a checkout that is routinely fast-forwarded), not a patch.

## The working rule I am adopting

**Never run a git command in a compound after a `cd` into another repository.**
Every git invocation against a repo I am not standing in takes `git -C <path>`
explicitly, so the target lives in the command rather than in shell state.
