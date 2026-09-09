# Count down the serving exception instead of discovering it on expiry day   (PR #TBD)

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
           existing data: `tests/test_serving_window_monitor.py` 16 passed (the 09-01 six-days-out warning with its exact wording, lead boundary inclusive at 7d, the 09-08 CLOSED state, no-exception silence, an artifact that stands on its own, unreadable expiry/regime-stamp/payload all `unknown`, CLI exit codes, `--notify` only on trouble, `--quiet`, missing artifact fails closed) [VERIFIED — 2026-09-09 ~01:0x PDT]; read-only run against the LIVE served artifact: as-of 2026-09-01 → `WARN days_left=6 eligible=0` naming 2026-09-07 and the sell-only consequence; as-of 2026-09-07 → `WARN days_left=0`; as-of 2026-09-08 → `CLOSED days_left=-1` [VERIFIED — same window, nothing posted, `--notify` not passed]; `bash -n` on the wrapper ok
           best-known?:   n/a — monitoring; no model claim. It does not extend, shorten or judge any window, and it cannot make a closed window open
           scope:         "this adds one read-only check and its alert to an existing daily job; it does not change the freshness monitor, that job's exit code, any gate, or any artifact"
NEXT:      after merge + `-run` sync the 05:45 job posts `SERVING WINDOW
           CLOSED — buy path shut` daily until a window is recorded or a
           candidate with eligible regimes is promoted; if the operator
           confirms LONG row 2h (window to 2026-10-16), the same monitor
           starts warning on 2026-10-09 — seven days before the next cliff,
           which is the whole point. Follow-up, not here: the monitor reads
           only the artifact's stamped expiry, so once pipeline#310's
           extension registry exists it should also consult it (otherwise it
           will report CLOSED while the runtime serves under an extension).
