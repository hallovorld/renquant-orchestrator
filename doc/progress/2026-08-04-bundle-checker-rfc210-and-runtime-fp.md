# 2026-08-04 — bundle checker: RFC#210 license mirror + runtime-authoritative calibrator match

## Two doctor REDs, one file, both "a consumer nobody re-taught"

Operator-forwarded system-health RED (`bundle_consistency`) decomposed into two
independent defects in `scripts/check_model_bundle_consistency.py`:

**1. `wf_gate_metadata` FAIL on the governance-served artifact.** The checker
required `passed is True` — the THIRD `passed`-consumer found today that never
learned the RFC#210 freshness-fallback license (after the runtime P-WF-GATE
and the reject-notify tone). Fixed by mirroring the license (exact basis
string, parseable ISO trained_date, age 0..28d, future refuses), rules kept in
LOCKSTEP with renquant-pipeline `kernel/rfc210_license.py` and noted as such.
The license never rescues missing numerics.

**2. `calibrator_scorer_match` FALSE-FAIL by fingerprint-schema divergence.**
The checker compared the calibrator's stamp against
`renquant_common.model_fingerprint.model_content_sha256` (v1-schema value
`c816bf13…`), but the calibrator stamps the runtime's LEGACY-schema value
(`d7bddf2a…`). Measured on the live pair with the pinned pipeline's own
loader: `PanelScorer.load(active).metadata["model_content_fingerprint"] ==
calibrator stamp == d7bddf2a` — **the runtime pair matches**; the red was the
checker asking a different implementation's question (the
[[calibrator-scorer-fingerprint-triple-impl-bug]] class, occurrence #5, this
time fail-noisy rather than fail-closed). Fixed: on common-impl mismatch the
checker now asks the RUNTIME's question directly (pinned-pipeline
PanelScorer fingerprint); runtime match ⇒ PASS with the divergence named in
the detail; pinned pipeline unavailable ⇒ stays FAILED (unknown is not a
pass).

## Verification

- `tests/test_check_model_bundle_consistency.py` + CI-gate suite: **23 passed**
  (5 license cases: served/aged-out/wrong-basis/future-date/never-rescues-
  numerics; fixture gained promotion_basis/trained_date knobs; 4 runtime-
  fallback branch cases through a stub pinned-runtime tree with sys.modules
  isolation: runtime-match passes with the authoritative detail, runtime-
  mismatch / absent tree / omitted repo all stay failed).
- Real bundle, this machine, post-fix: **`deploy_ready: true`**, all 5
  contracts green; details carry `rfc210=served(age=2d)` and the named schema
  divergence.

## Doctor closure

The daily doctor invokes this checker from the orchestrator-run checkout —
the RED clears after merge + run-checkout sync (same deploy batch as the
emitter-contract re-capture #790).
