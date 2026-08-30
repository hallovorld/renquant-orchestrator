# Manifest entries for the earnings-calendar + daily earnings-surprise jobs   (PR #1102)

STATUS:    delivered (reviewed-surface half of the 2026-08-30 earnings
           freshness fix; the jobs themselves live in umbrella PR
           RenQuant#627 — cross-linked below. NOTHING is installed by
           this PR; installation is the operator landing batch).

WHAT:      ops/launchd_manifest.json += two entries under "jobs" (the
           surface run_surface_drift_check.py and kernel_surface_census.py
           read), digests computed by the checker's own recipe
           (sha256(json.dumps(program_args))); and, since the two jobs are
           declared-but-not-installed, tests/test_run_surface_drift_check.py
           names that pending state (codex r1 — see §Review r1 below):
           * com.renquant.earnings-calendar-refresh — Mon-Fri 05:40 PT +
             Sat 04:40 PT, /Users/renhao/git/github/RenQuant/scripts/
             refresh_earnings_calendar.sh
           * com.renquant.daily-earnings-surprise — Mon-Fri 06:00 PT,
             /Users/renhao/git/github/RenQuant/scripts/
             daily_earnings_surprise_refresh.sh

WHY/DIR:   2026-08-30 data audit (umbrella PR RenQuant#627 carries the
           full root cause): the earnings-calendar producer was never
           scheduled — the prod artifact froze at 2026-04-24 (last date
           2026-07-24) and the live pre/post-earnings buffer silently
           could not fire for any Aug/Sep print; PEAD/SUE surprises were
           refreshed weekly only (Sat 04:00), staying median-imputed for
           up to a week after a print. The two new jobs close both lanes;
           this PR makes them part of the REVIEWED run surface so the
           drift scan guards them like every other com.renquant.* job.
           No memory-tier item changes: ops manifest addition, same class
           as the l1-exposure-shadow legitimisation
           (doc/progress/2026-08-08-l1-shadow-job-manifest.md).

EVIDENCE:  artifact:      ops/launchd_manifest.json (42 jobs after edit)
           prod or exp:   prod run surface (reviewed manifest)
           existing data: check_launchd_surface run against the edited
                          manifest this session: exactly the two expected
                          "manifested job {label} missing from disk"
                          findings for the not-yet-installed jobs, no
                          other new finding; both digests re-verified
                          with the checker's own recipe [VERIFIED — run
                          in-session]
           best-known?:   n/a — ops change
           scope:         "two manifest entries + this record; no job is
                          loaded, no plist is installed, no other entry
                          is touched"

TESTS:     json.loads round-trip OK; per-entry digest == checker recipe
           [VERIFIED]; check_launchd_surface findings as expected (see
           EVIDENCE). The plists themselves are plutil-linted in the
           umbrella PR. After the r1 fix (branch rebased onto main at
           989ceb86 = #1100, which made this file hermetic by default):
           tests/test_run_surface_drift_check.py default env **44 passed,
           5 skipped** (was 43/5 on main; +1 = the new hermetic alarm
           test); `RENQUANT_DRIFT_DISK_TESTS=1 … -k OperatorDisk` on the
           operator's disk **5 passed** (was 1 failed / 4 passed at
           b115414e — the finding); the PENDING_INSTALL cross-importers +
           census + liveness (test_momentum_train_job_surface.py,
           test_model_freshness_job_surface.py,
           test_kernel_surface_census.py, test_launchd_liveness_scan.py)
           **92 passed**; the 17 manifest-walking test files as a set
           **485 passed, 3 skipped** [VERIFIED 2026-08-30, this worktree].

NEXT:      operator landing batch: RenQuant#627 merged 2026-08-30 19:32Z;
           pull the live tree, cp the two plists from scripts/launchd/ into
           ~/Library/LaunchAgents/ and launchctl load them (literal
           commands in the umbrella progress doc). Until then the daily
           run-surface drift scan alarms "manifested job missing from
           disk" for these two labels — the DESIGNED reminder to finish
           the batch. When the install lands, the opt-in exact-equality
           test goes red with resolved=[the two labels]: delete
           EARNINGS_JOBS_PENDING_INSTALL_2026_08_30 (and its hermetic
           alarm test + the PENDING_INSTALL reference) in a follow-up, as
           #1100 did for the previous relaxations. Revert: git revert this
           PR (and bootout/rm if already installed).

## Review r1 (codex, 2026-08-30 19:31Z) — fixed

Finding (MED): the two new declared-but-not-installed jobs made the
repo's own exact-equality drift test red on the operator machine —
`test_declared_but_uninstalled_jobs_are_exactly_the_named_set` failed with
`unexpected=['com.renquant.daily-earnings-surprise',
'com.renquant.earnings-calendar-refresh']`. Reproduced at b115414e rebased
onto main 989ceb86 with `RENQUANT_DRIFT_DISK_TESTS=1` (after #1100 the
disk-reading partition is the opt-in `TestOperatorDiskSurface` class; the
default suite was already green, 43 passed / 5 skipped) [VERIFIED].

Fix (tests/test_run_surface_drift_check.py only; manifest untouched):
- `EARNINGS_JOBS_PENDING_INSTALL_2026_08_30` — one module-level tuple naming
  the two labels and the pending state (why, where the plists live, what
  deletes it).
- `TestOperatorDiskSurface.PENDING_INSTALL = set(...)` of that tuple, so the
  bounded relaxation admits exactly these two findings and nothing else;
  the exact-equality test goes red with `resolved=[...]` the moment the
  operator installs them (the forcing function #1100 describes).
- New hermetic test `test_the_two_earnings_jobs_absent_from_disk_alarm_as_missing`
  (runs on CI, no disk): the committed manifest against fixture plists with
  the two removed → exactly the two `manifested job … missing from disk`
  lines and nothing else — pins the EVIDENCE claim above on any machine.
- `test_installed_equals_manifest_is_clean` docstring: "all 40 jobs" →
  "every manifested job" (this PR makes 42; a count in a docstring goes
  stale on every addition).
Not done: nothing skipped from the finding.
