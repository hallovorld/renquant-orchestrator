# Which copy of the code runs was decided by `ls`, not by review

STATUS:   delivered. One new shared resolver, six wrappers rewired, two python
          resolvers unified, one scanner blind spot closed. No live path
          touched; behaviour on this machine is unchanged (see BEHAVIOUR).

WHAT:     Six scheduled rq105 wrappers each carried their own copy of

              RQ_COMMON_SRC=".../renquant-common-run/src"
              [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC=".../renquant-common/src"

          and two python entrypoints carried the equivalent
          `for name in ("renquant-common-run", "renquant-common")` loop. All
          eight now go through ONE named checkout, declared in
          `ops/renquant105/rq105_common_src.sh` (shell) and
          `liveness_common.COMMON_CHECKOUT` (python), with **no fallback**.

WHY/DIR:  orch#1016. The drift scanner's own phrasing is the finding: *which
          copy executes is decided by filesystem state, not by review*.
          `renquant-common-run` does not exist on this machine, so the `else`
          branch won on every job and all six imported the DEV working tree —
          edited freely, on whatever branch someone last used, governed by no
          pin. Worse, it flips SILENTLY: the day anyone creates that directory,
          six scheduled jobs change which code they run, with no commit, no
          review and no alarm.

BEHAVIOUR: unchanged today, deliberately. `RQ105_COMMON_CHECKOUT` is set to
          `renquant-common` — a RECORD of what actually runs, not an
          endorsement of it. Pointing scheduled jobs at a dev tree is its own
          problem and is NOT fixed here. What is fixed is that the answer now
          lives in a reviewed file: changing it takes a commit, and creating a
          sibling directory no longer changes anything.

EVIDENCE:
  artifact:      ops/renquant105/rq105_common_src.sh (new), six run_*.sh,
                 ops/liveness_common.py, ops/renquant105/rq105_liveness_check.py,
                 ops/run_surface_drift_check.py, and three test files.
  prod or exp:   neither. Nothing is deployed by this change; the wrappers in
                 the -run checkout are untouched until an operator-gated sync.
  existing data: the fallback fires today — `renquant-common-run` is absent
                 [VERIFIED 2026-08-24]. And the dev checkout is not merely on
                 PYTHONPATH: the venv's own `renquant_common` resolves to
                 `/Users/renhao/git/github/renquant-common/src/renquant_common/
                 __init__.py`, i.e. the install IS that working tree [VERIFIED].
                 That is also why failing closed is safe here — the named
                 checkout exists in production, so the new refusal path cannot
                 fire on the live box today.
  best-known?:   yes, and the decisive evidence is a differential run of the
                 SAME patched scanner against both trees:
                   unfixed tree (the -run checkout): 5 FALLBACK problems
                   fixed tree (this branch):         0, with 28 infos
                 Same detector, opposite verdicts — so what changed is the
                 defect, not the detector.
  scope:         path resolution only. No job's logic, schedule, or output
                 changes. The -run checkout is not modified.

VERIFICATION:
  Mutation-verified: 7 of 9 new tests fail against the unfixed tree; 9 pass
  with the fix [VERIFIED 2026-08-24].
  Affected scope (drift / rq105 / liveness / surface / wrapper test files):
  549 passed, 2 skipped, 0 failed. Baseline on pristine ops was 541 passed +
  my 7 new failures; 541 + 8 net-new = 549.

  THE BLIND SPOT, which is the real risk in this change. Consolidating the
  idiom into a sourced helper is also the perfect place to HIDE it: the scanner
  reads the wrapper, the wrapper is clean, the scan goes green, and the
  fallback runs anyway — a check that certifies the thing it stopped looking
  at. So `run_surface_drift_check` now follows `source`/`.` targets one level,
  and `test_a_fallback_hidden_in_a_sourced_file_is_still_found` plants a
  fallback in a sourced file and requires the scan to catch it.

  Two existing tests were updated rather than deleted:
   * `test_five_SCHEDULED_wrappers_currently_use_a_fallback` asserted the defect
     (`len(sites) == 5`). It is FLIPPED to assert remediation, and paired with a
     new `test_a_planted_fallback_is_still_detected` control — green must mean
     "no fallback", never "the scan stopped looking".
   * `test_clean_full_session_completion_is_silent` broke because its fake tree
     has no sibling checkout, and the resolver now refuses instead of assigning
     a path it never checked (the old code assigned the fallback WITHOUT testing
     that it existed). The fixture provides the checkout; the stricter contract
     is the point.

  One self-inflicted defect worth recording: my first `_SOURCE_RE` used
  `[^"]+` for the target and matched NOTHING, because `. "$(dirname "$0")/x.sh"`
  contains nested double quotes. `_FALLBACK_RE`, twenty lines below, carries a
  comment documenting that exact mistake being made once already in this file.
  I made it again. `test_an_unreadable_source_target_is_recorded_not_swallowed`
  is what caught it.

NEXT:     Not attempted here, and both are decisions rather than code:
          1. Should scheduled jobs import a dev checkout at all? Migrating to a
             pinned `renquant-common-run` is now a one-line change to
             `RQ105_COMMON_CHECKOUT` — made deliberately, with the checkout
             created first, instead of by whoever happens to run `git clone`.
          2. The -run checkout still has the old wrappers until an
             operator-gated sync; until then the drift scan keeps reporting the
             5 sites there, correctly.
