# B1+B2 landed: WF-loader ×3 and model_content_sha256 ×4 unified onto the M6 dispatch

DATE: 2026-07-04
CAMPAIGN: compliance fix campaign (PR #297) Group B rows B1+B2. Findings:
RQ#444 F-2/F-10, #295 P0-2, #296 BT-1 — the stamp-mismatch incident
generator (2026-05-27 / 06-22 / 07-01 fail-closed no-trade class).

## What landed (coordinated PRs, merge order)

1. **renquant-backtesting `fix/wf-loader-unify`** (merge FIRST — no
   cross-PR dependency, but it is the reviewed reference for the umbrella
   port): the forked `WalkForwardModelLoader` becomes a subclass of the
   pipeline loader; only the backtesting URI-resolution layer stays local;
   verification is IMPORTS ONLY from
   `renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch`.
   ARCHITECTURE DECISION: import the pipeline dispatch directly; do NOT
   lift it to renquant-common mid-window (window machinery is
   pipeline-owned per #210 §6; revisit at M6 stage-2 step 5 when the
   dispatch collapses to `verify()`).
2. **umbrella RenQuant `fix/wf-gate-loader-repoint`** (merge SECOND): the
   LIVE gate leg (`kernel/walk_forward/loader.py` behind `run_wf_gate.py` +
   `adapters/sim.py`) drops its local matcher for the same dispatch
   (fail-loud pinned-pipeline resolution; #421 digest binding preserved);
   `fit_calibrator_alpha158_fund.py` + `stamp_walkforward_fingerprints.py`
   move off the umbrella kernel's stale `model_content_sha256` copy onto
   stamped-value precedence + the explicit `renquant_common` legacy engine.
3. **this PR** (docs, merge with/after): amends the M6 stage-2 §2a
   inventory (new §2a-bis) — site-6 correction (stale local copy, not the
   pipeline re-export) + the two previously-missing loader legs.

## Protection-contract evidence (read-only, real inventory, 2026-07-04)

- fingerprint census baseline: GREEN — 47/47 legacy-stamped, 69 bindings,
  0 red.
- WF loader legs (umbrella AND backtesting), 2 in-scope manifests × 43
  folds, real `_assert_calibrator_matches_entry` with the pinned runtime
  pipeline: old vs new verdicts IDENTICAL (43 PASS / 43 NO_CALIBRATOR
  each), identity lists identical.
- `_artifact_fingerprint` / `_scorer_identity`: 47/47 identical values old
  vs new.
- 12-char-prefix reliance: MEASURED ZERO among green matches → the prefix
  acceptance was NOT dropped outright; it lives only inside the dispatch's
  legacy route behind `accept_legacy_stamps` (default ON) and retires at
  stage-2 step 4 — matching the design's §5 row 6 schedule.
- Suites A/B vs pristine mains: identical failure sets (pre-existing
  environmental only); +8 pins (backtesting) / +13 pins (umbrella).

## Deploy

No venv/pin prerequisite: the live `.subrepo_runtime/repos/renquant-pipeline`
already carries the dispatch (verified read-only 2026-07-04), and the
umbrella `kernel.walk_forward` package already imported `renquant_pipeline`.
Normal pin-advance flow applies; nothing enablement-gated.
