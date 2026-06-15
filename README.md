# renquant-orchestrator

Pinned-subrepo daily orchestration for RenQuant.

Operating model: https://github.com/hallovorld/RenQuant/blob/main/doc/arch/subrepo-operating-model.md

Repository map: [RENQUANT_REPOS.md](RENQUANT_REPOS.md)

Local automation:

```bash
make test
make doctor
renquant-orchestrator daily-contract \
  --strategy-config ../renquant-strategy-104/configs/strategy_config.json \
  --output-dir /tmp/renquant-daily-contract \
  --broker-type paper
renquant-orchestrator scheduled-jobs
renquant-orchestrator scheduled-jobs --fail-on-umbrella-bridge
renquant-orchestrator scheduled-health --status-json /tmp/renquant-scheduled-health.json --strict
renquant-orchestrator engineering-census --strict
python scripts/engineering/census_ci.py
renquant-orchestrator run-job weekly_alpha158_fund_retrain -- --staged
renquant-orchestrator live-offboard-status --strict \
  --env-file ../RenQuant/.env
renquant-orchestrator live-rehearsal-plan --strict \
  --output-dir /tmp/renquant-live-rehearsal \
  --env-file ../RenQuant/.env
renquant-orchestrator live-offboard-rehearsal --strict \
  --output-dir /tmp/renquant-live-rehearsal \
  --env-file ../RenQuant/.env
renquant-orchestrator run-job live_runner_bridge -- \
  --broker readonly-alpaca \
  --once \
  --native-inference-payload-output /tmp/renquant-live-rehearsal/live-native-inference.json \
  --bridge-bundle-output /tmp/renquant-live-rehearsal/live-bridge-bundle.json
renquant-orchestrator run-job native_live_execution_payload_fixture -- \
  --inference-json /tmp/renquant-live-rehearsal/live-native-inference.json \
  --output-json /tmp/renquant-live-rehearsal/live-native-execution.json \
  --broker-name readonly-alpaca
renquant-orchestrator run-job native_live_run_candidate -- \
  --inference-json /tmp/renquant-live-rehearsal/live-native-inference.json \
  --execution-output-json /tmp/renquant-live-rehearsal/live-native-execution.json \
  --commit-plan-output-json /tmp/renquant-live-rehearsal/live-native-commit-plan.json \
  --output-json /tmp/renquant-live-rehearsal/live-native-bundle.json \
  --broker-name readonly-alpaca
renquant-orchestrator live-parity-fixture \
  --bridge-bundle /tmp/renquant-live-rehearsal/live-bridge-bundle.json \
  --native-bundle /tmp/renquant-live-rehearsal/live-native-bundle.json \
  --fail-on-diff
renquant-orchestrator run-job native_live_parity_fixture -- \
  --bridge-bundle /tmp/renquant-live-rehearsal/live-bridge-bundle.json \
  --native-bundle /tmp/renquant-live-rehearsal/live-native-bundle.json \
  --fail-on-diff
```

The market-anomaly retrain trigger is the only path that uses yfinance; install
`renquant-orchestrator[market-data]` for that scheduled job.

This repo owns the top-level daily flow:

1. validate strategy/data/config inputs,
2. run a model-training pipeline,
3. run runtime inference,
4. execute order intents through an injected broker,
5. run an optional backtest/simulation check,
6. persist one auditable run bundle.

It does not own model logic, signal logic, broker implementations, or data
materialization. Those stay in their respective subrepos.

`scheduled-jobs` is the migration control surface for cron and operator loops:
it emits the training/inference/trading/ops job inventory, marks jobs that still
bridge to umbrella code, and can fail closed until those bridges are offboarded.
Its `summary` also reports remaining bridge job ids, native offboard blocker
counts, exit-gate counts, and jobs that still consume umbrella state paths.
Schedulers should call `renquant-orchestrator run-job <job_id>` from that
inventory so launchd/cron configs stay pinned to stable job ids instead of
internal Python module paths.
Remaining live bridge jobs also expose a `rehearsal_command` that captures a
readonly bridge bundle with `--bridge-bundle-output`; use that bundle as the
bridge side of live parity before changing production launchd commands.
They also expose `native_replacement_job_id` and `native_cutover_command` so the
final scheduler switch has a machine-readable target once parity is green.
`scheduled-health` is the last-exit control surface. Feed it a JSON object keyed
by scheduled `job_id` with `last_exit`, optional timestamps, `reason`, and
`last_log_path`; it emits `ok`, `reject`, `crash`, or `unknown` per job and a
red-job summary. `live-offboard-status` can fold in the same status source with
`--scheduled-health-json` so the operator panel shows bridge blockers and red
scheduled jobs together.
`live-offboard-status` reports `stage_status.current_stage` and
`stage_status.next_blocker` so operators can distinguish credential preflight,
bridge capture, native payload generation, parity, and final scheduled-job
cutover blockers.

`engineering-census` is the reproducibility surface for architecture and
research docs. It emits repo SHAs, key file line counts, strategy-config key
counts, and AST-counted `buy_blocked=True` writers with file/line evidence.
Use `--expect-buy-blocked-writers N --strict` in CI or review branches when a
GateRegistry migration intentionally changes the direct writer count.

`native_live_parity_fixture` is the exit gate before flipping
`daily_live_runner_bridge` or `live_runner_bridge` out of umbrella bridge mode.
It compares readonly bridge and native run bundles for decision traces, order
intents, and state mutations while ignoring volatile runtime fields.
`native_live_run_candidate` is the first scheduled native live job candidate:
it consumes native inference payloads, builds readonly execution payloads, and
emits readonly commit-plan and parity-ready native live bundle artifacts without
importing `RenQuant live.runner`.
`native_live_context_fixture` builds the explicit config/market/account context
fixture consumed by native inference. `native_live_inference_fixture` is the
preceding native producer for already hydrated native contexts; its payloads carry
`metadata.native_inference_producer.source=renquant_orchestrator.native_live_inference`.
`live-offboard-status` treats bridge-captured or unknown inference producers as
cutover blockers, so a green parity run cannot accidentally clear the remaining
bridge jobs while inference is still sourced from `live.runner`.
The native live run candidate remains readonly until live state and broker
commit semantics are ported into `renquant-execution`.
`live-offboard-status --strict` combines that inventory with the readonly
rehearsal preflight so operators can see the remaining bridge blockers and
missing Alpaca environment before attempting a production launchd switch.
`live-offboard-rehearsal --strict` executes the readonly evidence chain
(`bridge_capture`, `native_live_run_candidate`, `native_live_parity`) and writes
`<mode>-offboard-rehearsal-manifest.json`, `<mode>-rehearsal-plan.json`, and
`<mode>-offboard-status.json` under the chosen output directory. It never runs
the `native_live_commit_template`; live execution and persistence commit remain
separate operator-gated cutover steps.
