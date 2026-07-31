# AC5's sentinel has been merged for weeks and scheduled never

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 AC5

STATUS:    declaration only — manifest entry + committed plist + 2 tests.
           **The plist is NOT installed; that is a separate machine landing.**
WHAT:      Declares `com.renquant.rq104-silent-refusal` on the reviewed run surface.
WHY/DIR:   The programme anchor reads "AC5 = #619 已合". Accurate about the merge,
           silent about the deployment — and the gap cost four weeks of a dead
           retrain lane that this sentinel found on its first manual run.

EVIDENCE:  §4(b) block; model-specific fields filled and marked.

```
artifact:      ops/launchd_manifest.json (+1 entry),
               deploy/com.renquant.rq104-silent-refusal.plist (new)
prod or exp:   prod — declares a job on the live run surface
existing data: ops/renquant104/rq104_silent_refusal_sentinel.py is on main and was
               absent from ops/launchd_manifest.json and from `launchctl list`.
               Run by hand for the first time 2026-07-31, it immediately reported:
               "job 'weekly-retrain-patchtst' has not acted on 4 non-acting runs …
               (2026-07-25:refused, 07-18:failed, 07-11:failed, 07-03:failed;
               3 of them CRASHED)" — a four-week-dead lane, one reproducible cause.
               6 of 6 ops-audit detectors are on main; 0 were manifested.
               [VERIFIED — this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a deployment: 16:00 is chosen so the run lands AFTER the 15:00
               degradation sentinel, i.e. a day's refusals are already classified
               and the two alarms never interleave.
scope:         "this is ops/launchd_manifest.json + a new deploy/ plist, PROD
                DECLARATION ONLY; nothing is installed, no job runs, no trading
                behaviour changes."
```

NEXT:      Install the plist (machine landing, needs authorization). Until then the
           drift scan reports the job missing from disk — the intended reminder.

## 1. Why declare before installing

Because the reverse order is how a job ends up running unreviewed. The manifest is
the **reviewed** surface; the plist on disk is the **live** one. Declaring first
means the install has something to be checked against, and `run_surface_drift_check`
will say so loudly if the two ever disagree.

## 2. The consequence, stated rather than discovered

Merging this makes `TestManifestGeneration::test_committed_manifest_matches_live_surface`
report **2** stale entries instead of **1**:

```
origin/main : ['… com.renquant.rq104-model-freshness missing from disk']
this branch : ['… com.renquant.rq104-model-freshness missing from disk',
               '… com.renquant.rq104-silent-refusal  missing from disk']
```

`[VERIFIED — both runs this session]`

**That test is already red on `origin/main`, and `rq104-model-freshness` is already a
manifested-but-uninstalled job.** So this is a **second instance of an existing,
tolerated pattern** — a tracked reminder that a declared job is not yet live — not a
new alarm shape. Per CLAUDE.md's CONTAINMENT PROTOCOL, that alarm *is* the designed
mechanism; the wrong move would be silencing it by editing the manifest outside review.

## 3. Tests

- the manifest entry exists, points at the sentinel, and its `program_args_sha256`
  is self-consistent;
- **the committed plist and the manifest entry agree** — a plist that disagrees with
  the manifest is precisely the drift this repo exists to catch, and it must not ship
  disagreeing with itself on day one.

14 passed, 1 failed — the failure is the pre-existing manifest-vs-live-surface test
described in §2.

## 5. Correction made before review: the first plist built in the defect

The first version of this PR pointed `StandardOutPath` at
`logs/rq104/launchd_silent_refusal.out` — an **append-only file with no date in its
name** — and shipped no wrapper.

That is the exact anti-pattern measured on the drift scan the same night (**orch#663**):
**0 of 18 lines** in its `.out` began with a date, so no line belonged to any run, and a
**resolved** containment alarm was indistinguishable from a live one. Shipping a *new*
job with that shape would have been building the defect in on day one, in the same
session I filed the issue against it.

Corrected here:

- `ops/renquant104/run_silent_refusal_sentinel.sh` writes
  `logs/rq104/silent_refusal_<YYYY-MM-DD>.log`;
- the manifest entry gains an `evidence_glob` over that pattern, joining the 7 of 42
  jobs whose evidence — not just exit code — is checkable;
- the launchd `.out`/`.err` remain, but only as sinks for a run that never reached its
  own evidence.

**Evidence ordering is lifted deliberately from `run_model_freshness_monitor.sh`**, where
it was a codex BLOCKER on orch#638: prerequisites and an import probe run **before** the
dated file is created, so the file's **existence** is proof the sentinel ran. Verified
`[VERIFIED — this session]`:

```
RQ_ROOT=/nonexistent       -> rc=4, no evidence file created
RQ_ORCH_ROOT=/nonexistent  -> rc=4, no evidence file created
evidence files before/after: 0 / 0
```

`tee` is last in the pipe, so `PIPESTATUS[0]` is the only faithful read of the
sentinel's own status — the exit code is the payload and must not be swallowed.
