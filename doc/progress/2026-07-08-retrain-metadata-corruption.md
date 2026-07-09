# Per-ticker retrain metadata corruption — live fix

**Date**: 2026-07-08
**Severity**: P0 (silent universe collapse, affects 104 + 105)
**Status**: Live-fixed; prevention tracked at hallovorld/RenQuant#453 (owning repo, not this one)

## Root cause

The weekly per-ticker retrain (`train_104 --skip-panel`) ran on 2026-07-06 and:

1. Overwrote all 230 `*-policy-metadata.json` files (trained_date → 2026-06-30)
2. Changed `policy_type` for many tickers (e.g. BLK: `manual` → `xgboost`)
3. **Did NOT write the corresponding model weight files** (e.g. `BLK-xgb-buy.json`)
4. `load_artifact()` checks metadata-declared files → not found → returns `None`
5. `LoadArtifactsTask` rejects the ticker → candidate universe collapses

## Impact

| Metric | Before retrain (07-02) | After retrain (07-06) | After fix (07-08) |
|--------|------------------------|----------------------|-------------------|
| `load_artifact` OK | 83/142 (58%) | 65/142 (46%) | 133/142 (94%) |
| `no_artifact` rejected | 3 | 77 | 9 (ETFs, no model dir) |
| batch_scores coverage | 83 tickers | 35 tickers | expected ~83+ |

- 104 daily pipeline saw universe shrink 83 → 33 candidates
- 105 batch scores (fed to intraday session) only covered 35/145 tickers
- 105 intraday decisions: 112/145 tickers blocked by `missing_panel_score`

## Fix applied

```bash
# Restored all model files to committed (pre-retrain) state
git checkout HEAD -- backtesting/renquant_104/models/
```

Safe: only restores metadata + weight files to committed versions.
Applied at 10:23 PT, 3.5h before daily_104 (13:55 PT).

## Breakdown of 77 failing tickers (post-retrain, pre-fix)

| Failure mode | Count | Example |
|-------------|-------|---------|
| `xgb_missing_model` | 21 | BLK (manual→xgboost, no xgb-buy/sell.json) |
| `qlearning_missing` | 19 | FTNT (no qtable/bin-edges) |
| `classification_no_rf` | 17 | ABBV (no rf-trees.json) |
| `manual_no_rules` | 11 | GOOG (no manual-rules.json) |
| `no_dir` | 9 | SPY, XLI, XLY (ETFs, expected) |

## Prevention needed (owned by RenQuant, not this repo)

**This document is an orchestrator-side incident record only.** The retrain
workflow, its atomic-write fix, and any regression test for it belong to
`RenQuant` (umbrella/backtesting model artifacts), not to
`renquant-orchestrator`. Tracked at hallovorld/RenQuant#453.

The retrain script must be atomic: do not update `policy-metadata.json` unless
the corresponding weight files are successfully written. Currently metadata is
written first, and if weight-file generation fails/skips, the metadata declares
artifacts that don't exist. This PR/doc does not fix that — hallovorld/RenQuant#453 does.

Note: per-ticker models are LEGACY (panel scorer is the production scorer).
`LoadArtifactsTask` gates admission on these legacy artifacts — a structural
coupling that should eventually be removed for panel-only strategies.
