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
| N2_pit_snapshots | ≥90 consecutive daily snapshots | `data/estimate_snapshots/` dirs |
| N2_pit_features | ≥90 processed days in C1 manifest | `c1_revision_drift.manifest.json` |
| S10_intraday_corpus | ≥100 tickers with intraday data | `data/intraday/` dirs |
| M1_readonly_sessions | 5 clean 105 sessions | `data/105_sessions/*.json` |
| S5_decision_ledger | ≥95% forward-return coverage | `decision_entries` table |
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
