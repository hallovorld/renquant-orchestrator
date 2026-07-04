# Readiness monitor for data-accumulation gates

STATUS: implementation complete
DATE: 2026-07-04
SCOPE: orchestrator

## What

Automated readiness monitor (`readiness_monitor.py`) that programmatically
checks every data-accumulation gate in the unified master plan (#231).
Each accumulation item that blocks the next engineering step has a
check function, threshold, and progress percentage.

## Checks implemented

| Check | AC | Source |
|-------|-----|--------|
| N2_pit_snapshots | ≥90 valid accrued days (not stale) | `data/estimate_snapshots/` dirs, validated via `ops/pit/pit_liveness_check.check_snapshot()` |
| N2_pit_features | ≥90 processed days in C1 manifest | `c1_revision_drift.manifest.json` |
| S10_intraday_corpus | ≥100 tickers with intraday data | `data/intraday/` dirs |
| M1_readonly_sessions | 5 clean 105 sessions | `data/105_sessions/*.json` |
| S5_decision_ledger | ≥95% aged fwd-outcome join coverage | `decision_ledger` + `decision_outcomes` tables, via `ledger_attribution.outcome_coverage()` |
| D1_gate_verdict | verdict within last 14 days | `gate_verdicts` table |
| S6_lambda_sweep | 45 experiment sessions (3×15) | `config_experiments` table |
| baseline_trading_days | ≥60 live trading days | `pipeline_runs` table |

## Features

- CLI: `rq-readiness` (text table or `--json`)
- State-transition detection: `--state-file` persists status, logs
  NOT_READY→READY and READY→NOT_READY transitions to `.transitions.jsonl`
- Read-only: never writes to DB or production data paths
- All checks gracefully handle missing dirs/tables (UNKNOWN, not crash)

## Live output (2026-07-04)

```
Readiness: 1/8 checks passing

N2_pit_snapshots       [-] NOT_READY     2.2%  2 snapshot days
N2_pit_features        [-] NOT_READY     2.2%  2 processed days in manifest
S10_intraday_corpus    [+]    READY   100.0%  192 tickers
M1_readonly_sessions   [-] NOT_READY     0.0%  Stage-1 not yet started
S5_decision_ledger     [-] NOT_READY     0.0%  ledger table not yet created
D1_gate_verdict        [-] NOT_READY     0.0%  no gate verdicts recorded
S6_lambda_sweep        [-] NOT_READY     0.0%  sweep not started
baseline_trading_days  [-] NOT_READY    91.7%  55 live trading days
```

## Tests

35 new tests covering all checks, transitions, CLI text/JSON output,
and all-ready exit code.

## Round 2 (Codex review — two checks measuring the wrong thing)

Codex blocked on two schema/validity mismatches:

1. **`check_decision_ledger()` queried an invented schema.** The real S5
   substrate (built earlier the same day in `#320`) is `decision_ledger`
   (keyed `run_id, as_of, scope, gate`) + `decision_outcomes` (keyed
   `as_of, scope, ticker, gate`, with `fwd_5d_ret`/`fwd_20d_ret`/
   `fwd_60d_ret`) — not a `decision_entries.fwd_return` column. Reproduced
   the exact failure: pointed the pre-fix code at a DB with the real
   `decision_ledger` schema and got
   `sqlite3.OperationalError: no such column: fwd_return`, confirming
   codex's "returns UNKNOWN via the broad exception handler" prediction.
   Also found a second, unstated bug: `check_decision_ledger`'s default DB
   path was the shared `runs.alpaca.db` (via `run_all_checks`'s uniform
   dispatch), but the real ledger lives in a DIFFERENT file
   (`decision_ledger.DEFAULT_DB` = `~/renquant-data/decision_ledger.db`) —
   fixed the dispatch in `run_all_checks()` to special-case this check with
   its own default/override (`--ledger-db` CLI flag), rather than sharing
   `--db`.

   Fixed: reuses `ledger_attribution.outcome_coverage()` (the single-impl
   S5 coverage query) unchanged, read-only (checks both tables exist first
   rather than using `connect_attribution()`'s auto-create-via-write path,
   preserving this module's own never-writes contract). "Aged" = `as_of`
   at least 60 calendar days old (`fwd_60d_ret` is the longest tracked
   horizon), measured over a rolling 90-day window ending at that cutoff.

2. **`check_pit_snapshots()` counted bare directory names.** Reproduced the
   exact pre-fix failure: 95 arbitrarily-named (no manifest) directories
   reported `READY` with `current=95`. Found the real, established,
   single-implementation validity contract:
   `ops/pit/pit_liveness_check.check_snapshot()` (already reused unchanged
   by `scripts/kpi_scorecard.py::metric_pit_accrual_days` for the identical
   purpose) — checks all 4 endpoint manifests present, `status=='ok'`,
   `as_of` matching, referenced parquet present + non-empty. Wired that in
   directly (not re-derived).

   On "consecutive": traced the real established AC via
   `metric_pit_accrual_days`'s own docstring and the KPI scorecard's
   `pit_accrual_days` metric definition — the actual single-implementation
   source of truth counts total ACCRUED valid days plus a separate
   staleness signal (latest valid day not >3 calendar days old), not an
   unbroken day-to-day run. This check's own prior docstring claim
   ("consecutive") did not match that real AC, so it's corrected here
   rather than having new consecutiveness-enforcement logic invented from
   scratch; the staleness check IS wired in (a run with ≥90 valid-but-old
   days now correctly reports NOT_READY).

Both fixes verified: constructed the exact pre-fix failure scenarios,
confirmed the OLD code's wrong behavior, confirmed the NEW code's correct
behavior. 8 new/rewritten tests. 2078/2078 relevant tests pass (2
pre-existing, unrelated failures in `test_bundle_consistency_ci_gate.py`
reproduce identically on a clean `origin/main` checkout).
