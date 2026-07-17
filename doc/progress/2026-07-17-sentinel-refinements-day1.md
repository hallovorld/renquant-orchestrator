# Sentinel day-1 refinements: top-up-aware buys + umbrella branch check

STATUS: delivered
WHAT: two refinements from the sentinels' first live day:
1. Degradation sentinel counts the trades table as buy-activity ground
   truth (pipeline_runs.n_buys excludes top-up orders; n_candidates is
   zeroed post-veto) — removes the 07-17 first-firing false alarm class;
   fail-safe when the trades table is absent.
2. Drift scan alarms when the umbrella live tree is not on `main` — the
   07-17 stray-branch incident silently disabled the 13:55 daily until
   the wrapper guard fired mid-day; the 07:00 scan now catches it 7 hours
   earlier. The alarm text warns against reset --hard (uncommitted
   operational fixes may be present).
WHY/DIR: GOAL-5 continuous hardening — every alarm/incident on day 1
feeds back into the detection surface same-day.
EVIDENCE: 20+13 module tests incl. the top-up regression fixture; live
umbrella check CLEAN post-restore; full suite 4008 passed.
NEXT: none (monthly-meta-label + retrain-panel104 investigations tracked
separately).
