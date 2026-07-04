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
| S10_intraday_symbols_present *(informational, round 3)* | days/tickers accrued so far, no frozen target | `logs/renquant105_pilot/intraday_ticks.jsonl` (the real N1 feed) |
| M1_session_logs_observed *(informational, round 3)* | raw session-log file count only | `data/105_sessions/*.json` |
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

**Historical snapshot — predates the round-4 fix below.** This is the
original (buggy) output cited in Codex's round-3/round-4 review as the
false-positive example (`S10_intraday_corpus READY 192 tickers` was dead
code counting a fictional directory). Current output uses the renamed,
informational `S10_intraday_symbols_present`/`M1_session_logs_observed`
checks and a different `N/M authoritative checks passing` denominator.

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

## Round 4 (Codex review — two more checks measuring proxies)

Codex confirmed S5/N2 (round 3's fix) are genuinely fixed, but flagged
`S10_intraday_corpus` and `M1_readonly_sessions` as still measuring proxies
that can false-green: S10 counted ticker directories instead of the actual
S10 binding step (day-accrual per the S10 research docs); M1 counted raw
session-log files against a much stronger real AC (decisions logged,
nothing placed, four-class replay green every tick, census complete —
citing `Stage2Authorization`'s `evidence.shadow_sessions_clean`/
`evidence.replay_audits_green` contract).

**S10 — deeper bug than reported.** `check_intraday_corpus()` counted
directories under `data/intraday/`, a path the real N1 collector
(`intraday_quote_logger.py`) never writes to at all — it appends
`{date, ticker, ...}` records to a single rolling JSONL
(`default_tick_feed_path()`). The old check was silently dead code (always
UNKNOWN on any real data root), not merely measuring the wrong axis.
Fixed to read the real feed and report distinct-days + distinct-tickers
accrued. No fixed `N_days` target exists anywhere in the codebase to gate
READY on — the actual power calculation
(`scripts/s10_open_auction_is_study.py::_cluster_robust_prospective_n_days`)
is a data-dependent sensitivity table, not a frozen constant, and computing
it here would require this filesystem-only monitor to run real statistical
power analysis (out of scope). Renamed to `S10_intraday_symbols_present`,
marked `authoritative=False` (Codex's own explicit fallback option).

**M1 — no real per-session verifier is cheaply available.** The sharpest
real evidence contract for "5 clean sessions" is `Stage2Authorization`'s
`evidence.shadow_sessions_clean`/`evidence.replay_audits_green`
(`intraday_live_executor.py`) — but that's a SCHEMA VALIDATOR over a
manually-authored authorization file (`load_stage2_authorization()`), not
an automated per-session re-derivation from raw logs; it can only confirm
a human's *claim* passes shape/value checks. The actual per-tick verifier
that could derive "clean" is `intraday_replay_audit.replay_session()`, but
it requires binding a live tick-runner to the real pipeline ("fail closed"
per its own docstring) and has no default persisted report location
(`--report-out` is optional/operator-chosen) — nothing on disk this
read-only monitor can safely glob for without invoking that heavy pipeline
machinery itself. Kept the raw file count (genuinely all that's cheaply
knowable) but renamed to `M1_session_logs_observed`, marked
`authoritative=False`, and the detail string now states explicitly what it
does NOT verify.

**Mechanism**: added `CheckResult.authoritative: bool = True`. Non-
authoritative results are still computed, printed (tagged
`[informational — excluded from READY count]` in the text table, with an
`authoritative` field in JSON), but excluded from both the READY/total
ratio and the overall exit code.

9 new/rewritten tests (including a direct regression proving the old
directory-based S10 path was dead code, and that six session files no
longer report READY or block `rc==0`). 2081/2081 relevant tests pass (the
same 2 pre-existing, unrelated `test_bundle_consistency_ci_gate.py`
failures reproduce identically on a clean `origin/main` checkout).
