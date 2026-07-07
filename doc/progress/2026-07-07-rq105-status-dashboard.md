# 2026-07-07 — rq105 status dashboard

**PR**: orchestrator feature

## What

One-command status dashboard for rq105:

```bash
python ops/renquant105/rq105_status.py
```

Shows in one screen:
- launchd job states (running / exit code)
- today's log files (exists / size / freshness)
- batch scores availability for today
- latest qualifying DB run (date + scored count)
- paper account cash
- recent errors from launchd stderr logs

## Why

No way to quickly check if 105 is healthy without manually running
`launchctl list | grep rq105`, `ls logs/rq105/`, checking the DB, etc.
Operator asked for a quick dashboard command.

## Scope

New file: `ops/renquant105/rq105_status.py`. Read-only, no side effects.

## Round 2 (codex review)

STATUS: fixed
WHAT: the initial version duplicated five contracts this repo already owns
elsewhere, creating split-brain risk between the dashboard and the real
gates/checks it was meant to summarize:
1. Hard-coded `>= 30` good/warn threshold for scored-candidate count, while
   the canonical batch-export gate had just moved to an evidence-backed
   `MIN_ROWS = 25` (PR #415) — the dashboard would have warned on runs the
   real export gate treats as healthy.
2. A hand-typed `LAUNCHD_JOBS` label list — verified against the real
   `scheduled_jobs.py` registry, these labels didn't even match (e.g.
   `com.renquant.rq105-quote-logger` vs. the real
   `com.renquant.intraday-quote-logger`), so this section would never have
   found any real job regardless of health.
3. A bespoke DB run-selection query (`run_type='live'`, no dedup/floor)
   instead of `tc_measurement._canonical_daily_runs()`'s established
   one-run-per-`run_date`/`MIN_FULL_RUN_CANDIDATES`-floor selection.
4. A hard-coded `RQ_ROOT` default instead of `runtime_paths.default_data_root()`.
5. A naive per-file size/mtime log check instead of
   `rq105_liveness_check.check_collector_data_outputs()` — the real function
   already has per-collector freshness-basis logic (row-event-time for the
   continuous quote feed vs. file-mtime for the two post-close one-shot
   batch collectors) this dashboard's naive check couldn't replicate.

WHY-DIR: codex was right that a dashboard which disagrees with the real
serving/export gate on what counts as healthy is worse than no dashboard —
it actively misleads the operator at the exact moment they need ground
truth.

EVIDENCE:
- `MIN_ROWS` is now imported directly from `export_batch_scores` (identity-
  checked in tests, not just value-checked).
- Launchd job checks now iterate a small `_RQ105_JOB_IDS` list of job_ids,
  resolved against the real `scheduled_jobs.scheduled_jobs()` registry for
  both label and stderr-log path — a job_id absent from the registry is
  dropped, never fabricated. Two of the original six checks
  (`batch-scores-export`, `postclose`, `liveness`) had no corresponding
  registry entry at all and are not part of the launchd-status section any
  more; `postclose`'s actual constituent jobs (`intraday_pairing_logger`,
  `entry_timing_shadow`) are covered directly.
- `_db_latest_run()` now calls `tc_measurement._canonical_daily_runs()` for
  run selection, then a plain count query scoped to that one `run_id` — the
  canonical-run algorithm itself is never re-implemented.
- `RQ_ROOT` is `runtime_paths.default_data_root()`.
- `_today_logs()` now reports `rq105_liveness_check.check_collector_data_outputs()`'s
  verdict directly for the three collectors it covers (quote logger, pairing
  logger, entry-timing shadow); `session_scheduler`/`shadow_serving` (which
  that module doesn't cover) keep a simple existence+mtime check, explicitly
  documented as such rather than silently implying equivalent rigor.
- 8 new tests in `tests/test_rq105_status.py` prove genuine coupling (not
  coincidentally-matching values) for all five points — e.g. patching the
  canonical `MIN_ROWS`/`check_collector_data_outputs` and confirming the
  dashboard's own output changes to match. 7 of 8 confirmed to fail against
  the pre-fix hardcoded implementation (the 8th tests the underlying
  `runtime_paths` resolver directly as a sanity check, not the dashboard's
  usage of it). Full suite 3173/3176, no new failures.

NEXT: `batch-scores-export`, `postclose` (as a wrapper concept), and
`liveness` are not currently tracked in the `scheduled_jobs` registry at
all — a genuine gap in that registry, out of scope here, worth a follow-up
if operator visibility into those specific launchd units is wanted later.
