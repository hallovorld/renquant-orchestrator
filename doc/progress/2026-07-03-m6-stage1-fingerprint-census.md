# M6 stage-2 step-1: fingerprint census (orchestrator deliverable)

Design: `doc/design/2026-07-03-m6-stage2-fingerprint-migration.md` §3 step 3 /
§3c (the read-only "both computations agree" proof). Step 0 (legacy
pre-stamp) executed 2026-07-03 under operator grant — 47/47 artifacts carry
legacy stamps.

## Shipped

- `scripts/fingerprint_census.py` — read-only census over the §3a inventory
  (prod + both shadow lanes + the 43-fold active WF corpus + all calibrator
  families). Reuses the step-0 tool's inventory resolution and guarded legacy
  hashing by IMPORT (never re-derived; triple-impl lesson, design §5 row 3);
  v1 hashes via `renquant_common.model_fingerprint` imports only. Grades every
  artifact under the ONE semantics its stamp declares (version dispatch):
  versionless ⇒ legacy stamp == legacy recompute; `fingerprint_schema_version:
  1` ⇒ v1 stamp == v1 recompute AND (when present) the
  `model_content_fingerprint_legacy_081` audit field == the legacy recompute
  over the payload minus the stage-2-added top-level fields; unstamped ⇒ RED.
  Calibrator bindings dispatched the same way (cross-schema = RED by
  construction). Machine-readable JSON report for run bundles; exit 0 green /
  2 red.
- `tests/test_fingerprint_census.py` — fixture-tree coverage: all-legacy
  green, unstamped/tampered red, v1 green + corrupt red, legacy-081 audit
  green/red, binding mismatch + cross-schema red, regime-calibrator
  out-of-scope, manifest stamped-field agreement, read-only property,
  exit codes.
- `tests/test_prestamp_legacy_fingerprints.py` unchanged: the pipeline
  stage-1 PR keeps `_scorer_fingerprints_from_payload` importable as a
  payload-only back-compat view, so the step-0 verifier-acceptance tests pass
  against both pipeline main and the dispatch branch.

## Real-tree census (2026-07-03, read-only, post step-0)

GREEN: 47/47 artifacts (2 prod, 2 shadow, 43 WF folds) legacy-stamped with
stamp == legacy recompute; 47/47 v1-ready (no unclassified keys ⇒ step-2
dry-run would not abort); 45/45 active (RED-severity) bindings MATCH or
FAMILY_SPLIT_NA; 0 red manifest rows. 22 WARN rows are historical snapshot
calibrators (`.staging` / `weekly_rollback_*`) with stale declarations —
non-blocking by design (step-0 reported the same).

## Cross-repo dependencies (separate PRs per §4 ownership)

- renquant-common 0.9.2: `model_content_fingerprint_legacy_081` +
  `restamp_provenance` classified OPERATIONAL (hash-preserving; schema
  version stays 1). The census audit-field tests skip on older siblings.
- renquant-pipeline stage-1: version-dispatched verification behind
  `ranking.panel_scoring.fingerprint.accept_legacy_stamps` (default true) at
  both fail-closed binding checks + divergence telemetry.

## Remaining for stage-2 (design §3/§4)

- strategy-104 config PR introducing the flag explicitly (default true).
- Deploy: pin bumps + live pin-align + venv >= 0.9.2 (evidence recorded).
- Step-2 v1 re-stamp run (operator grant; dry-run first), then census green
  over the step-3 window (7 daily runs + weekly refit + wf_promote), flag
  flip (step 4), shim removal (0.10, step 5).
- Step-3 criterion (e) (zero legacy-route acceptances) reads the pipeline's
  `fingerprint-dispatch verify:` telemetry from run bundles — wire the census
  + telemetry scrape into the daily bundle during the window.
