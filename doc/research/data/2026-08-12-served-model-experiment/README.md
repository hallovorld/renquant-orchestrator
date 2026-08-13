# served-model architecture experiment — window definition (digest-only)

This directory holds the **frozen window definition** for the orch#799 served-model
experiment (`doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`).

- **`fold_manifest.json`** — the 125-fold walk-forward window (2019-01-14 .. 2026-03-02):
  per-fold `cutoff`, recipe fingerprints (`feature_cols_sha256`, `params_sha256`,
  `config_fingerprint`), `n_features`, `label_col`, and the regime label
  (`regime_label` / `is_bear`, recomputable from SPY via
  `kernel/hmm_regime_labels.py`). Top-level: `recipe_consistent:true`, `n_folds:125`,
  `n_bear_folds:15`, `n_bear_episodes:8`.

**No raw fold artifacts are committed here.** WF fold artifacts belong in
`renquant-backtesting` (their generator's repo), not in the orchestrator. This manifest
is a **reference-by-digest** anchor: recipe identity is pinned by the common
`feature_cols_sha256` + `params_sha256` (identical across all 125 folds). The raw
2019-2023 backfill folds (from the 2026-08-02 `jobb-gbdt-depth-extension` run) are
**materialized + committed to `renquant-backtesting` at execution** and byte-verified
against these recipe digests then — see the prereg §8.

The manifest does NOT byte-pin individual artifacts (no per-file content digest);
recipe-identity is the design-time freeze, byte-materialization is the execution step.
