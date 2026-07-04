# Signal pipeline configuration — 106 feature flag-off pre-build

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: 106 service path (C1/PIT feature pipeline flag-off)

## What

Adds `signal_pipeline_config.py` — the feature-flag-off infrastructure that
makes enabling new signal families a config flip instead of a code change.

### Module
- `SignalSource` dataclass: name, kind, enabled, min_history_days, data_subpath,
  prereg_gate, upstream_repo
- `PipelineConfig`: registry of signal sources with enable/disable partitioning
- `default_config()`: production sources ON (alpha158_fundamental, patchtst),
  future sources OFF (pit_estimate_revisions, fmp_analyst_estimates,
  regime_conditioned_momentum)
- `source_readiness()`: per-source data-availability check vs min_history_days
- `save_config()` / `load_config()`: JSON config I/O (refuses prod paths)
- `pipeline_summary()`: readiness report for CLI/ops

### CLI
- `renquant-orchestrator signal-pipeline [--config C --data-root D --json]`

## Design

Future signal sources (PIT revisions, analyst estimates, regime momentum) are
defined but start DISABLED. Each carries:
- `min_history_days`: minimum data accrual before the source CAN be enabled
- `prereg_gate`: the pre-registration gate that must be passed before enabling

When a signal passes its M-SIG prereg and has enough accrued history, activation
is a config change: set `enabled: true` in the pipeline config JSON.

## Tests

16 new tests. All 1929 pass.
