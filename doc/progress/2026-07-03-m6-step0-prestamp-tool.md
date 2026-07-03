# M6 stage-2 step-0: legacy pre-stamp tool

DATE: 2026-07-03
DESIGN: `doc/design/2026-07-03-m6-stage2-fingerprint-migration.md` §3 step 0 +
§3a (PR #270, branch `design/m6-stage2-fingerprint-migration`).
DELIVERABLE: `scripts/prestamp_legacy_fingerprints.py` +
`tests/test_prestamp_legacy_fingerprints.py`. TOOL ONLY — running it against
the live tree is a separate landing action under operator grant.

## Verifier-semantics verification (the design's load-bearing claim)

Verified against code before building (renquant-pipeline and
renquant-backtesting origin/main, 2026-07-03): the fail-closed verifiers are
READ-STAMP-AND-COMPARE with list-OR acceptance, not strict
recompute-and-compare — so the step-0 stopgap works as designed.

- `job_panel_scoring.py::_assert_calibrator_matches_scorer` compares
  `_fingerprint_values(scorer_meta)` vs the calibrator's declared identities
  via `_any_fingerprints_match` (pure comparison, no hashing). The active
  scorer identity comes from `stamp_artifact_metadata` (0.9.1 shim), whose
  `setdefault` preserves an existing `model_content_fingerprint` stamp.
- `walk_forward/loader.py::_scorer_fingerprints_from_payload` (~:158,
  identical in pipeline and backtesting) appends the bare-name recompute
  inside `try/except` (fail-soft) AND every stamped identity key from the
  payload top level + nested `metadata`; `_assert_calibrator_matches_entry`
  (:424, fail-closed) matches ANY-of. A legacy stamp therefore keeps every
  fold green even when the recompute goes v1.
- The arming sites prefer the stamp too: umbrella
  `fit_calibrator_alpha158_fund.py::_artifact_fingerprint` resolves
  `payload.get("model_content_fingerprint") or <recompute>` — a stamped
  artifact pins the weekly refit to the legacy identity.

Census recomputed read-only with the renquant-common 0.9.1 module: every
design §1 value confirmed exactly (prod `9c4bbd74…`/`0f798015…`, shadows
`8ea3b5f6…`/`65ff1af3…` and `a5566cd9…`/`fde9a033…`, 43/43 fold bindings
hold, regime calibrators declare no scorer identity).

## What the tool does

Writes `model_content_fingerprint: <legacy 0.8.1 hash>` (versionless = the
legacy declaration per §3's version dispatch) + a provenance record nested in
`metadata` into every unstamped §3a scorer artifact. Hashes are IMPORTS ONLY
from `renquant_common.model_fingerprint` (0.9.1 deprecated shim path,
cross-checked against `_legacy_model_content_sha256`; fail-closed against the
shim's silent whole-file fallback). Stamp keys are operational under both
schemas, so neither content hash changes — only file bytes, hence the
mandated `stamp_walkforward_fingerprints.py` re-run is emitted as a follow-up
command (delegated, never re-implemented).

Inventory is enumerated at run time (never from the doc table): §3a globs +
pinned-config resolution (`strategy_config.json` / `.shadow.json`:
`artifact_path`, `global_calibration.artifact_path`, calibrator-declared
`scorer_artifact`) + manifest reachability (default scope =
`walkforward_manifest_gbdt_prod_recipe_v2*`; other manifests reported
out-of-scope, includable via `--manifest`). Calibrators are verify-only
(step-0 column of §3a): active + fold binding mismatches are RED and block
`--apply`; snapshots WARN; `.pt`-paired lanes classify FAMILY_SPLIT_NA;
regime calibrators reported outside scope (§5 row 8).

Fail-closed refusals: foreign stamp, `fingerprint_schema_version` already
present (step-2 territory), no predictive content, invalid JSON, any path
outside `--root`/inventory, `--apply` without `--grant`. Idempotent:
re-running is a byte-for-byte no-op. Dry-run default; `--apply` prints the
landing banner and requires `--grant "<note>"` recorded in provenance +
report; `.bak` per file + before/after hashes in the JSON report (run-bundle
evidence).

## Evidence

- 13 new tests green, incl. verifier-acceptance through the REAL pipeline
  code: stamped fixture passes `_assert_calibrator_matches_scorer` and the
  WF loader matchers; under pipeline origin/main + renquant-common 0.9.1
  (the converged-fleet state) the UNSTAMPED fixture FAILS the WF match and
  the v1-refit-vs-legacy-runtime daily detonation raises — both defused by
  the stamp. Byte-identity of the stamp vs the shim output asserted.
- Full orchestrator suite in the worktree: 1370 passed, 3 skipped.
- Live-tree DRY-RUN (read-only, report kept): 47 targets (1 data-prod +
  2 shadow + 1 config-resolved prod scorer + 43 folds), 0 refusals, 0 red
  bindings, active + 43/43 fold bindings MATCH, zero writes.

## Venue note (divergence from design §4 row 1 — for reviewer decision)

Design §4 row 1 places the re-stamp tool in RenQuant `scripts/` (invoke-only).
Delivered in renquant-orchestrator instead: per #210 §6 umbrella scripts
"schedule and invoke but own no selection logic", and this tool is
selection/refusal logic + provenance reporting (orchestrator-owned:
coordination/monitor/provenance), invoked BY the umbrella under grant. If
review prefers the literal §4 placement, the file moves verbatim (it has no
orchestrator-internal imports).

## Landing (NOT part of this PR — operator grant required)

Dry-run first, then apply under one grant, then the manifest-stamper
follow-ups printed by the tool, then census; all BEFORE any live venv
convergence to renquant-common 0.9.x.
