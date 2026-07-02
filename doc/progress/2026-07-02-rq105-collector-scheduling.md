# rq105 collector scheduling (N1 landing package) — ops PR

STATUS:   ops scaffolding for review (repo files only — nothing is installed or executed by this
          PR; installation is the landing step, per the direction-advancement loop's charter).
REVISION: r3 (2026-07-02) — Codex review round 2: the code was correct but the DOCUMENTED
          activation contract still contradicted #229's own dependency DAG (README instructed
          bootstrapping all jobs immediately; the N1 AC section started the live 3-session clock
          unconditionally; NEXT told the operator to just install it). Made the repo artifact
          itself unambiguously N1a/N1b split: (1) new `ops/renquant105/check_activation_prereqs.py`
          — a mechanical (non-cryptographic, heuristic RFC-text-marker) guard that refuses with a
          non-zero exit + explicit error if #224 (broker envelope) and #227 (measurement pins)
          haven't both landed on the checked-out RFC; (2) README rewritten into two clearly
          labeled sections — N1a (plist validation, log-dir creation, test suite — safe now, no
          gate) vs. N1b (the actual `launchctl bootstrap` step, prefixed by a MANDATORY guard-check
          command, explicitly labeled "DO NOT RUN until #224 and #227 have both merged"); (3)
          Acceptance section split the same way — N1a acceptance (tests/plist-parsing/dry-run
          calendar check) is gradeable now, N1b acceptance (the 3-live-session clock, #231 §1)
          explicitly states it has NOT started and starts only once N1b is actually activated; (4)
          `check_activation_prereqs.py` verified against the real repo state (correctly REFUSES —
          #224/#227 are still open as of this round) and covered by 7 new tests (missing-both,
          missing-224-only, missing-227-only, both-present, RFC-file-missing, main() refuse/pass
          exit codes) — 23/23 total pass. Prior: r2 (2026-07-02) — Codex review round 1: fixed an invalid `Hour=25` on the quote-logger
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
          scope:         this is ops/renquant105/{rq105_liveness_check.py,
                          check_activation_prereqs.py} + 3 plists + README, round 3 of #232, vs
                          round 2's baseline (correct schedule/holiday-gate/output-check code, but
                          a documented activation path that still let an operator bootstrap live
                          jobs before #224/#227 land) — 23/23 tests pass (16 round-2 + 7 new for
                          the activation guard); `check_activation_prereqs.py` run directly against
                          this worktree's real `main` checkout correctly REFUSES (exit 1) since
                          #224/#227 are still open PRs as of this round
          ```
NEXT:     Codex review. Once #224 AND #227 both merge to main: operator/lander runs N1a (install +
          validate, already safe) then re-checks `check_activation_prereqs.py` (should now exit 0)
          before running N1b (actual `launchctl bootstrap`); N1 AC's live 3-session clock starts
          only at that point, not at install time. Follow-up PR wires the batch-scores export so
          the fourth collector (shadow serving) can be scheduled. This round's fix makes that
          blocked-until-#224/#227 dependency mechanically enforced by this PR's own artifact
          (the guard script), not just documented in the parallel #229 roadmap fix.
