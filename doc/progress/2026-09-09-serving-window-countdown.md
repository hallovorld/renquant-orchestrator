# Count down the serving exception instead of discovering it on expiry day   (PR #1120)

STATUS:    delivered — the recurrence guard for the 2026-09-07 cliff.
WHAT:      New observe-only `serving_window_monitor.py`: reads the SERVED
           artifact only and answers one question — *if the serving exception
           closes on its stamped date, will the book still be able to buy the
           next day?* Verdicts: `ok` (no exception in force, or the artifact
           carries eligible regimes of its own so the close is harmless, or
           the close is further out than the lead), `warn` (closing within
           `--lead-days`, default 7), `closed` (already past), `unknown`
           (unreadable artifact, unparseable expiry, or an unreadable regime
           stamp — reported, never guessed). Exit 0/1/2/3; `--notify` posts
           only on non-ok, at priority 4/5; `--as-of` and `--artifact` make it
           fully testable. The alert names the date, the days left, the
           eligible-regime count, and both exits in the operator's terms
           (promote a candidate whose WF produced round-trips, or record a new
           dated window). `ops/renquant104/run_model_freshness_monitor.sh`
           runs it as step 2b, so it fires with the existing 05:45 job and
           needs no plist change; the wrapper's own exit code stays the
           FRESHNESS monitor's, because the run-health classifier reads this
           job's status as the freshness verdict and re-pointing it would
           silently change what those codes mean — the window verdict is
           recorded in the evidence log and paged by the monitor itself.
WHY/DIR:   The A4-T1 license was granted 2026-08-31 with a stamped expiry of
           2026-09-07. It closed itself exactly as designed — and the 09-08
           session went straight to sell-only, because the licensed artifact
           has zero eligible regimes and nothing else was servable: the
           previous model is 37d old against a 28d SLA, and every candidate
           since 09-01 carries 0 eligible regimes with genuine_ic 0.0002–0.0009
           against a 0.02 floor. A self-expiring license is the right design;
           what was missing is the alarm in front of it. Nobody had scheduled
           what happens ON expiry, so the window closed into a state with no
           servable model and the first anyone knew was the daily aborting.
           Direction: G-A/G-D — a foreseeable cliff must page before it, not
           after.
EVIDENCE:  artifact:      `RenQuant/logs/daily_104/2026-09-08.log:394-400` (`✗ P-REGIME-IC … PRE-FLIGHT FAILED … rerunning sell-only`) and the 13:55 ntfy `[sell-only] DECISION | no trade (no_candidates)` [VERIFIED — read 2026-09-08]
           prod or exp:   prod ops surface — one new alert on an existing daily job; reads one JSON file, promotes nothing, writes no state, changes no window
           existing data: `tests/test_serving_window_monitor.py` 27 passed (the 09-01 six-days-out warning with its exact wording, lead boundary inclusive at 7d, the 09-08 CLOSED state, no-exception silence, an artifact that stands on its own, unreadable expiry/regime-stamp/payload all `unknown`, CLI exit codes, `--notify` only on trouble, `--quiet`, missing artifact fails closed, a verdict crash reported as `unknown`, a failed page recorded without becoming the verdict, the age bar binding when it comes first, the window binding when it does, both cliffs on one day, an unavailable age bar noted never guessed, and the bar read from the pipeline's own constant) [VERIFIED — 2026-09-09 ~01:3x PDT]; read-only run against the LIVE served artifact: as-of 2026-09-01 → `WARN days_left=6 eligible=0` naming 2026-09-07 and the sell-only consequence; as-of 2026-09-07 → `WARN days_left=0`; as-of 2026-09-08 → `CLOSED days_left=-1` [VERIFIED — same window, nothing posted, `--notify` not passed]; `bash -n` on the wrapper ok; the four suites this touches are 77 green [VERIFIED]
           guards hit:    three of the repo's own guards tripped on the first push and none were noise. (1) The GOAL-3 twin-surface audit caught a bare `evaluate` colliding with `scorer_identity_monitor.evaluate` — renamed `evaluate_window`, which restores the pinned 17/11/14 census instead of re-pinning it upward to make room for a new twin. (2) The freshness job's invocation allowlist names every `$PYTHON` call; widened to an exhaustive ordered list of four named (flag, module) pairs rather than loosened, which its own docstring rules out. (3) The strategy snapshot regenerated — one line. Following (2) surfaced two real defects, fixed here: step 2b is now import-PROBED and SKIPS when the module is absent (between a merge and the next `-run` sync the running checkout does not carry it, and as written that ordinary gap would have exited 4 on the FRESHNESS job every morning), and `main` no longer lets a crash wear a verdict's clothes — the wrapper maps 0/1/2/3 onto verdicts, so an unhandled exception exiting 1 would have read as "window closing"
           best-known?:   n/a — monitoring; no model claim. It does not extend, shorten or judge any window, and it cannot make a closed window open
           scope:         "this adds one read-only check and its alert to an existing daily job; it does not change the freshness monitor, that job's exit code, any gate, or any artifact"
CORRECTION (2026-09-09, same day): the monitor counted down the STAMPED
           WINDOW only. A4-T1 is the INNER gate — the artifact must ALSO clear
           RFC#210's age bar (`DEFAULT_MAX_SERVED_AGE_DAYS`), and measuring the
           live artifact showed the bar biting on 2026-09-29 while the then-
           proposed window ran to 2026-10-16, so the monitor would have promised
           37 days that did not exist. It now takes whichever cliff comes FIRST
           and NAMES it ("the RFC#210 age bar (trained 2026-08-31)" vs "the
           A4-T1 window"), reports `binding_constraint`/`cliff`/`age_expiry`
           alongside the window, and says "the window runs to X, but the age bar
           bites first" when they differ. The bar is IMPORTED from the pinned
           pipeline, never transcribed — a hardcoded 28 would silently disagree
           the moment the SLA moved; an unimportable module or unreadable
           `trained_date` disables that axis with a stated note rather than
           assuming a generous date. Proven non-vacuously: with the pipeline on
           the path the helper returns 2026-09-28 from THEIR constant and a
           10-16 window binds on age at 13d left (as of 09-15) [VERIFIED
           2026-09-09]. 27 tests (was 18).
NEXT:      after merge + `-run` sync the 05:45 job posts `SERVING WINDOW
           CLOSED — buy path shut` daily until a window is recorded or a
           candidate with eligible regimes is promoted. If the operator
           confirms LONG row 2h (now 2026-09-28, the age-bar ceiling), the
           same monitor starts warning on 2026-09-21 — seven days before the
           next cliff, which is the whole point; and because both cliffs now
           fall on 09-28, the alert will say so explicitly rather than
           implying the window alone is what ends. Follow-up, not here: the
           monitor reads the artifact's stamped expiry plus the age bar, but
           NOT pipeline#310's extension registry, so once that registry
           merges this must consult it too — otherwise it will report CLOSED
           while the runtime serves under an extension.
