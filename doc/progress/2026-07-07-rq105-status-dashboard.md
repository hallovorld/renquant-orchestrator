# 2026-07-07 — rq105 status dashboard (v2)

**PR**: orchestrator feature — supersedes closed #417

## What

One-command status dashboard for rq105:

```bash
python ops/renquant105/rq105_status.py
```

Shows in one screen:
- launchd job states for the registry's rq105 intraday-session jobs
- today's log files (exists / size / freshness)
- batch scores availability for today
- latest qualifying DB run (date + run_id, per the real exporter contract)
- paper account cash
- recent errors from launchd stderr logs

## Why

Operator asked for a quick way to check 105 health without manually
running multiple commands.

## v1→v2 changes (addresses Codex review on #417)

- Path resolution via `runtime_paths.default_repo_root()` (not hardcoded)
- Batch-scores threshold imported from `export_batch_scores.MIN_ROWS`
  (single source of truth — was hardcoded 30, now tracks canonical 25)
- Launchd jobs discovered dynamically by prefix, not a hardcoded label list
- DB query uses `created_at DESC` ordering (matches canonical exporter)

## Round 2 (Codex review on v2)

STATUS: fixed
WHAT: three remaining split-brain duplications — same class of finding as
#417, on the same conceptual dashboard, this time on genuinely different
code (v2 was a fresh implementation, not a continuation of the #417 fix).
1. Root resolution used `runtime_paths.default_repo_root()` — the umbrella
   checkout resolver — instead of `default_data_root()`, the resolver this
   repo's multi-repo migration built specifically for status/ops entrypoints
   to follow `RENQUANT_DATA_ROOT` once state is no longer anchored under the
   umbrella checkout.
2. Launchd discovery scanned for a `com.renquant.rq105-` prefix — wrapper-era
   naming that predates the native multirepo launchd labels this repo has
   migrated to (e.g. `com.renquant.intraday-quote-logger`). Under the intended
   architecture this would silently report zero jobs.
3. The "latest DB run" check was a bespoke `latest live run with non-null
   panel_score rows` query — looser than, and independent of, the real
   exporter contract (`export_batch_scores._select_source_run`), which also
   requires a completed `pipeline_runs` row, `run_type='live'`, a non-empty
   `strategy`, and — critically — checks the EXACT expected prior NYSE
   session rather than "any date before today".
WHY-DIR: a dashboard that disagrees with the real serving/export gate on
what counts as a healthy upstream run, or that silently reports zero rq105
jobs under the naming scheme this repo is migrating to, is exactly the kind
of split-brain contract this session has repeatedly found and fixed
elsewhere (calibrator/scorer fingerprint triple-impl, tc_measurement
canonical-run selection, retention-policy path authority).
EVIDENCE: `_rq105_job_labels()` now derives `job_id -> launchd_label` from
`scheduled_jobs()` filtered to `cadence == "intraday_session"` — the real
native rq105 job set (`intraday_quote_logger`, `intraday_pairing_logger`,
`entry_timing_shadow`, `intraday_session_scheduler`, `realtime_data_plane`,
`shadow_realtime_serving`). `_db_latest_run()` now calls
`export_batch_scores._select_source_run(con, expected_previous_session(today))`
directly instead of its own query. 7 new tests in `test_rq105_status.py`
prove genuine coupling (patch the canonical source, confirm the dashboard's
output changes to match) for all three fixes; confirmed all 7 fail against
the pre-fix code (`git stash` on just this file) and pass after. Full suite
3176/3179, no new failures.
NEXT: none — all three points addressed.

## Scope

New file: `ops/renquant105/rq105_status.py`. New test file:
`tests/test_rq105_status.py`. Read-only, no side effects.
