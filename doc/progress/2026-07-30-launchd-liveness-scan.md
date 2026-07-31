# 24 of 40 jobs have no evidence of running — and nothing records which SHOULD   (PR pending)

STATUS:    delivered
WHAT:      Adds `ops/launchd_liveness_scan.py`: for every job in the reviewed launchd
           manifest, how many of its **own scheduled firings** have elapsed since its
           log was last written. Read-only. Reproduces #621's four dead rq105 jobs as a
           positive control and finds twenty more.
WHY/DIR:   GOAL-5. #621's four rq105 jobs exited 0, 0, 0 and 1 — so the existing
           exit-code sentinel could not see them, because a job that stops firing
           produces no nonzero exit at all. Exit codes are the wrong instrument for
           silence.
EVIDENCE:  §1.
NEXT:      §2 — the actionable finding is NOT "24 jobs are broken". It is that the
           manifest has no per-job notion of *expected to be running*, so no scan can
           separate a deliberately retired job from a dead one. That is why 28 days of
           rq105 silence sat unnoticed.

## §1 EVIDENCE

`[VERIFIED — python3 ops/launchd_liveness_scan.py, 40 manifested jobs, 2026-07-30]`:

| class | count |
|---|---|
| `EVIDENCE_FRESH` | **14** |
| `NO_EVIDENCE_STALE` | **24** |
| `UNJUDGEABLE_NO_SCHEDULE` (KeepAlive-style, cadence undefined) | 2 |

**Positive control passes:** all four rq105 jobs #621 measured by hand come back
`NO_EVIDENCE_STALE` with 17–19 missed firings, matching #621's count. A tool that could
not reproduce a known finding would not be evidence about the unknown ones.

The worst of the twenty new ones:

| job | missed firings | last log write | size | decoded exit |
|---|---:|---|---:|---:|
| `intraday104` | **2389** | 2026-04-22 | 0 B | 0 |
| `daily103` | 77 | 2026-04-13 | 0 B | n/a |
| `open103` | 76 | 2026-04-15 | 0 B | n/a |
| `preclose103` | 75 | 2026-04-15 | 0 B | n/a |
| `monthly-calibrator-refresh` | 59 | 2026-06-01 | 0 B | 0 |
| `conditional-retrain104` | 56 | 2026-05-12 | 0 B | **1** |
| `retrain-alpha158-linear` | 53 | 2026-05-18 | 0 B | 0 |
| `preopen-cancel-gate` | 42 | 2026-06-02 | 0 B | 0 |
| `weekly-wf-promote` | 10 | 2026-05-17 | 0 B | **1** |
| `shadow-ab-daily` | 19 | 2026-07-10 | 0 B | **3** |

`weekly-wf-promote` is worth calling out separately: it is the **WF promotion** job, and
its log has not been written since **2026-05-17**. Every claim on this programme of the
form "the weekly retrain was admitted by the gate" assumes that job runs. This scan does
not establish that it stopped — see the wording caveat below — but it does establish that
nothing in the repo could have told anyone either way.

### What the tool refuses to claim

#621 states it and the tool honours it: **0-byte stdout does not by itself prove a job
did not run.** A job can run and write nothing. So every class name and every message
says *no evidence*, never *did not run*, and a test asserts the wording
(`test_the_wording_never_claims_the_job_did_not_run`). The remedy for that ambiguity is a
positive liveness record — the receipt mechanism added for the rq104 sentinel — not a
stronger inference from an absence.

### Staleness is measured against each job's own cadence

Never a fixed number of days. A weekly job is not stale at three days and a weekday job
is; a fixed threshold would validate the wrong object, which is the recurring defect
class here. `expected_firings()` walks the job's own `StartCalendarInterval`, handles the
single-dict and list forms, treats a missing `Weekday` as every day, and converts
launchd's Sunday (0 **or** 7) to Python's Monday-0 weekday explicitly rather than
assuming. Tolerance is 2 missed firings, so one boundary artifact does not alarm — #621's
four had missed 17–19, so this bound is not what hid them.

## §2 THE ACTIONABLE FINDING, which is not the count

24 of 40 is not 24 broken jobs. `daily103`, `open103` and `preclose103` stopped writing
in **April** and are very plausibly the retired 103 generation — a deliberately dormant
job legitimately produces exactly this signature. **The manifest records `program_args`
and a `program_args_sha256`, and nothing about whether a job is expected to be running.**

So no scan — this one or any other — can separate *retired* from *dead*, and that is the
structural reason 28 days of rq105 silence went unnoticed: it was indistinguishable from
the dormant majority. The fix is a reviewed `expected_state` per manifest entry
(`live` / `dormant`, with a reason for dormant), after which this scan alarms only on
`live` jobs and the dormant set becomes an explicit, reviewed decision rather than an
inference from a stale log. That is a manifest schema change on a reviewed surface and
belongs in its own PR — filing it rather than smuggling it in here.

## §3 A false finding I caught before shipping it

The first run reported **2 plists as malformed XML** (`ExpatError: not well-formed`) and
I was about to report that launchd cannot load them. **`plutil -lint` says both are OK.**

Python's `plistlib` uses expat, which rejects `--` inside an XML comment; both files carry
a prose comment block with a `---` underline. Apple's parser tolerates it and launchd loads
them fine. Shipping that would have been a false finding sending someone to fix files that
are not broken — and it is the same mistake this whole tool exists to catch: **I was
reading a different object than the one that runs.** `load_plist()` now falls back to
`plutil -convert xml1`, raising only when both parsers fail, with a test for each side.

After the fix, `UNJUDGEABLE_NO_PLIST` went from 2 to **0**.

Also fixed in the same pass: launchd's `LastExitStatus` is a raw wait status, not an exit
code. The first version printed `768`, which is exit code **3**. It is now decoded, so a
reader cannot mistake the encoding for a status.

## §4 Suite

| tree | result |
|---|---|
| `origin/main` @ cb3d4cab, separate worktree | 7 failed, 4490 passed, 5 skipped, 27 warnings in 132.20s (0:02:12) |
| this branch | 7 failed, 4516 passed, 5 skipped, 27 warnings in 131.20s (0:02:11) |

`[VERIFIED — python3 -m pytest -q in both worktrees, all sibling checkouts on PYTHONPATH]`

## §5 Live-surface impact

None. The tool reads plists, stats log files and queries `launchctl list`. It writes
nothing, never invokes git, never touches a log — asserted by
`test_the_scan_does_not_modify_a_log_it_reads`. It is not wired into any scheduled job in
this PR; wiring it in requires the §2 `expected_state` field first, or it would alarm on
the dormant majority every day and be muted within a week.
