# Stamp calibrator fingerprint after refit

**Date:** 2026-07-06
**PR:** (this PR)

## Problem

The weekly retrain pipeline (`retrain_alpha158_fund.py`) calls
`fit_calibrator_alpha158_fund` to refit the calibrator, but the resulting
artifact has `model_content_sha256: null`.  The runtime's
`fingerprint_dispatch.verify()` then crashes with
`calibrator/scorer fingerprint mismatch` on the next daily-full run.

This is root-cause #3 of the "triple-impl fingerprint bug" (memory
2026-07-01): three independent hash implementations compute different values,
and the calibrator path doesn't compute one at all.

Every manual promote since June has required a manual re-stamp of the
calibrator hash.  This fix automates the stamp.

## Fix

- New `StampCalibratorFingerprintTask` runs immediately after
  `RefitCalibratorTask` in the `RetrainJob` pipeline.
- Reads the scorer artifact, computes `model_content_sha256` via the canonical
  `renquant_pipeline.fingerprint_dispatch` (fallback: `renquant_common`), and
  writes the hash into the calibrator JSON.
- Logic extracted into `_stamp_calibrator_fingerprint()` for testability.

## Tests

- `test_stamp_calibrator_fingerprint_writes_scorer_hash` — unit test for the
  stamp function (monkeypatched hash).
- Updated `test_pipeline_shape_is_single_job_with_ordered_tasks` — new task in
  expected task list.
- Updated `test_retrain_pipeline_command_sequence` and
  `test_pipeline_isolates_sigma_head_failure_from_ranker_retrain` —
  monkeypatched stamp to avoid needing a real scorer payload.

## Risk

Low.  The stamp is append-only (adds one key to calibrator JSON).  If the hash
function import fails, the task raises and blocks promote — fail-closed, same
as today's manual crash but earlier in the pipeline.
