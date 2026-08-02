# Retire com.renquant.weekly-retrain-patchtst from the reviewed launchd surface (orch#741)

STATUS: complete (the manifest half of the orch#741 RETIRE decision; deployment
is a separate operator grant, checklist below).
WHAT: `com.renquant.weekly-retrain-patchtst` removed from
`ops/launchd_manifest.json` `jobs` (43 -> 42 entries). The drift-check test
class gains a bounded `PENDING_UNINSTALL` set — the exact mirror of the
existing `PENDING_INSTALL` relaxation — naming this one job as
retired-from-the-reviewed-surface-but-still-installed, with an exact-equality
test that goes red the moment the plist is booted out, forcing the entry's
deletion. The SCHEDULED drift scan (`com.renquant.run-surface-drift` running
`ops/run_surface_drift_check.py`) does NOT read that set: from this merge
until the operator's bootout it will alarm "unmanifested com.renquant job on
disk: com.renquant.weekly-retrain-patchtst" — per the CONTAINMENT PROTOCOL
(CLAUDE.md, GOAL-5 AC3) that alarm is the DESIGNED reminder to complete the
uninstall, and it must NOT be silenced by editing the manifest back outside
review.
WHY/DIR: orch#741 (decision comment 2026-08-02, under the operator's standing
delegation of research-line decisions): RETIRE the served hf_patchtst lane.
Governance — the artifact this job exists to refresh is 625d (~22x) past the
RFC #210 28-day SLA and the job's promotion chain has NEVER completed (22/22
trigger-fired chain FAILEDs, 36 non-acting wf-promote runs; provenance
orch#731/#724). Merit — the lane's own frozen prereg evaluation (model#90,
control_ok=true) scored it PERSISTENCE-DRIVEN while both comparison arms
scored FRESH-INFORMATIVE. A weekly job whose only purpose is to refresh a
retired lane through a chain with zero historical successes is dead weight on
the reviewed surface; keeping it manifested would assert it is wanted.
PatchTST-the-architecture is explicitly preserved — any future PatchTST
enters as a fresh candidate.
EVIDENCE:
  artifact:      ops/launchd_manifest.json (entry removed; 42 jobs remain,
                 JSON parses `[VERIFIED — json.load, this session]`),
                 tests/test_run_surface_drift_check.py (PENDING_UNINSTALL +
                 3-bucket partition + exact-equality anti-rot test;
                 18/18 file-local tests green `[VERIFIED — pytest, this
                 session]`),
                 companion config PR: renquant-strategy-104#75 (shadow lane +
                 manifest narrative removal, shadow-only)
  prod or exp:   prod-adjacent but merge-inert — the manifest is the REVIEWED
                 surface, not the live one; the installed plist keeps running
                 until the granted bootout. No launchd job, config, artifact,
                 or state file is touched by this merge.
  existing data: plist still installed on the operator machine — the drift
                 check reports exactly one unmanifested job after the removal,
                 this one `[VERIFIED — drift-check test run against the live
                 ~/Library/LaunchAgents, this session]`. Sentinel ack ledger
                 `ops/renquant104/sentinel_acks.json` carries 0 references to
                 the job `[VERIFIED — grep -c "patchtst" = 0, this session]`.
                 References that REMAIN (deliberately): historical docstrings
                 in ops/renquant104/{rq104_silent_refusal_sentinel.py,
                 run_silent_refusal_sentinel.sh,
                 freshness_axis_frontier_parity.py} (measurement history);
                 the silent-refusal sentinel's `weekly-retrain-patchtst`
                 WATCHED lane and its tests (log-reading, manifest-
                 independent — named follow-up below); the committed
                 census.json snapshot in tests (frozen historical
                 measurement) `[VERIFIED — grep sweep of ops/ and tests/,
                 this session]`.
  best-known?:   yes — mirrors the repo's own reviewed precedent for
                 present/declared divergence (PENDING_INSTALL, 2026-07-31
                 retarget: bound the named state in tests, keep the scheduled
                 scan alarming). The alternative — leaving the two disk-facing
                 tests red on the operator machine until bootout — is the
                 shape that retarget explicitly rejected ("a permanently-red
                 test trains its reader to ignore local failures").
  scope:         ops/launchd_manifest.json + tests/test_run_surface_drift_check.py
                 + this doc. Full suite 5416 passed, 8 skipped
                 `[VERIFIED — make test, 2026-08-02, this branch]`.
                 Intermediate state (manifest entry removed, tests not yet
                 updated): 2 failed, 5413 passed, 8 skipped — the two
                 disk-facing drift tests firing on the now-unmanifested
                 installed plist, i.e. the alarm working as designed
                 `[VERIFIED — make test at that intermediate state, this
                 session]`.

## Deployment grant checklist — ONE operator grant batch, in order

Nothing below happens at merge time. Each item names its revert. The grant is
one batch per the landing-actions rule; the drift-scan alarm stands until (c)
completes.

(a) **Merge this PR** (renquant-orchestrator).
    Revert: `git revert` of the merge commit (restores the manifest entry and
    the strict test shape in one step).

(b) **Advance the strategy-104 pin** to a commit including
    renquant-strategy-104#75 (the shadow-lane removal). Surface:
    `subrepos.lock.json` in the umbrella repo — current pin
    `8402a6297ec07e316f8c8a19b403ae8b5af4e64d`
    `[VERIFIED — read from /Users/renhao/git/github/RenQuant/subrepos.lock.json,
    2026-08-02]` — advanced via the standard promote_pin flow, never by
    hand-editing the live tree.
    Revert: restore the pin to `8402a629...` via the same flow.

(c) **Uninstall the launchd job** (literal command):
    `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renquant.weekly-retrain-patchtst.plist && rm ~/Library/LaunchAgents/com.renquant.weekly-retrain-patchtst.plist`
    Revert: `git revert` of this PR's commit (restores the manifest entry) +
    re-create the plist from the reverted manifest's program_args
    (`/Users/renhao/git/github/RenQuant/scripts/weekly_retrain_patchtst.sh`,
    Sat 05:30 schedule) and `launchctl bootstrap gui/$(id -u)` it.

(d) **Sync the run checkout(s)** so the pinned strategy-104 config is what the
    daily run reads (merged != deployed; the daily run consumes the pinned
    local checkouts).
    Revert: re-sync to the reverted pin.

## Named follow-ups (tracked, not silently absorbed)

1. After (c), `test_retired_but_still_installed_jobs_are_exactly_the_named_set`
   goes red with `resolved=['com.renquant.weekly-retrain-patchtst']` — that is
   the designed prompt to DELETE the `PENDING_UNINSTALL` entry in a small
   follow-up PR, restoring the fully strict invariant. The relaxation cannot
   outlive the state it names.
2. The silent-refusal sentinel still WATCHES the `weekly-retrain-patchtst`
   log lane (`ops/renquant104/rq104_silent_refusal_sentinel.py`). It reads
   dated logs, not the manifest, so it is untouched here; once the job is
   uninstalled the lane will stop producing fresh logs and the lane's
   retirement (plus its tests) should ride the same follow-up PR as (1) —
   its own reviewed change, kept out of this PR to keep the reviewed-surface
   diff minimal and provably merge-inert.
