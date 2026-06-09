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
renquant-orchestrator run-job weekly_alpha158_fund_retrain -- --staged
renquant-orchestrator run-job live_runner_bridge -- \
  --broker readonly-alpaca \
  --once \
  --bridge-bundle-output /tmp/bridge-live-bundle.json
renquant-orchestrator live-parity-fixture \
  --bridge-bundle /tmp/bridge-live-bundle.json \
  --native-bundle /tmp/native-live-bundle.json \
  --fail-on-diff
renquant-orchestrator run-job native_live_parity_fixture -- \
  --bridge-bundle /tmp/bridge-live-bundle.json \
  --native-bundle /tmp/native-live-bundle.json \
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
Schedulers should call `renquant-orchestrator run-job <job_id>` from that
inventory so launchd/cron configs stay pinned to stable job ids instead of
internal Python module paths.
Remaining live bridge jobs also expose a `rehearsal_command` that captures a
readonly bridge bundle with `--bridge-bundle-output`; use that bundle as the
bridge side of live parity before changing production launchd commands.

`native_live_parity_fixture` is the exit gate before flipping
`daily_live_runner_bridge` or `live_runner_bridge` out of umbrella bridge mode.
It compares readonly bridge and native run bundles for decision traces, order
intents, and state mutations while ignoring volatile runtime fields.
