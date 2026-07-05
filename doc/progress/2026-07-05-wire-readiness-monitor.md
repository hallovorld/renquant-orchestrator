# Wire readiness_monitor into CLI + scheduled jobs

STATUS: delivered
WHAT: Wire the existing `readiness_monitor` module into the orchestrator CLI,
scheduled-job inventory, and job-runner dispatch table.
WHY/DIR: The readiness monitor was implemented and tested but not reachable via
the CLI or scheduled automation. Wiring it enables `renquant-orchestrator
readiness-monitor` and `renquant-orchestrator run-job readiness_monitor`.
EVIDENCE: `make test` passes (95 pass, 2 pre-existing unrelated failures from
missing `renquant_execution` module).
NEXT: Operator can schedule the new `com.renquant.readiness-monitor` launchd job
for daily automated readiness checks.

## Changes

- `src/renquant_orchestrator/cli.py`: Added `readiness-monitor` subcommand with
  `--data-root`, `--db`, `--ledger-db`, `--json`, `--state-file` flags, matching
  the module's own `main(argv)` API.
- `src/renquant_orchestrator/scheduled_jobs.py`: Added `readiness_monitor`
  ScheduledJob (kind=ops, cadence=daily, launchd_label=com.renquant.readiness-monitor).
- `src/renquant_orchestrator/job_runner.py`: Added dispatch mapping
  `readiness_monitor -> renquant_orchestrator.readiness_monitor`.
- `tests/test_scheduled_jobs.py`: Updated inventory count assertions
  (total 32->33, native_multirepo 30->31, umbrella_state_dependency 20->21).
- `data/strategy_snapshot.json`: Regenerated via `scripts/generate_strategy_snapshot.py --update`.
