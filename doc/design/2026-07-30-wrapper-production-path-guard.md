# Any copy of a job wrapper writes production by default — for DISCUSSION

**STATUS: DESIGN PROPOSAL. Nothing is implemented in this PR.** No wrapper is
changed, no plist is touched, no job behaviour moves. Opened for review before the
change, per the operator's 2026-07-30 directive that behaviour changes get a design
PR first.

**Date:** 2026-07-30 · GOAL-5 (daily-run reliability) · `renquant-orchestrator`
**Occasioned by:** the stray process terminated today (issue #639) — an orphaned
wrapper from a *worktree* that had held write access to production paths for
**7 days 18 hours**.

---

## 1. Bottom line

Every job wrapper resolves the production umbrella **by default**:

```sh
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
```

That default is **correct for the scheduled job** and **identical for every other
copy of the file**. A wrapper run by hand from an experiment worktree therefore
writes the production day log, the production crash log, the production data
products, and fires production ntfy — with no warning and no guard.

**Measured scope** `[VERIFIED — grep over ops/ and scripts/, 2026-07-30]`:

| | count |
|---|---:|
| wrappers carrying the production default | **12** |
| of those, launchd entry points | **11** (11 jobs) |
| of those, invoked by nothing | **1** — `ops/renquant105/run_liveness_check.sh` |
| wrappers that check which checkout they run from | **0** |

The orphaned one is not a rounding error: the rq105 liveness plist invokes the
`.py` **directly**, so its wrapper has no caller and no output file has ever been
written through it `[VERIFIED — manifest + forensics sweep, 2026-07-30]`.

Worst single case: `run_quote_logger.sh` has **22** references to production paths
`[VERIFIED — grep -c]`, including `FEED_PATH`, which **appends** to
`logs/renquant105_pilot/intraday_ticks.jsonl` — the 600 MB tick feed that is the
sole upstream input to the postclose pairing logger, to shadow-serving's replay, and
to two of the rq105 liveness staleness checks. A stray copy does not merely write a
log; it can interleave rows into the feed three other jobs read.

## 2. Why the obvious fix is the wrong one

**"Remove the default; require `RQ_ROOT` explicitly."** This breaks all 11 scheduled
jobs unless each plist gains an `EnvironmentVariables` block — **11 plist edits, so
11 machine landings**, each needing authorisation, on the same day the run checkout
is already 110 commits stale. The remedy would be more dangerous than the defect.

It also gets the subject wrong. The production default is not the bug. The bug is
that **the default does not depend on who is running it**.

## 3. Proposal — the wrapper checks where it is running from

A wrapper knows its own path. **Correction to a claim I nearly shipped in this
document:** it is *not* true that every `program_args` entry begins with the run
checkout. Measured, the 41 jobs' arguments resolve to three roots —
`RenQuant` **32**, `renquant-orchestrator-run` **18**, `renquant-orchestrator`
**1** `[VERIFIED — manifest parse, 2026-07-30]`. I wrote the stronger claim from
memory and it was wrong; the guard has to rest on the narrower fact below.

The narrower fact does hold: **all 11 launchd-invoked wrappers carrying the
production default are invoked from `renquant-orchestrator-run/ops/`, and none is
invoked from anywhere else** `[VERIFIED — set intersection of the grep hits with
every job's program_args, 0 exceptions]`. That is the property the guard can use.

So:

> If the script's own resolved directory is **not** under the reviewed run checkout,
> **and** `RQ_ROOT` was not set explicitly, **refuse to run** with a message naming
> both facts.

Properties, and why this shape rather than another:

- **Zero behaviour change for production.** The scheduled jobs run from the reviewed
  checkout and take the same default they take today. Nothing to re-authorise.
- **Zero plist edits, zero machine landings.**
- **An experiment can still touch production — deliberately.** Setting `RQ_ROOT`
  explicitly is the opt-in. The guard converts an accident into a choice; it does
  not remove the capability.
- **It fails closed and says why.** "This copy is at `<path>`, which is not the
  reviewed run checkout. Set `RQ_ROOT` explicitly to run it anyway."

## 4. What review needs to settle before implementation

1. **Where does the expected prefix come from?** Hardcoding
   `renquant-orchestrator-run` in 11 files creates 11 places to update if the
   checkout ever moves. Reading it from `launchd_manifest.json` at run time makes
   every wrapper depend on parsing JSON in shell. **Neither is obviously right** and
   I would rather be told than choose quietly.
2. **What about the wrapper nothing calls?** `run_liveness_check.sh` has no manifest
   row, so there is no reviewed location to derive an expected path from. Guarding it
   and deleting it are both defensible; leaving an unguarded, uncalled script that
   writes production is not.
3. **Symlinks and `cd`.** The resolved path must be canonical, or a symlinked
   worktree defeats the check. This is exactly the class of hole that makes a guard
   pass forever, so the resolution method is part of the design, not an
   implementation detail.
4. **Rollout order.** 11 files at once, or the highest-blast-radius one
   (`run_quote_logger.sh`) first as a shape to review against? I lean to the second
   — one file, one reviewable diff, then a mechanical sweep once the shape is agreed.

## 5. What this does NOT fix

- The stray that occasioned it is already dead (#639); this prevents the next one.
- It does **not** stop a wrapper *inside* the reviewed checkout from misbehaving.
- It does **not** address the missing `KeepAlive` on the installed quote-logger
  plist, which remains a separate, still-unauthorised machine landing.
- It is **not** a substitute for the drift scan gaining schedule/KeepAlive coverage
  (#639) — that guard and this one fail in different directions.

## 6. Explicitly not proposed

No implementation in this PR. No production surface change. No plist edit. No
change to any wrapper's behaviour when run from the reviewed checkout.


## 7. Adjacent finding from the same measurement — filed here, not fixed here

**`com.renquant.crypto-session` runs from the DEV checkout**, not the run checkout:

```
/Users/renhao/git/github/renquant-orchestrator/scripts/crypto_session_runner.py
```

`[VERIFIED — launchd_manifest.json, the single entry of 41 rooted at
`renquant-orchestrator`]`. That is the checkout an agent actively edits and switches
branches in. Whatever branch is checked out at 
its fire time is what the scheduled job executes — the code it runs is not a
reviewed artifact, it is whatever the working tree happens to hold.

Two things make this worth its own decision rather than a quiet path swap:

- The G2 crypto programme was **KILLED on 2026-07-18** by its preregistered gate, so
  this job may be vestigial. Repointing a job that should be retired is the wrong
  fix.
- Repointing it *is* a machine landing.

Not proposed here. Raised so it is on the record with the measurement attached.
