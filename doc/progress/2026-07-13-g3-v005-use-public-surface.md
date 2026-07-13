# fix(V-005): use pipeline public surface instead of kernel internals

**Date**: 2026-07-13
**PR**: orchestrator fix/v005-use-public-surface
**Depends on**: pipeline #197

## Change

Replace 5 `from renquant_pipeline.kernel.*` imports in
`native_context_hydration.py` with imports from
`renquant_pipeline.public` — the stable re-export surface added in
pipeline #197.

`train_gbdt.py` keeps its direct kernel import (it's inside a
try/except fault-tolerant path, and the public module's eager loading
would bring in unneeded dependencies).

All imports remain function-scoped (deferred), preserving the existing
lazy-load behavior.

## Motivation

V-005 (architecture audit): orchestrator's direct imports from pipeline
kernel internals create fragile coupling.  The public surface decouples
orchestrator from kernel module layout changes.
