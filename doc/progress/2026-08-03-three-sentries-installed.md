# Three declared-pending sentries installed; the first finding was diagnosed and the alarm's one defect fixed

**Date:** 2026-08-03 · `renquant-orchestrator` · GOAL-5 / 104-repair directive

STATUS:    machine landing DONE (bootstraps verified, containment trail in the
           session grants log); this PR lands the reviewed-surface bookkeeping
           that the same batch requires, plus one sentinel defect fix.
WHAT:      (1) manifest: the two `_pending_install_comment` blocks become
           `_installed_comment` records; (2) drift tests: PENDING_INSTALL
           emptied (exact-equality design forces this in the same change);
           (3) the superseded silent-refusal twin plist DELETED;
           (4) sentinel: crash vs delegated-FAIL are now separate outcomes.

## 1. The installs (machine landing, 2026-08-03 ~22:58-23:07Z)

All three declared-pending jobs bootstrapped under the operator's 104/105
perfection directive, each verified with `launchctl print` after bootstrap:

| job | schedule | first hand-run |
|---|---|---|
| com.renquant.ops-audit | per plist | rc=3, 10-finding report (real worklist) |
| com.renquant.rq104-model-freshness | per plist | rc=3, freshness BREACH (primary 42d) |
| com.renquant.rq104-silent-refusal | daily 16:00 | rc=1, retrain-panel104 finding below |

The #638 precondition was verified before the freshness bootstrap (run
checkout carries the executable wrapper).

## 2. The twin-plist find (what the drift scan is FOR)

The silent-refusal install first used `ops/renquant104/…-sentinel.plist`
(2026-07-29 artifact: python direct invocation, weekly Sun 08:11, label
`…-sentinel`) — and the scheduled drift scan immediately alarmed
ProgramArguments CHANGED against the manifest. Root: the repo carried TWO
committed plists for this job; the 2026-07-31 REVIEWED surface
(`deploy/com.renquant.rq104-silent-refusal.plist`: bash wrapper, daily 16:00
deliberately after the 15:00 degradation sentinel, label without suffix) had
superseded the 07-29 artifact, which nobody deleted. Resolution: the reviewed
surface won — machine re-bootstrapped on the deploy/ plist (verified loaded),
the twin deleted here, and the drift suite is 18/18 green against the real
machine `[VERIFIED — this session]`. My first move had been to rename the
MANIFEST key toward the stale artifact; the 07-31 progress doc corrected me.

## 3. First scheduled finding, diagnosed (read-only agent, full report on #541)

The sentinel's day-one finding said retrain-panel104 "has not acted on 11
non-acting runs … 11 of them CRASHED". Diagnosis: **zero of the 6 quoted
Sunday failures is a crash** — the lane's `failure_re` matches the wrapper's
honest `delegated weekly_wf_promote FAIL` echo and the message glossed every
`failed` as CRASHED. The 6 split into a resolved config-parity era
(06-28/07-05) and the ACTIVE chronic WF-gate REJECT (07-12→08-02: benchmark
lag ΔSharpe −0.39..−0.55 + a placebo ceiling ~+0.023..0.030 sitting under the
~+0.04 embargo-leakage floor). The #541 ack correctly covers the active era;
the sentinel reads no acks BY DESIGN. The 08-09 run will fail identically
unless the gate-v3/freshness decision is made (GOAL-4 territory, tracked).

## 4. The one new defect, fixed here

`crash_re` (died before deciding) is now separate from `failure_re` (the
job's own FAIL vocabulary); `crashed` and `failed` are distinct outcomes,
both still count toward the streak, and the alarm reports
"N of them CRASHED" / "N of them reported FAIL (the job's own verdict, not a
crash)" accurately. Regression test pins the exact defect shape (2 delegated
FAILs + 1 crash → never "3 CRASHED").

EVIDENCE:

```
artifact:      ops/launchd_manifest.json, deploy/ (unchanged; twin deleted
               from ops/renquant104/), tests/test_run_surface_drift_check.py,
               ops/renquant104/rq104_silent_refusal_sentinel.py,
               tests/test_rq104_silent_refusal_sentinel.py
prod or exp:   prod run-surface bookkeeping + a sentinel's alarm wording
existing data: drift tests 18/18 against the live machine; sentinel tests
               green; full suite 5483 passed / 2 skipped  [VERIFIED]
scope:         "no job behaviour changes except the alarm's wording; the
                streak semantics (refused+failed+crashed all count) are
                unchanged."
```

## Revert

Manifest/tests: git revert. Machine: `launchctl bootout
gui/502/com.renquant.rq104-silent-refusal && rm ~/Library/LaunchAgents/<that
plist>` (and the other two labels likewise) restores the pre-install state;
the PENDING_INSTALL entries would then need re-adding in the same change —
the exact-equality tests force it.
