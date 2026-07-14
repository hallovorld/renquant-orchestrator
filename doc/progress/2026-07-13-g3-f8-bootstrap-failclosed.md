# G3 F-8: bootstrap alias fail-closed

Date: 2026-07-13
PR: fix(bridge): fail-closed bootstrap alias for pipeline kernel imports
Finding: F-8 from 2026-07-04 umbrella compliance audit (PR #444)

## Problem

`bootstrap_multirepo` catches all exceptions from pipeline kernel imports
and silently falls back to the umbrella copy. Only `kernel.preflight` and
`kernel.panel_pipeline` are force-aliased with fail-closed semantics. A
pipeline-side regression (missing dep, syntax error) silently reverts part
of the live run to umbrella code.

## Fix (r3: pipeline-declared ownership contract)

Removed both the `UMBRELLA_ONLY_STEMS` allowlist (codex r1) and the
directory-as-manifest + minimum-count heuristic (codex r2).

The redesign consumes `NON_OWNED_KERNEL_STEMS` declared by the pinned
`renquant_pipeline.kernel` package (companion PR pipeline #198):

- **Owned stems** (not in `NON_OWNED_KERNEL_STEMS`): imported from
  pipeline, fail-closed on any import error.
- **Non-owned stems** (e.g. `meta_label`): pipeline import is skipped
  entirely; routed to an explicit alias target (`renquant_backtesting.
  meta_label`), which also fails closed if unavailable.
- **Missing contract**: if the pinned pipeline does not declare
  `NON_OWNED_KERNEL_STEMS`, the run fails closed (can't verify ownership).
- **Uncovered non-owned stems**: if pipeline declares a non-owned stem
  that orchestrator has no alias target for, fails closed.
- **No owned modules**: empty pipeline kernel directory fails closed
  (replaces the arbitrary `_MIN_PIPELINE_KERNEL_MODULES = 10`).

## Tests

7 tests:
- Owned module import failure → RuntimeError (fail closed)
- Umbrella-only module absent from pipeline dir → not aliased (OK)
- Multiple owned failures → all reported in the error
- Missing `NON_OWNED_KERNEL_STEMS` → RuntimeError
- Non-owned stem skips pipeline import, uses alias target
- Non-owned stem alias target failure → RuntimeError (fail closed)
- No owned modules discovered → RuntimeError
- Uncovered non-owned stem → RuntimeError
