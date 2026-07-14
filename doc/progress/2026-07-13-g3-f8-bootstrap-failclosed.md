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

## Fix

Added `UMBRELLA_ONLY_STEMS` frozenset allowlist: stems that are known to
exist only in the umbrella kernel and are expected to fail import from the
pipeline. Any other stem that fails to import raises `RuntimeError` with
the specific module name and error — fail closed.

The allowlist contains: fundamentals, macro, macro_features,
manifest_uri_resolver, drph, model_acceptance, model_acceptance_legacy,
meta_label, metrics, reconciliation, registry.

## Tests

4 new tests:
- Non-allowlisted stem import failure raises RuntimeError
- Allowlisted (umbrella-only) stem failure is silently accepted
- Multiple failures are all reported in the error message
- UMBRELLA_ONLY_STEMS is a frozenset (immutable)
