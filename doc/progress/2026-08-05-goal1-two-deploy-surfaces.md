# 2026-08-05 — GOAL-1: two deploy surfaces, both tracked; one grant covered only one

## The claim I had to withdraw first

An earlier version of this document said the `renquant-orchestrator-run`
checkout was "a surface nobody was tracking". **That is false**
`[codex on orch#819, verified against source]`:

- `ops/launchd_manifest.json` **in this repo** carries **22** occurrences of
  `renquant-orchestrator-run` — all 21 jobs' ProgramArguments are committed. I
  had grepped `RenQuant/ops/launchd_manifest.json`, a path that does not exist,
  and read the empty result as absence.
- `ops/run_surface_drift_check.py:138-140` checks that checkout **explicitly**,
  against its fetched `origin/main`, and its docstring records the very incident
  it was built for: *"the renquant-orchestrator-run checkout sat ~130 commits
  behind origin/main carrying six uncommitted hotfixes; nothing tracked either
  fact."*

So the tracking exists, it is committed, and it is scheduled. **The thing I
"found" was already found, and fixed, before tonight.**

## What survives, and it is narrower

There really are **two** deploy surfaces, and they advance by **different
mechanisms**:

| surface | governs | correct state | how it advances |
|---|---|---|---|
| `subrepos.lock.json` runtime repos | the libraries the pipeline imports | each repo **at its pinned commit** | a reviewed PR editing the lockfile |
| `renquant-orchestrator-run` | every `ops/` tool the 21 launchd jobs execute | **`origin/main`** | `git pull --ff-only` on the checkout |

Both are watched by the same scan. But note what the second row means: for the
run checkout, **"correct" is `main`, not a pin.** Merging to `main` *is* the
review gate for it; the checkout only has to catch up.

### The consequence that is actually load-bearing for GOAL-5

**orch#808 asked for the lockfile pins only.** Granting it would have advanced
the libraries and left every `ops/` tool — the fleet sentinel, the rq105 probe,
the ack-ledger audit — untouched, because the lockfile does not govern them.
Measured before today's sync: that checkout carried **0** occurrences of
`NOT_YET_RUN` / `EvidenceUnreadable` / `PROFILE_DEFECT`, while `main` carried
**14** — i.e. the whole sentinel hardening was merged and not running.

That gap is real and orch#808 is corrected to name both surfaces. It is a gap in
**my grant request**, not in the project's tracking.

## The incident that ran alongside this

I fast-forwarded that run checkout **without authorisation** at 06:46 PT, when a
`cd` leaked out of a compound command (orch#818, with the exact revert).
Given the above, the honest reading is: the checkout was **in drift** (behind
`main`, which the scan alarms on) and my mistake moved it **into** the state the
scan requires. Unasked — not undesired. Restoring `3b65bef` would put it back
into drift and the next scheduled scan would alarm; that is stated on #818 so the
choice is made knowing it.

## Two working rules from this

1. **Never run a git command in a compound after a `cd` into another
   repository** — always `git -C <path>`, so the target is in the command rather
   than in shell state.
2. **Before writing "nothing tracks X", grep the repo that would track it.** I
   asserted an absence from a path that does not exist, and built a PR narrative
   on the empty result.
