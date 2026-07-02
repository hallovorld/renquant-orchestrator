# rq105 collector scheduling (N1 landing package) — ops PR

STATUS:   ops scaffolding for review (repo files only — nothing is installed or executed by this
          PR; installation is the landing step, per the direction-advancement loop's charter).
REVISION: r1.
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
NEXT:     Codex review; operator/lander runs the README install (3 commands); N1 AC clock
          starts at first session with all three outputs present; follow-up PR wires the
          batch-scores export so the fourth collector (shadow serving) can be scheduled.
