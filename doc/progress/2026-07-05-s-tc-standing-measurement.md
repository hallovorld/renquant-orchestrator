# S-TC: standing transfer coefficient measurement

DATE: 2026-07-05

## What

Promote the POC transfer coefficient measurement (`scripts/poc_transfer_coefficient.py`,
3 rounds of Codex review) to a schedulable standing measurement module.

## Changes

- `src/renquant_orchestrator/tc_measurement.py` — new module:
  - `compute_buy_side_tc()` — core computation per run (admission taxonomy from POC round 3)
  - `run_measurement()` — batch: find un-measured canonical runs, compute, persist
  - `main(argv)` — CLI entry point with `--runs-db`, `--ledger-db`, `--dry-run`
  - Persists to `tc_metrics` table in `decision_ledger.db` (append-only, WAL, idempotent)
- Job runner: `tc_measurement` registered in `_MODULE_JOBS` + `scheduled_jobs` inventory
- Tests: 10 new tests covering classification, computation categories (measured,
  no_deployment, zero_dispersion, insufficient population), end-to-end persistence,
  idempotency, dry-run, empty DB
- Strategy snapshot regenerated for the new source module
- `doc/roadmap-backlog.json`: mark `s2-wire-gate-ledger` done (code-complete across all
  repos — pipeline #176 + orchestrator #133 + DecisionLedgerWriteTask registered in
  pp_inference.py; config enablement is a separate operational step)

## Sprint status note

Cross-repo scan (2026-07-05) confirms ALL engineering code for SHORT-tier items is merged
with flags OFF across all 9 repos. Remaining work is config enablement + operational
verification, not code.
