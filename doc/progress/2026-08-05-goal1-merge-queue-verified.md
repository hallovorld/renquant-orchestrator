# GOAL-1: the 18-PR blocked queue merges clean and green — verified, not assumed

STATUS:   delivered (docs-only verification; unblocks nothing by itself — merge still needs Codex).
WHAT:     merges all 18 open PRs onto `origin/main` in ascending number order and measures the
          result: 18/18 merge with 0 conflicts, full suite 6029 passed / 2 skipped / 0 failed
          (vs. main alone today: 5910 passed, 1 failed), and every live-tree probe added across
          the queue produces the same exit code post-merge as it did on its own branch.
WHY/DIR:  GOAL-1 (shadow reliability gates) — the merge pipeline stalled ~5h with 0 reviews; this
          guarantees that when review resumes, the 18-PR stack lands clean and main goes green
          instead of red, rather than leaving that unverified.
EVIDENCE: local merge of all 18 PRs onto `origin/main`: 18/18 merged, 0 conflicts, 55 commits,
          `pytest` 6029 passed/2 skipped/0 failed on the merged stack vs. 5910 passed/1 failed on
          bare main (#849 clears the standing red from a transient live-job-state test); #852 and
          #858 (same-file touch) verified beyond textual merge — module imports and all 3 launchd
          checks present. `[VERIFIED — this session, local 18-PR merge + full pytest run this
          session]`
NEXT:     nothing here unblocks the queue — that needs Codex review. This only guarantees a clean
          landing when review resumes; the verification is against `origin/main` as of this run
          and is invalidated by any merge from another session in the meantime.

**Date:** 2026-08-05
**Lane:** GOAL-1 (shadow reliability gates)

## Why this instead of a 19th probe

The merge pipeline stopped at **2026-08-05T20:23Z** (#840). As of 01:19Z that is
**~4h56m with zero merges and zero codex reviews**, and 18 PRs are queued. The
marginal value of another probe that cannot land is low; the marginal value of
knowing the queue is *safe to land* is high, because the failure mode when review
resumes is a cascade of conflicts and a red main.

GitHub reports every PR `MERGEABLE`, but that is each branch against **today's
main** — it says nothing about the branches against **each other**. Two of them
(#852, #858) modify the same file, `ops/run_surface_drift_check.py`.

## Measured `[VERIFIED — this session]`

Merging all 18 open PRs onto `origin/main` in ascending number order:

| | |
|---|---:|
| PRs merged | **18 / 18** |
| conflicts | **0** |
| commits landed | 55 |
| full suite on the merged stack | **6029 passed, 2 skipped, 0 failed** |

For comparison, `origin/main` alone today: 5910 passed, **1 failed**.

**#849 clears the standing red.** `test_the_LIVE_2026_08_04_session_refutes_the_stdout_reading`
has failed on main all session (orch#855 — a test pinning a transient live job
state). It is fixed in #849, and the merged stack is green because of it.

#852 and #858 auto-merge cleanly: they touch different regions of the drift
scan. Verified beyond the textual merge — the merged module imports and all
three launchd checks are present.

Every probe added across the queue still runs against the live tree after the
merge:

```
run_surface_drift_check.py                     exit=1
kernel_surface_census.py                       exit=0
freshness_axis_agreement_probe.py              exit=1
wf_gate_discrimination_probe.py                exit=1
shadow_lane_control_probe.py                   exit=1
shadow_leg_independence_probe.py               exit=1
momentum_dividend_coverage_probe.py            exit=1
```

Six exit 1 because each is reporting its live finding; `kernel_surface_census`
exits 0 because no launchd surface is undetermined. These match the exit codes
each probe produced when run individually on its own branch — the merge changed
no verdict.

## Two measurement errors I made and caught inside this one check

Both are recorded because both would have produced a confident wrong number.

**1. zsh does not word-split unquoted expansions — second time this session.**
`for n in $PRS` passed the entire newline-joined list as a *single* PR number.
The loop merged **nothing**, and the suite I then ran was bare `origin/main` —
which duly showed `1 failed` and would have been reported as *"the merged stack
is red"*. The first instance was `--range $DATES` on the fleet probe (orch#856),
where the probe's own refusal caught it. Here nothing refused; only the
implausible output did.

**2. `$(basename …)` resets `$?` before `printf` reads it.** My first probe
smoke-test printed `exit=0` for all seven — I was reading *basename's* exit
status, not python's. The give-away was that probes I had watched exit 1 minutes
earlier were suddenly clean. Re-measured with `rc=$?` captured on its own line.

## What this does NOT establish

- **Not that the PRs are correct** — only that they combine without conflict and
  the suite is green. Every one still needs the review it is waiting for.
- **Not a merge order recommendation.** Ascending number order was verified;
  other orders were not, and a different order could conflict where this one did
  not.
- The verification is against `origin/main` **as of this run**. Any merge from
  another session invalidates it.

## Next

Nothing here unblocks the queue — that needs codex. This only guarantees that
when it resumes, the stack lands clean and main goes green rather than red.
