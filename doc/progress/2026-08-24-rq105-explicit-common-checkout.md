# The pinned copy was already on PYTHONPATH — and losing to an unpinned one

STATUS:   delivered. Shared pin-verifying resolver + six wrappers rewired + two
          python resolvers unified + one scanner blind spot closed. No live path
          touched; the -run checkout is not modified.

WHAT:     Six scheduled rq105 wrappers each carried their own copy of

              RQ_COMMON_SRC=".../renquant-common-run/src"
              [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC=".../renquant-common/src"

          and two python entrypoints carried the equivalent two-name loop. All
          eight now resolve `<RQ_ROOT>/.subrepo_runtime/repos/renquant-common/src`
          — the copy the umbrella PINS — and refuse unless its HEAD matches
          `subrepos.lock.json`'s recorded commit.

WHY/DIR:  orch#1016. The drift scanner's phrasing is the finding: *which copy
          executes is decided by filesystem state, not by review*.
          `renquant-common-run` is absent here, so every job imported the
          mutable dev working tree — and the venv's own `renquant_common`
          resolves into that same tree, so it is not a supplement, it IS the
          install.

          MY FIRST ATTEMPT WAS WRONG AND CODEX WAS RIGHT TO BLOCK IT. It
          replaced the fallback with one NAMED sibling checkout, which fixes the
          wrong half:
          * a directory NAME is not a revision. Checking that `src/` exists says
            nothing about what is in it;
          * `run_session_scheduler.sh` ALREADY had `$SUBREPO/renquant-common/src`
            — the pinned runtime — on PYTHONPATH, positioned AFTER the mutable
            sibling. The pin was present and losing. Consolidating on the sibling
            would have entrenched exactly that;
          * `RQ105_COMMON_CHECKOUT` was env-overridable, so an unreviewed
            process environment could still choose the code while the scan
            reported the choice as reviewed — a fail-open I introduced while
            closing one.

EVIDENCE:
  artifact:      ops/renquant105/rq105_pinned_common.py (new, the single
                 implementation), ops/renquant105/rq105_common_src.sh, six
                 run_*.sh, ops/liveness_common.py,
                 ops/renquant105/rq105_liveness_check.py,
                 ops/run_surface_drift_check.py, three test files.
  prod or exp:   neither. Nothing is deployed; the -run checkout keeps the old
                 wrappers until an operator-gated sync.
  existing data: the pin exists and currently MATCHES [VERIFIED 2026-08-24]:
                   subrepos.lock.json subrepos[renquant-common].commit
                     = ef7726dd6c90dea5c28669823c6ed7475d752d11
                   .subrepo_runtime/repos/renquant-common HEAD
                     = ef7726dd6c90dea5c28669823c6ed7475d752d11
                 and running the new resolver against the live umbrella prints
                 `.../.subrepo_runtime/repos/renquant-common/src`, pin-verified.
                 So this change is behaviour-CHANGING in the right direction and
                 cannot fail closed on the live box today.
  best-known?:   yes, and the decisive evidence is a differential run of the
                 SAME patched scanner against both trees:
                   fixed tree (this branch):        0 fallback, 28 infos
                   unfixed tree (-run checkout):    5 fallback, 23 infos
                 Same detector, opposite verdicts — what changed is the defect,
                 not the detector.
  scope:         path resolution only. No job's logic, schedule or output
                 changes. ONE implementation serves shell and python, because
                 two implementations of a pin check are two chances to disagree
                 about what is pinned.

VERIFICATION:
  18 tests, covering what codex asked for by name:
    wrong HEAD vs pin            -> refused
    lock entry missing           -> refused
    pin present but empty commit -> refused ("a pin that names no revision")
    runtime checkout missing     -> refused, WITH a tempting sibling present
    unrelated siblings present   -> pinned copy still wins (precedence)
    ambient env redirect         -> RQ105_COMMON_CHECKOUT / RQ_COMMON_SRC /
                                    PYTHONPATH set to an "evil" tree, ignored,
                                    plus a source-level assertion that no such
                                    override exists in either language
    scheduler PYTHONPATH         -> no literal renquant-common entry remains
  Affected scope (drift / rq105 / liveness / surface / wrapper): 558 passed,
  2 skipped, 0 failed [VERIFIED 2026-08-24].

  CI RED, AND WHY. The previous push failed both `test` jobs with
  `FileNotFoundError: /bin/zsh` — I hardcoded the operator's shell into
  subprocess tests, and the ubuntu runner has no zsh. Fixed at the source rather
  than by skipping: the resolver had used `${0:A:h}` (zsh-only, EMPTY under
  bash), so the wrappers now pass `RQ105_OPS_DIR` explicitly and the tests pick
  `zsh or bash or sh`. A skipped shell test would have left the resolver
  unexecuted on every CI run — a green check covering nothing, which is the
  failure mode this repo keeps relearning. There is a test asserting the
  resolver loads under `/bin/sh`.

  THE BLIND SPOT this change creates. Consolidating the idiom into a sourced
  helper is also the perfect place to HIDE it: the scanner reads the wrapper,
  the wrapper is clean, the scan goes green, the fallback runs anyway. So
  `run_surface_drift_check` now follows `source`/`.` targets one level, and a
  test plants a fallback in a sourced file and requires the scan to catch it.
  My first `_SOURCE_RE` used `[^"]+` and matched NOTHING, because
  `. "$(dirname "$0")/x.sh"` contains nested double quotes — a mistake
  `_FALLBACK_RE` twenty lines below already documents being made once in this
  file. I made it again;
  `test_an_unreadable_source_target_is_recorded_not_swallowed` caught it.

  Two existing tests were updated, not deleted:
   * `test_five_SCHEDULED_wrappers_currently_use_a_fallback` asserted the defect.
     FLIPPED to assert remediation, paired with a new
     `test_a_planted_fallback_is_still_detected` control — green must mean "no
     fallback", never "the scan stopped looking".
   * `test_rq105_quote_logger_failloud`'s fake tree now builds a real (tiny) git
     checkout plus a matching lock, because the wrapper verifies a pin now. A
     fixture that only made a directory would test a weaker contract than ships.

NEXT:     Not attempted here: the -run checkout still carries the old wrappers
          until an operator-gated sync, so the drift scan keeps reporting the 5
          sites there — correctly.
