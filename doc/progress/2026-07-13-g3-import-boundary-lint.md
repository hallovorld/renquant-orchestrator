# 2026-07-13 G3 import boundary lint (V-018 remediation)

Ported the renquant-model import boundary test pattern to renquant-orchestrator.
The existing test checked broker/torch/xgboost prefixes; this PR adds
`renquant_pipeline.kernel` to the forbidden list (V-018) and adds parametrized
tests for the three known V-005 violation modules (`native_context_hydration`,
`live_bridge`, `train_gbdt`) that verify their kernel imports remain deferred
(not eagerly loaded at module import time).
