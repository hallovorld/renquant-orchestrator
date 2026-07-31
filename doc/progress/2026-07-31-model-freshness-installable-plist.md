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
