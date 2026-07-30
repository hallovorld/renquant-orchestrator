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

### 3.1 REVISION — `RQ_ROOT` being set is not an acknowledgement

The first version of this proposal said: refuse unless the script sits under the run
checkout **or** `RQ_ROOT` was set explicitly. Codex round 1: *"an inherited shell
environment, editor task configuration, or copied worktree command can set that generic
variable accidentally, recreating the bypass the proposal is meant to stop."*

**Correct, and it makes the escape hatch worthless.** `RQ_ROOT` is a *destination*
variable that already exists for ordinary reasons — it is exported in experiment shells,
set in editor run configurations, and carried into subprocesses. A guard whose opt-in is
satisfied by a variable people already set for unrelated purposes converts nothing into a
choice; it just adds a condition that is usually already true. I had conflated two
separate questions:

| question | variable |
|---|---|
| **where** should this run write? | `RQ_ROOT` |
| **am I permitted** to write *production* from an unreviewed copy? | must be its own thing |

### 3.2 The guard, revised

Two facts are computed independently, both canonicalised (§4.3):

* `SELF` — the wrapper's own resolved directory;
* `TARGET` — the resolved root the run would actually write to, *after* defaulting.

> **Refuse only at the intersection:** `SELF` is not under the reviewed run prefix
> **AND** `TARGET` resolves to the production umbrella **AND** the dedicated
> acknowledgement is absent.

The acknowledgement is a **purpose-named variable that exists for no other reason**, and
its value must name the target rather than being a truthy flag:

> `RQ_PRODUCTION_WRITE_ACK="<the absolute canonical production root>"`

A bare `=1` is rejected. This matters because the accidental-inheritance failure mode
codex identified is exactly how a `=1` flag propagates: a value that must equal the very
path being written cannot be set "in passing", and if it is inherited from a shell that
genuinely was pointed at production, that is not an accident.

**What this buys that the first version did not:**

- **Experiments against a sandbox need no acknowledgement at all.** `RQ_ROOT=/tmp/x`
  from a copied worktree just runs. The first version demanded ceremony for the common,
  harmless case and accepted a stray variable for the dangerous one — backwards.
- **The dangerous case is the only one that asks.** Unreviewed copy + production target.
- **Zero behaviour change for production.** Scheduled jobs sit under the run prefix, so
  the first conjunct is false and the guard never fires. No plist edits, no landings.
- **It fails closed and says why**, naming `SELF`, `TARGET`, and the exact variable to
  set.

## 4. Settled by review round 1 — these were open questions, now decided

Codex asked for these to be specified *before* the design is accepted rather than
deferred to implementation. Agreed: each is load-bearing on whether the guard works.

### 4.1 Trusted source for the allowed run prefix

**Decided: an absolute literal in each wrapper, compared against `realpath`, with the
manifest as the reviewed cross-check — not a value read from the environment.**

The prefix must not be redefinable by the thing being guarded. That rules out reading it
from an env var (the copy inherits whatever the copier set) and from a path relative to
the wrapper (a copy's relative path resolves to the copy). An absolute literal has the
property that a copy carries it *unchanged* and therefore fails its own check.

The 11-places-to-update objection is answered by a test, not by indirection:
`ops/launchd_manifest.json` already records every job's `program_args`, so CI asserts
that **every guarded wrapper's literal equals the prefix the manifest actually invokes
it from**. If the checkout moves, the manifest changes, and the test names all 11 files.
Shell-side JSON parsing is avoided entirely; the coupling lives in CI where it can fail
loudly.

**Stated limit, because the alternative is to overclaim:** a copy whose *literal is
edited* defeats this, as it defeats any guard implemented inside the thing it guards.
The threat model is an **accidental** copy — a worktree, a backup, a scratch clone —
not an adversary. A guard that claimed to stop the latter would be lying.

### 4.2 Scheduled production entry points vs the one dev-checkout job

Codex is right that a uniform policy is wrong here. The measured roots are `RenQuant`
**32**, `renquant-orchestrator-run` **18**, `renquant-orchestrator` **1**
`[VERIFIED — manifest parse, 2026-07-30]`. That last one is a **scheduled job that
legitimately runs from the dev checkout**, so a rule reading "not under the run prefix ⇒
refuse" would break it — the guard would fire on a reviewed, intended configuration.

**Decided:** the allowed prefix is **per-job, taken from the manifest row that invokes
that wrapper**, not a single global constant. A wrapper invoked from the dev checkout has
the dev checkout as its reviewed location. The invariant is *"running from where the
reviewed manifest says this job runs from"*, which is the property actually wanted;
"under `-run`" was a proxy for it that happened to hold for 11 of 12.

The unreviewed case is then exactly what it should be: **a wrapper with no manifest row
has no reviewed location**, and §4.3 applies.

### 4.3 `run_liveness_check.sh` — no manifest row

**Decided: guard it with `TARGET`-only logic and no reviewed prefix.** With no manifest
row there is nothing to derive a location from, so the location conjunct cannot be
evaluated and the guard reduces to: *writing production requires the acknowledgement,
wherever you are.* Deleting it is still defensible and remains on the table, but it is a
separate change with its own blast radius; leaving it unguarded because it is awkward is
the one option ruled out.

### 4.4 Canonicalisation

**Decided, and specified rather than left to implementation** — this is the class of
hole that makes a guard pass forever:

* both `SELF` and `TARGET` are canonicalised before comparison, resolving symlinks and
  `..`;
* comparison is on **path components**, not string prefixes, so
  `/x/renquant-orchestrator-run-backup` does not match a `/x/renquant-orchestrator-run`
  prefix;
* if canonicalisation **fails** (target does not exist yet, permission error), the guard
  **refuses** rather than falling back to the raw string. An unresolvable path is
  unverifiable, and this programme has repeatedly shipped guards that treated
  "could not check" as "checked and fine".
* macOS `/bin/sh` has no `realpath(1)` guarantee; the resolution helper and its fallback
  are part of the implementation PR and must carry a test that a symlinked copy is
  rejected.

## 4b. Rollout

One file first (`run_quote_logger.sh`, highest blast radius) as a shape to review
against, then a mechanical sweep once the shape is agreed. Unchanged from the first
version and unchallenged in review.

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
