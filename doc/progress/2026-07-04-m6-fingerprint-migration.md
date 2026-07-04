# M6 call-site migration: orchestrator → renquant-common fingerprint

DATE: 2026-07-04

## What changed

Migrated orchestrator's `model_content_sha256` imports from the pipeline's
legacy per-repo implementation (`kernel.panel_pipeline.panel_scorer`) to the
canonical shared implementation in `renquant_common.model_fingerprint`.

Two call sites migrated:
1. `src/renquant_orchestrator/model_bundle.py` — `_default_model_content_sha256()`
2. `scripts/check_model_bundle_consistency.py` — inline fallback import

## Why

M6/R2 of the unified plan: "one shared content-fingerprint impl — kills
the recurring fail-closed no-trade class (3 incidents)." The shared module
was built in renquant-common (760 lines, total classification schema,
schema-versioned). This PR migrates the orchestrator call sites to use it.

The legacy pipeline import was a try/except fallback chain
(`renquant_pipeline.kernel...` → `kernel...`) that silently picked up
whichever copy was on PYTHONPATH — exactly the triple-impl divergence
mechanism that caused the 3 incidents.

## Test plan

- `test_check_model_bundle_consistency.py`: 16 pass (injected mock, not
  import-dependent)
- `test_scheduled_jobs.py`: 9 pass (scheduled job inventory unchanged)
