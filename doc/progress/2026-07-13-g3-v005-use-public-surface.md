# fix(V-005): use pipeline public surface instead of kernel internals

**Date**: 2026-07-13
**PR**: orchestrator fix/v005-use-public-surface
**Depends on**: pipeline #197

## Change

Replace 3 `from renquant_pipeline.kernel.*` imports in
`native_context_hydration.py` with imports from
`renquant_pipeline.public` — the lazy re-export surface added in
pipeline #197. Only `LocalStore`, `HoldingState`, `RegimeState` use the
public surface (genuine cross-repo type contracts).

`LoadUniverseJob`/`UniverseContext` keep direct kernel imports — pipeline
execution internals, not suitable for a public contract (codex review).
`_last_completed_nyse_session` keeps its kernel import — use
`renquant_common.market_calendar` instead (codex review).
`train_gbdt.py` also keeps its direct kernel import (fault-tolerant
try/except path).

All imports remain function-scoped (deferred), preserving the existing
lazy-load behavior.

## Motivation

V-005 (architecture audit): orchestrator's direct imports from pipeline
kernel internals create fragile coupling.  The public surface decouples
orchestrator from kernel module layout changes.
