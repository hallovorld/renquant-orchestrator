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

## Fix (r2: pipeline-manifest-driven)

Removed the `UMBRELLA_ONLY_STEMS` allowlist (codex r1 rejected it: an
allowlisted stem present in the pipeline directory but failing to import
would silently fall back — still an unpinned substitution).

The pipeline kernel directory IS the manifest: every `.py` file and
sub-package present there is a declared module that MUST import
successfully. Modules that exist only in the umbrella kernel never appear
in this directory, so no allowlist is needed.

Added a minimum-alias-count guard (`_MIN_PIPELINE_KERNEL_MODULES = 10`)
to catch empty/misconfigured pipeline checkouts that would silently
produce zero aliases.

## Tests

4 tests:
- Declared module import failure raises RuntimeError (fail closed)
- Umbrella-only module absent from pipeline dir is not aliased (OK)
- Multiple declared failures all reported in the error
- Too few aliased modules raises RuntimeError (path misconfiguration guard)
