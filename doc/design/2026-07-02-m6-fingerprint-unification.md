# M6/R2: content-fingerprint unification — the measured divergence and the shared contract

STATUS: design for review (docs only; implementation lands as renquant-common + per-repo
migration PRs after discussion). Task M6/R2 of the unified plan (#231 Term PROCESS).
DATE: 2026-07-02

## 1. The divergence, measured (not asserted)

Three recurring fail-closed no-trade incidents (05-27, 06-22, 07-01) trace to
`model_content_sha256` disagreeing across repos. Inventory (read-only, 2026-07-02):

| Site | Semantics | Mechanism |
|---|---|---|
| **pipeline** `kernel/panel_pipeline/panel_scorer.py:108` | **SUBTRACTIVE**: hash payload minus `_MUTABLE_ARTIFACT_KEYS` denylist (`metadata`, `wf_gate_metadata`, `artifact_path`, `artifact_sha256`, `artifact_fingerprint`, `model_content_fingerprint`, `config_fingerprint`, …) | any NEW key is hashed by default |
| **model** `renquant_model_gbdt/fit_calibrator_alpha158_fund.py:35` | **ADDITIVE**: hash an explicit ~12-field allowlist (`params`, `feature_cols`, `feature_means/stds`, `feature_norm_*`, `label_col`, …) | any NEW key is ignored by default |
| **umbrella** `scripts/fit_calibrator_alpha158_fund.py:32` | imports the PIPELINE impl (not a third copy — one prior belief corrected); `stamp_walkforward_fingerprints.py` to be classified in the implementation PR | — |

**Mismatch by construction**: an artifact stamped under the model repo's allowlist and
verified under the pipeline's denylist disagrees the moment ANY key exists outside both
lists — new predictive fields (allowlist silently ignores → false MATCH) and new
operational fields not yet in the denylist (denylist hashes them → false MISMATCH, the
observed incident class). Each incident was "fixed" by a manual re-stamp, which mutates the
artifact and re-arms the trap.

## 2. The shared contract (proposal)

One implementation in **renquant-common** (`renquant_common.model_fingerprint`), with
**TOTAL classification** — the design property both current impls lack:

1. Every payload key MUST be classified as exactly one of {PREDICTIVE, OPERATIONAL}.
   An **unclassified key fails LOUDLY at stamp time** (never a silent default in either
   direction — the silent defaults are the root cause).
2. The hash covers the PREDICTIVE set; the classification tables ship IN the shared module
   and carry a `fingerprint_schema_version` stamped into the artifact next to the hash.
3. Verification checks hash AND schema version; a version gap is its own explicit error
   ("re-stamp under vN" — an auditable operation), never a bare mismatch.
4. Migration: transition artifacts carry BOTH old and new hashes; verifiers accept either
   for one release window; re-stamp tooling becomes a thin wrapper over the shared impl;
   cross-repo fixtures assert identical hashes on identical payloads from all import sites
   (the test that has never existed).

## 3. Acceptance (from #231 M6, made concrete)

Fixture green from all import sites (pipeline, model, umbrella scripts); every stamp/verify
call site migrated (inventory in §1 + `stamp_walkforward_fingerprints.py` +
`stamp_patchtst_fingerprint.py`); **zero fingerprint-class fail-closed events in 30 days**
post-deploy; the re-stamp runbooks reference the shared impl only.

## 4. Ownership + order

renquant-common PR (the module + tables + fixtures) → model + pipeline migration PRs
(delete local impls, import shared) → umbrella script re-point → 30-day watch. Boundary
note: the classification TABLES are a modeling contract (model repo reviews them); the
MECHANISM is shared infrastructure (common).
