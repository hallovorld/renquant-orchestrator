# The model-freshness monitor's install precondition is now met — and it still had no plist

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5

STATUS:    one committed plist + 1 test. **Nothing installed; no job runs.**
WHAT:      `deploy/com.renquant.rq104-model-freshness.plist` — the installable artifact
           for a job that has been declared on the reviewed surface with none.
WHY/DIR:   Its own manifest entry names a bootstrap precondition. That precondition is
           now satisfied, and the only remaining gap was the plist itself.

EVIDENCE:  §4(b) block; model-specific fields filled and marked.

```
artifact:      deploy/com.renquant.rq104-model-freshness.plist (new)
prod or exp:   prod — an installable artifact for the live run surface
existing data: the manifest entry's own _install_precondition_comment (codex CR on
               orch#638) says: "program_args target the RUN checkout, which was
               measured 110 commits behind origin/main on 2026-07-30 and does NOT
               contain this wrapper. Verify `test -x <run-checkout>/ops/renquant104/
               run_model_freshness_monitor.sh` BEFORE launchctl bootstrap."
               Measured 2026-07-31: that file EXISTS in the run checkout and is
               executable. The precondition is met.
               Also measured: of 19 manifest jobs targeting the run checkout,
               exactly ONE target is still missing — com.renquant.ops-audit's
               ops/run_ops_audit.sh, which arrives with orch#650.
               [VERIFIED — this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a deployment: 07:30 is chosen so the run lands AFTER the 07:00
               run-surface drift scan and BEFORE the day's decision (~13:55) — a
               freshness BREACH is only actionable while a session remains.
scope:         "this is deploy/…plist, PROD ARTIFACT ONLY; nothing is installed, no
                job fires, no trading behaviour changes."
```

NEXT:      Install is a machine landing needing authorization. `ops-audit` still has
           no plist and cannot get one usefully until orch#650 lands its wrapper.

## 1. A false alarm I caught before reporting it

The same sweep flagged **7 jobs whose target file is "not executable"**. It is not a
finding: all seven are invoked as `[python, script.py]`, so the executable bit is
irrelevant — the interpreter is `argv[0]`.

Checking `os.access(..., X_OK)` on a script that is never exec'd directly is a check
whose subject is not what the reader assumes. Recorded because it is the same shape
that produced several near-misses this session.

## 2. What was actually missing

The monitor's wrapper is on `main`, its manifest entry is on `main` with a full
`evidence_glob` and rationale — and there was **no plist anywhere**. Installing it
would have meant authoring one on the spot, unreviewed, which defeats the point of
declaring the job first.

`orch#665` is the only other declaration this session that ships its plist alongside.

## 3. Test

`test_every_pending_install_job_ships_an_installable_plist` asserts the plist exists,
its `Label` and `ProgramArguments` **match the manifest entry**, and the schedule is
the pre-decision slot. `ops-audit` is exempted **by name**, so the exemption cannot
spread silently to a future declaration.

Mutation check: deleting the plist fails the test.

**13 passed, 1 failed** — the failure is the pre-existing
`test_committed_manifest_matches_live_surface`, retargeted separately in orch#666.

## 5. Extended after orch#650 merged: the exemption is gone

The first version of this PR exempted `com.renquant.ops-audit` **by name**, because its
wrapper `ops/run_ops_audit.sh` was still unmerged. **orch#650 has since merged**, so the
wrapper is on `main` `[VERIFIED — this session]` and the reason for the carve-out is gone.

`deploy/com.renquant.ops-audit.plist` is added and the exemption removed: the rule is now
**universal over every pending job, with no allow-list**. An exemption that outlives its
reason is exactly how a temporary carve-out becomes permanent.

**Both pending jobs now ship an installable plist**, and the test asserts, per job, that
`Label` and `ProgramArguments` match the manifest, that both launchd sinks are set, and
that `RQ_ORCH_ROOT` is present.

**Firing order is asserted, not assumed**: `ops-audit 06:30 → drift 07:00 → freshness
07:30`, so the aggregate detector verdict is on disk before the narrower jobs fire and an
operator reading at 08:00 sees them in sequence.

### Still blocked, and it is the same variable as everything else tonight

`ops/run_ops_audit.sh` is on `main` but **not in the run checkout**
`[VERIFIED — this session]`, and `program_args` targets the run checkout. Installing now
would give a job that fires daily and fails at exec — the precondition
`rq104-model-freshness`'s manifest entry spells out and which that job has since
satisfied. The run-checkout sync is an authorized machine landing.

### A duplication I created deliberately and flagged

`_PENDING_INSTALL` in this branch's test duplicates `TestManifestGeneration.PENDING_INSTALL`
introduced in orch#666. Two copies of a set that must stay in sync is the twin shape this
org keeps a registry for. The constant carries a delete-me note naming #666, so the
duplication is temporary **by construction** rather than by good intentions — the two
branches cannot both land without someone reading it.

Mutation check: deleting either pending job's plist fails the test.

## Review round 1 — a plist can be reviewed, committed, and still guaranteed to fail

Codex: this PR ships `com.renquant.ops-audit` while its own evidence says the target
wrapper is absent from the run checkout launchd would execute — *"installable in form
but guaranteed to fail after bootstrap"*.

**Verified independently rather than taken on the review's word**
`[VERIFIED — filesystem, this session]`:

| plist target | in the run checkout? |
|---|---|
| `…-run/ops/renquant104/run_model_freshness_monitor.sh` | **PRESENT**, executable |
| `…-run/ops/run_ops_audit.sh` | **ABSENT** — merged to `main` by orch#650, not synced |

So the finding is exact: one of the two plists is installable today and the other is not.

**Took the second option — the preflight — rather than scoping to model-freshness.**
Scoping would fix this instance; the preflight closes the class. `ops/plist_install_preflight.py`
refuses to declare a job installable unless, **in the run checkout launchd actually
executes**:

* the target exists;
* it is executable **when it is `argv[0]`**;
* the plist's `ProgramArguments` match the reviewed manifest entry, so the thing being
  preflighted is the thing that was reviewed.

Read-only, exit 2 when any job is refused, and it never installs anything — installation
stays an operator action.

**Two of my own errors, both caught by running it against the real machine.**

1. **I required the exec bit unconditionally**, and it refused three jobs that are
   installed and running right now (`rq104-degradation-sentinel`,
   `rq104-shadow-scorer-sentinel`, `run-surface-drift`). They run `/bin/bash <script>`,
   where the interpreter is executed and the script is an argument — mode 0644 is fine.
   **A preflight that refuses working jobs gets switched off, and then it protects
   nothing.**
2. **My run-root override mangled already-correct absolute paths** into
   `<root>/<basename>`, reporting a present file as missing. Now it re-roots only when
   the path is not already under the requested root.

**A genuine pre-existing finding, reported rather than absorbed.**
`com.renquant.shadow-ab-daily`'s committed plist and its reviewed manifest entry name
**different checkouts** — the plist runs `renquant-orchestrator/scripts/…`, the manifest
declares `RenQuant/.subrepo_runtime/repos/renquant-orchestrator/scripts/…`
`[VERIFIED — both read at origin/main]`. Not caused by this PR. It is named in
`KNOWN_PLIST_MANIFEST_DRIFT` with the measured divergence so the set cannot grow
silently, and which path is correct is a question about that job rather than about this
preflight.

**Merge conflict** with `main` resolved the same way as #664/#666: main's partition side
kept, this branch's new test kept, and the branch's own temporary `_PENDING_INSTALL`
duplicate **deleted** exactly as its comment instructed once orch#666 landed the
canonical set — two copies of a set that must stay in sync is the twin shape this org
keeps a registry for.

`[VERIFIED — this session]` 10 preflight tests pass; the drift-scan suite passes 27.

**Correcting a claim I put in the commit message.** I wrote "full suite green". It is
not: `python3 -m pytest tests/` in this worktree dies with
`INTERNALERROR SystemExit: 2` from `ops/run_bundle_schema_audit.py`, which raises on
`ModuleNotFoundError: renquant_common`. That is the isolated-worktree missing-sibling
condition, **not** this change — a detached `origin/main` worktree produces the
identical `3 skipped, 51 errors` `[VERIFIED — both runs this session]`. CI has the
siblings and is unaffected.

I wrote "green" before running it. Recording the correction rather than amending,
because the claim was already pushed and the check is what caught it.

## Round 2 — the preflight had no caller, and the plists name three different trees

**The preflight works.** Live: **4 REFUSED / 5 INSTALLABLE**, exit code **2**, including the
`ops-audit` case the review named `[本次实测 2026-08-01]`. (My first reading said exit 0 —
that was me taking `$?` after a pipe, i.e. the *tail* exit code. The rule I quote at
others, broken by me in the same round.)

**But nothing calls it.** `grep` across the repo finds only its own tests and one mention
in this document. There is no bootstrap script here to wire it into, so as shipped it is
a gate nobody consults — the deployed-but-dark shape.

### What CAN bind today, at PR time

Two tests, needing no machine landing:

1. **every committed plist targets a script this repo actually has** — otherwise it ships
   a job that can never work from any tree. All 9 pass.
2. **which checkout does a committed plist name?** Measured across `deploy/*.plist`:

| tree named | n | |
|---|---:|---|
| run checkout (`orchestrator-run/`) | **7** | correct |
| **dev checkout** (`/renquant-orchestrator/scripts/`) | **2** | `shadow-ab-daily`, `stops-liveness` |

And the **installed** `shadow-ab-daily` names a **third** location —
`RenQuant/.subrepo_runtime/repos/renquant-orchestrator/scripts/` — the pinned runtime.

> **Three candidate trees for one job, and the committed artifact names a different one
> than the machine runs.** That is #623/#675's *which copy executes* at the plist level,
> and it is why the preflight already refuses `shadow-ab-daily` for disagreeing with the
> reviewed manifest.

The second test is a **tripwire, not an allowance**: it fails if a third dev-checkout
plist appears **and** if either of these two is repaired — because that repair is a
run-surface change somebody must look at rather than absorb silently.
