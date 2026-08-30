# Manifest entries for the earnings-calendar + daily earnings-surprise jobs   (PR #TBD)

STATUS:    delivered (reviewed-surface half of the 2026-08-30 earnings
           freshness fix; the jobs themselves live in umbrella PR
           RenQuant#TBD — cross-linked below. NOTHING is installed by
           this PR; installation is the operator landing batch).

WHAT:      ops/launchd_manifest.json += two entries under "jobs" (the
           surface run_surface_drift_check.py and kernel_surface_census.py
           read), digests computed by the checker's own recipe
           (sha256(json.dumps(program_args))):
           * com.renquant.earnings-calendar-refresh — Mon-Fri 05:40 PT +
             Sat 04:40 PT, /Users/renhao/git/github/RenQuant/scripts/
             refresh_earnings_calendar.sh
           * com.renquant.daily-earnings-surprise — Mon-Fri 06:00 PT,
             /Users/renhao/git/github/RenQuant/scripts/
             daily_earnings_surprise_refresh.sh

WHY/DIR:   2026-08-30 data audit (umbrella PR RenQuant#TBD carries the
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
           umbrella PR.

NEXT:      operator landing batch: merge umbrella PR RenQuant#TBD, pull
           the live tree, cp the two plists from scripts/launchd/ into
           ~/Library/LaunchAgents/ and launchctl load them (literal
           commands in the umbrella progress doc). Until then the daily
           run-surface drift scan alarms "manifested job missing from
           disk" for these two labels — the DESIGNED reminder to finish
           the batch. Revert: git revert this PR (and bootout/rm if
           already installed).
