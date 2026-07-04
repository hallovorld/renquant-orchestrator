# Signal pipeline configuration — 106 readiness scaffolding

**Date**: 2026-07-04
**PR**: #321
**Master plan ref**: 106 service path (C1/PIT feature pipeline flag-off pre-build)

## What

Adds `signal_pipeline_config.py` — a **pre-build inventory and readiness
scaffold** for the 106 signal evolution path.

**This is scaffolding, NOT an already-effective pipeline toggle.** No existing
training or feature-building flow reads this registry yet. Wiring a real consumer
so `enabled=True` actually feeds a retrain is downstream work tracked by M-SIG.

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
registered but start DISABLED. Each carries:
- `min_history_days`: minimum data accrual before the source CAN be enabled
- `prereg_gate`: the pre-registration gate that must be passed before enabling

The activation path is not yet wired: when a real consumer (retrain flow) is
connected to read this config, enabling a source will become a config flip.

## Tests

16 new tests.
