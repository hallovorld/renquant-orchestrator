# rq105 collector scheduling (N1 landing package) — ops PR

STATUS:   ops scaffolding for review (repo files only — nothing is installed or executed by this
          PR; installation is the landing step, per the direction-advancement loop's charter).
REVISION: r2 (2026-07-02) — Codex review round 1: fixed an invalid `Hour=25` on the quote-logger
          plist (never a valid launchd hour) and two wrong times (postclose 15:15→13:15,
          liveness 00:00→14:00, all PT); replaced the liveness check's bare-weekday session gate
          with the REAL NYSE exchange calendar (`intraday_quote_logger.default_session_calendar`,
          `pandas_market_calendars`-backed — the same primitive the quote logger and
          `renquant_execution.preopen_cancel_gate` already use), so a market holiday no longer
          fires a false lapse alert; replaced the glob-based "some data exists somewhere"
          output check with an EXACT per-collector check — each collector's own
          `default_*_path()` resolver (not a hardcoded path, not a glob) plus a freshness
          verification (last JSONL row's own `date` field must be today, falling back to file
          mtime only if the last row is unparseable); added `mkdir -p` for both log directories
          to the README's install step (launchd needs `StandardOutPath`/`StandardErrorPath`'s
          parent directory to exist on first launch — it will not create it, unlike each
          wrapper's own runtime `mkdir -p`, which only helps after a job has already run once);
          replaced deprecated `launchctl load`/`unload` with current-macOS
          `bootstrap`/`bootout`/`kickstart` against the per-user `gui/$UID` domain; added
          `tests/test_rq105_collector_scheduling.py` (16 tests: plist schedule parsing, holiday
          gating incl. fail-closed-on-calendar-error, per-collector freshness logic) — see
          EVIDENCE below. Prior: r1 (2026-07-02) — initial landing package.
WHAT:     `ops/renquant105/` — two zsh wrappers (session-long quote logger; post-close pairing +
          entry-timing loggers), a liveness-check script (ntfy per missing output; liveness ≠
          freshness per #212), three launchd plists (06:25 / 13:15 / 14:00 PT weekdays), and a
          README with one-command-per-step install, off-hours smoke commands, the N1 acceptance
          criteria, and open items. Runs from a PINNED run checkout
          (`renquant-orchestrator-run`, main, ff-only) — never the working tree, never the live
          umbrella tree.
WHY/DIR:  #231 N1 is the top NOW item: 105 is DATA-BOUND — the merged Stage-1 collectors
          (#215/#216/#220) produce the pilot corpus that §9.4, S10, and every EXEC-term
          milestone consume, and they are currently NOT RUNNING (the exact deployed-but-dark
          failure the shadow-retrain lapse already demonstrated). The unscheduled-job pathology
          is the known root cause of three frozen model populations; the fix pattern (scheduled
          cadence + separate lapse alert) is #212's, applied here to the collectors.
EVIDENCE: collectors verified present on origin/main with argparse CLIs and internal session
          gating (`intraday_quote_logger --cadence/--once/--force/--env-file`;
          `intraday_pairing_logger --date`; `entry_timing_shadow --date`); existing launchd
          pattern (`com.renquant.*.plist` in ~/Library/LaunchAgents); ntfy.sh + NTFY_TOPIC as
          the established alert channel; `shadow_realtime_serving` requires a
          `--batch-scores-json` producer that does not yet exist (open item #1 — follow-up PR).

          ```
          artifact:      ops/renquant105/{rq105_liveness_check.py,com.renquant.rq105-*.plist,
                          README.md} + tests/test_rq105_collector_scheduling.py
          prod or exp:   ops scaffolding (repo files only; not installed/executed by this PR —
                          no model/data claim, this evidence block covers CORRECTNESS of the
                          scheduling/liveness logic, not any trading result)
          existing data: n/a — no oos_mean_ic/training_runs baseline applies; the relevant
                          "existing data" is the ALREADY-MERGED collector modules
                          (intraday_quote_logger, intraday_pairing_logger, entry_timing_shadow,
                          #215/#216/#220) whose own `default_*_path()` resolvers this liveness
                          check now imports directly rather than re-deriving/hardcoding paths
          best-known?:   best-available fix for this round's 3 findings (invalid/wrong schedule
                          times, holiday-blind gate, unverified glob check); reuses the SAME NYSE
                          calendar primitive already proven in production by
                          intraday_quote_logger/preopen_cancel_gate rather than introducing a
                          second, divergent holiday-handling implementation
          scope:         this is ops/renquant105/rq105_liveness_check.py + 3 plists, round 2 of
                          #232, vs round 1's baseline (Hour=25 invalid, 15:15/00:00 wrong,
                          weekday-only gate, glob-based check) — 16/16 new tests pass, all 3
                          plists parse with valid 0-23 hours matching the documented 06:25/
                          13:15/14:00 PT schedule, real end-to-end run against the actual
                          pandas_market_calendars NYSE calendar confirms today correctly reads
                          as a session day
          ```
NEXT:     Codex review; operator/lander runs the README install (now 4 steps: pin checkout,
          create log dirs, bootstrap the 3 jobs, smoke-test); N1 AC clock starts at first
          session with all three outputs present; follow-up PR wires the batch-scores export
          so the fourth collector (shadow serving) can be scheduled. Separately: a parallel
          fix to #229 (H2 execution roadmap, in flight this session) marks actual
          installation/activation of this package as BLOCKED pending #224 (broker envelope)
          and #227 (measurement pins) landing first, to avoid a retroactively-dirty pilot
          corpus — this PR's own scope (fixing the scheduling/liveness code) is unaffected by
          that gate, only the INSTALL step is.
