# daily104 and intraday104 were never stale; the scan read the wrong file   (PR pending)

STATUS:    delivered
WHAT:      Declares `evidence_glob` for the two production jobs whose liveness readings
           were false, and adds tests that the globs stay dated-file-scoped and
           job-unique.
WHY/DIR:   GOAL-1 / GOAL-5. `ops/launchd_liveness_scan.py` (#627) measures
           `StandardOutPath`, which for a wrapper that redirects into its own dated file
           is a **proxy** that never updates. #630 fixed three rq105 jobs this way; these
           two are the ones whose false reading matters most.
EVIDENCE:  §1.
NEXT:      §3 — 30 more jobs are still measured by proxy, and assigning their globs is
           **not** a mechanical job. Evidence below.

## §1 EVIDENCE

| job | before (StandardOutPath) | after (evidence_glob) |
|---|---|---|
| `com.renquant.daily104` | NO_EVIDENCE_STALE, **9 missed**, last write 2026-07-16 | **EVIDENCE_FRESH, 0 missed**, last write **2026-07-29 14:48** |
| `com.renquant.intraday104` | NO_EVIDENCE_STALE, **2394 missed**, last write 2026-04-22 | **EVIDENCE_FRESH, 0 missed**, last write **2026-07-30 08:48** |

Scan totals move from `EVIDENCE_FRESH 16 / STALE 22` to **`18 / 20`**, and
`measured_by_proxy` from 37 to **35 of 40**
`[VERIFIED — ops/launchd_liveness_scan.py --json, before and after]`.

**`intraday104` produced a dated log at 08:48 today** while the scan reported it 2394
firings behind. It is the 盘中 line and it is running.

Both log directories were verified to be used by **that job alone** before the glob was
added , so neither glob can pick up another job's evidence.

## §2 Why the globs match dated files, not the directory

A directory-wide glob would also match `launchd_stdout.log` — the very proxy being
replaced — and, since it is the newest file whenever the wrapper writes a line, would
silently restore the wrong reading. The pattern is `20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].log`
and a test pins that.

## §3 The remaining 30 are NOT mechanically assignable

Measured: **32 of the 37 jobs without a glob have dated files beside their stdout**
`[VERIFIED — dirname sweep over all manifested plists]`. So the proxy problem is close to
universal and most "stale" verdicts from #627 are **not trustworthy**.

But the assignment cannot be automated, and here is the counterexample:
`pit-c1-features`, `pit-estimate-snapshot` and `pit-liveness` all report the **same**
newest dated file, `c1_features_2026-07-29.log` — they share a log directory. A
directory-derived glob would hand one job's evidence to two others, which is the
wrong-object defect this whole line is about, one level up.

So each remaining job needs a per-job filename pattern established from what that job
actually writes. `test_no_two_jobs_share_an_evidence_glob` guards the invariant while
that happens.

## §4 What this does NOT claim

That the 20 still-stale jobs are healthy. It claims only that a reading taken from
`StandardOutPath` is not evidence about a job that redirects, and that two specific
readings were false. The rest remain undetermined until their real surface is named.

## §5 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree |  |
| this branch |  |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §6 Live-surface impact

None. `program_args` and `program_args_sha256` are untouched, so no manifest drift. The
scan is read-only and still not wired into any scheduled job.
