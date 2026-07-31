# A test that was red on the operator's machine on every branch, for months

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5

STATUS:    one test retargeted into two, argued in §2. No production code touched.
WHAT:      `test_committed_manifest_matches_live_surface` asserted the committed
           manifest matches the live launchd surface EXACTLY. The system
           deliberately violates that, so it failed locally on every branch.
WHY/DIR:   A permanently-red test trains its reader to ignore local failures, which
           is worse than no test. `make test` is now green on this machine.

EVIDENCE:  §4(b) block; model-specific fields filled and marked.

```
artifact:      tests/test_run_surface_drift_check.py (test only)
prod or exp:   prod-adjacent — guards ops/launchd_manifest.json, the reviewed
               run surface; no production code changed
existing data: measured against origin/main, 2026-07-31:
                 manifest 42 jobs / installed on disk 40 / deploy/ plists 6
                 declared-but-uninstalled: com.renquant.ops-audit,
                                           com.renquant.rq104-model-freshness
                 unmanifested-on-disk: NONE
               The test skips off-machine (`~/Library/LaunchAgents` absent), so it
               was green in CI and red only here — the purest form of
               "tests that measure the operator's disk".
               [VERIFIED — this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a fix: keeps BOTH failure directions rather than deleting the
               test or widening it to always-pass.
scope:         "this is tests/test_run_surface_drift_check.py, TEST ONLY; no
                manifest entry, no plist, no job, no trading behaviour changes."
```

NEXT:      Neither pending job ships a plist under `deploy/` — see §3.

## 1. Why it was red

The old assertion was `check_launchd_surface() == []`: the manifest must match the
live surface exactly. But **declaring a job before installing it is deliberate** —
the manifest is the *reviewed* surface, the plist on disk is the *live* one, and
declaring first is what gives the install something to be checked against.
`com.renquant.rq104-model-freshness` has been in that state all along.

So the test asserted something the system is designed to violate, and failed on every
branch. It also skips off-machine, so **CI was green while the operator's `make test`
was red** — nobody looking at CI would ever see it.

## 2. What replaces it — both directions, argued

**Strict, no allow-list** — `test_no_unmanifested_job_runs_on_disk`: a job installed
on disk but absent from the manifest is a job running code nobody approved. That is
the "silent containment / job swap" shape, and it has **no** legitimate case.
Measured today: **none**.

**Bounded, named** — `test_declared_but_uninstalled_jobs_are_exactly_the_named_set`:
the pending set must equal an explicit constant. Declaring ahead of install stays
legal; the set cannot grow **silently** into manifest rot. Adding a declaration now
requires naming it here, which is the same discipline the ack ledger needs.

Nothing is weakened: the dangerous direction went from "asserted alongside a
permanently-failing condition" to "asserted alone, and passing".

## 3. Measured while writing this, and it is a gap

**Neither pending job ships a plist under `deploy/`.** `com.renquant.ops-audit` and
`com.renquant.rq104-model-freshness` are declared on the reviewed surface with **no
installable artifact anywhere** — installing either means authoring a plist from
scratch, unreviewed. `orch#665` is the only declaration this session that ships its
plist alongside the manifest entry.

That is a gap in those two declarations, not in this test, and it is recorded rather
than fixed here.

## 4. Mutation check

| mutation | result |
|---|---|
| drop a name from `PENDING_INSTALL` (a job silently becomes uninstalled) | **fails** |
| add a name that is actually installed (stale pending entry) | **fails** |

The set is asserted by **equality**, so both drift directions are caught.

`tests/test_run_surface_drift_check.py` → **14 passed, 0 failed** — green on this
machine for the first time tonight.
