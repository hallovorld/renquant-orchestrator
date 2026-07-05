# D1 verdict assessment — gate works, model fails

DATE: 2026-07-04

## What

Extracted D1 WF-gate verdict from the existing production model metadata.
S1-S3 gate code confirmed ALL MERGED in backtesting (PRs #48-#64).

## Finding

D1 = FAIL, but the blocker is the MODEL not the gate:
- BULL_CALM genuine IC = 0.017 (< 0.02 bar), ~78% of trading time
- CHOPPY genuine IC = 0.002 (signal ≈ placebo)
- BEAR genuine IC = 0.247 (strong, but rare regime)
- S3 overall genuine IC = 0.0415 (PASS as shadow)

## Impact

Gate engineering is complete. D1 clearance requires a model retrain that
demonstrates genuine predictive power in BULL_CALM. This is a research/model
problem, not an infrastructure problem.
