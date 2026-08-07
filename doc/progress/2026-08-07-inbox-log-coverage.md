# 2026-08-07 — Log coverage 3/16 → 9/16, read from the wrappers not guessed

STATUS:   READY FOR REVIEW. 3 new tests; inbox suite 36 passed
          `[VERIFIED — python3 -m pytest tests/test_agent_inbox.py -q]`.
          Read-only; no job, config, or live surface changes.

WHAT:     Replaces the two guessed log-layout conventions with `_LOG_LOCATION`,
          an explicit `job → (directory, dated-basename|None)` map. Every row was
          read out of that job's own wrapper — its `LOG=` / `exec >>` line or the
          plist `StandardOutPath` — and then confirmed against a real file.

WHY/DIR:  #890 landed `newest_log` with **3 of 16** rows resolving a date
          `[VERIFIED — prior work, doc/progress/2026-08-07-inbox-launchctl-staleness.md]`,
          and its NEXT said to raise that by reading each wrapper rather than
          guessing a convention. Done. Coverage is now **9 of 16**, re-measured
          this session with the REPRO command below `[VERIFIED — REPRO, 2026-08-07]`.

          The reason guessing failed is worth stating: **the log directory
          matches the job name in fewer than half of these**. Measured by
          reading each job's `LOG=`/`exec >>` line
          `[VERIFIED — RenQuant/scripts/monthly_calibrator_refresh.sh:49,66;
          RenQuant/scripts/retrain_panel.sh:29,39;
          ops/run_ops_audit.sh:14 (this repo);
          ops/renquant104/run_model_freshness_monitor.sh:51 (this repo);
          ops/renquant105/run_shadow_serving.sh:21 (this repo), 2026-08-07]`:

```
monthly-calibrator-refresh -> logs/monthly_calibrator/     (not …_refresh)
retrain-panel104           -> logs/retrain_panel/          (not …104)
ops-audit                  -> logs/ops_audit/ops_audit_<date>.log
rq104-model-freshness      -> logs/rq104/model_freshness_<date>.log
rq105-shadow-serving       -> logs/rq105/shadow_serving_<date>.log
```

          Three layouts are in use, not two: a per-job directory of bare
          `YYYY-MM-DD.log`; a per-job directory of `<base>_YYYY-MM-DD.log`; and a
          SHARED directory (`rq104`, `rq105`) of `<base>_YYYY-MM-DD.log`.

          REPRO (produces both the 9/16 count above and the per-row dates below):
```
python3 -c "from ops.agent_inbox import read_launchd_exits as f; r = f(); \
print(sum(1 for x in r if x['newest_log']), '/', len(r)); \
[print(x['job'], '->', x['newest_log']) for x in r]"
```

          What the coverage buys, immediately `[VERIFIED — REPRO, 2026-08-07]`:
          four of the nine resolvable rows are reporting conditions **days
          old** — `monthly-calibrator-refresh` and `rq104-risk-budget` newest
          log 2026-08-01, `retrain-panel104` 2026-08-02, `weekly-wf-promote`
          2026-08-04 — against five that are current (2026-08-06). Before
          this, all nine looked equally current.

EVIDENCE:
artifact:      `ops/agent_inbox.py`, `tests/test_agent_inbox.py`
prod or exp:   **neither** — read-only reporting tool.
existing data: each job's launchd plist and wrapper; `logs/` listings.
best-known?:   yes for these nine. The remaining seven write to undated files
               (`launchd_*.out`, `stdout.log`) or outside `logs/`
               (`shadow-ab-daily` → `~/renquant-shadow-ab/logs/`), so a date is
               genuinely not available — `None` still means "undiscoverable",
               never "no logs".
scope:         one map + one helper; no classification logic changed.

`test_every_mapped_location_is_real_on_this_machine` fails if a mapped directory
disappears. Without it a stale map degrades silently to `None` — reporting
"undiscoverable" for a job that does have logs, which is precisely the failure
the map exists to remove.

NEXT:     The seven unresolvable rows need their wrappers to write a DATED log
          before any lookup can help; that is a change to those wrappers, not to
          this module, and should not be done by widening the guess here.
          Separately, now that stale-vs-current is visible, decide whether a row
          whose code predates its newest log should be demoted from the work
          list — that needs each job's schedule, which this change does not read.

## NOT ESTABLISHED

1. **That the four stale rows are stale conditions.** The exit code may still
   describe reality; it is simply not evidence that it does. The point is that
   the reader can now tell the difference.
2. **That 9/16 is the ceiling.** It is the ceiling for jobs that already write
   dated logs.
3. **Which run produced any retained code.** Unchanged from #890 — `launchctl`
   does not say, and this does not guess.

## REVERT

Restore `_LOG_BASENAME` / `_FLAT_LOG_DIRS` and the previous `_newest_log_date`
body, delete `_LOG_LOCATION`, and drop the three tests added here. No other file
changes.
