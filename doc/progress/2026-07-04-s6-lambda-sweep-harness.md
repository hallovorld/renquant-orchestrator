# S6: QP lambda sweep harness

DATE: 2026-07-04
PR: #333 (feat/104-105-code-completion)

## What

`scripts/s6_lambda_sweep.py` — promoted version of `poc_lambda_sweep.py` that
writes structured experiment rows to the `config_experiments` table in
`runs.alpaca.db`. Runs the QP solver at multiple `cash_drag_lambda` values
against real daily-run inputs (mu/sigma from `candidate_scores`, w_current from
`trades.target_pct`).

Companion: `src/renquant_orchestrator/config_experiment_store.py` provides the
table DDL and insert/query helpers consumed by both this script and the
readiness monitor's `check_lambda_sweep` gate.

## Key design choices

- Read-only on all tables except `config_experiments` (new table, created if absent)
- Imports the real pipeline solver (`renquant_pipeline.kernel.portfolio_qp`)
- Records per-run per-lambda: deployed fraction, position count, turnover estimate
- The readiness monitor S6 gate checks for ≥3 configs × 15 sessions = 45 experiments

## Tests

10 tests in `tests/test_s6_lambda_sweep.py` — solver mock, DB round-trip, dry-run,
edge cases.
