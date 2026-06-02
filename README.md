# renquant-orchestrator

Pinned-subrepo daily orchestration for RenQuant.

Operating model: https://github.com/hallovorld/RenQuant/blob/main/doc/arch/subrepo-operating-model.md

Repository map: [RENQUANT_REPOS.md](RENQUANT_REPOS.md)

Local automation:

```bash
make test
make doctor
python -m renquant_orchestrator daily-contract \
  --strategy-config ../renquant-strategy-104/configs/strategy_config.json \
  --output-dir /tmp/renquant-daily-contract \
  --broker-type paper
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
