# Backfill 2019-2023 walk-forward window artifacts (served-model experiment corpus)

This directory holds **82 recipe-consistent walk-forward fold artifacts** covering
cutoffs **2019-01-14 .. 2023-09-11** (one `<cutoff>/panel-ltr.json` per fold). It is the
2019-2023 extension of the served-model architecture experiment window (orch#799 decider,
`doc/design/2026-08-12-served-model-architecture-experiment-prereg.md` §3), committed here
as **durable, independently-reviewable** evidence so the window/power claims can be verified
without the scratch tree.

## Provenance

- **Regenerated**: 2026-08-02, `jobb-gbdt-depth-extension` run
  (`run001`); the artifacts are verbatim copies of that run's `window_artifacts/`.
- **Recipe (prod recipe v2, identical to the 43-fold prod WF manifest)**:
  - 172 `alpha158_fund` features (`feature_cols`; byte-identical across all folds)
  - label `fwd_60d_excess`, `lookahead_days=60`, `cutoff_embargo_days=60`
  - GBDT params `objective=rank:pairwise, eta=0.05, max_depth=5, min_child_weight=50,
    subsample=0.7, colsample_bytree=0.7, seed=42` — **`max_depth=5` in EVERY fold**; the
    run's "depth-extension" name means *time-depth* (longer history), NOT tree depth.
- **NOT a production/live path.** This is a one-time RESEARCH corpus under `doc/research/`;
  it is never read by the daily run, the WF gate, or any live/serving surface.

## What certifies these

The per-fold recipe fingerprints (`feature_cols_sha256`, `params_sha256`,
`config_fingerprint`), regime labels, and the recipe-consistency assertion for the full
125-fold window (these 82 backfill folds + the 43 prod-manifest folds) live in the sibling
`../fold_manifest.json`. The regime labels are recomputable from SPY daily OHLCV via
`RenQuant/kernel/hmm_regime_labels.py`. See that manifest for the common shas and the
BEAR-coverage counts.
