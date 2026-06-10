# E2 holding-horizon sweep on the clean PatchTST signal - post-#76 verdict

**Date:** 2026-06-10.
**Experiment:** E2, the IC-to-Sharpe RFC section 5 holding-horizon sweep on the clean PatchTST signal.
**Status:** Strong diagnostic evidence, not production-decision-grade evidence. This rerun supersedes the closed pre-#76 evidence PR because that run mixed E1/E2 metadata and used the pre-#76 held-universe semantics.

Run directory:
`RenQuant/backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E2_clean_post76/20260610T214248Z/`

The committed manifest pins:

- `renquant-pipeline`: `440cc02a8e68b49ac074ce431a45574456e85f7c` (post-#76 writer + held-universe fix)
- `renquant-model`: `19919ec9350fdcb6931dfb2de4a10c3c90d1393a`
- predictions SHA256: `sha256:d74fc52d1bf91101edcfd09ecc362300b31448c43bd9045366e0145024813109`

## Why This Replaces PR #72

PR #72 was closed instead of patched because its evidence had a broken chain of custody:

- the E2 CSV rows were labeled `E1`;
- `manifest.json` said top-level `experiment: E1`;
- `manifest.outputs` referenced `e1_results.csv` while the committed file was `e2_results.csv`;
- the pipeline pin predated #75 and #76, even though the verdict depended on the E2 wrapper behavior.

This rerun fixes those issues in one regenerated evidence bundle. The manifest says `experiment: E2`, the committed file is `e2_results.csv`, CSV rows are labeled `E2`, and the manifest output hash includes `e2_results.csv`.

## Result

Clean PatchTST signal, 190 bars, 1-day realized PnL, 5 bps cost, A0 decile long/short measurement book held for each horizon:

| hold bars | Sharpe | TC | mean turnover | cumulative return |
|---:|---:|---:|---:|---:|
| 1 | 0.09 | 0.70 | 1.0834 | 0.25% |
| 5 | 0.52 | 0.54 | 0.2457 | 4.55% |
| 20 | -0.47 | 0.39 | 0.0685 | -4.45% |
| 40 | -0.84 | 0.29 | 0.0341 | -6.11% |
| 60 | -2.34 | 0.25 | 0.0269 | -15.90% |

The broad conclusion survives the post-#76 rerun but the exact numbers changed slightly from the pre-#76 bundle. A0 peaks around a short hold, not at the 60-day label horizon. The 60-day label IC does not imply a 60-day holding period; the held book's transfer coefficient decays materially as it drifts from the live cross-section.

## Interpretation

This answers the narrow A0-cost question: daily A0 is cost-shredded, short-horizon A0 is better, and long-horizon A0 becomes poor. It does not overturn E1's deployable conclusion. A0 is a dollar-neutral measurement instrument with intentional `w_lower` violations; A2 long-only remains the deployable direction from E1.

The production experiment should therefore not freeze a 60-day rebalance cadence simply because the model label is 60-day. The next production-grade measurement should sweep A2 long-only plus scalar overlay horizons, or use a cost-aware glide, then let WF plus step-4g replay choose the cadence with DSR/PBO.

## Caveats

1. This is a minimal replay snapshot, not a production decision-trace reproduction.
2. This is one fixed holdout, not walk-forward evidence.
3. A0 is a measurement instrument, not a deployable long-only book.
4. The manifest fingerprints the full generated run directory, including raw per-step trace files. The committed evidence surface here follows the existing E1 pattern: manifest, tidy CSV, and verdict.

Reproduction:

```bash
cd /Users/renhao/git/github/RenQuant
set -a && source .env && set +a
RENQUANT_REPO_ROOT=/Users/renhao/git/github/RenQuant \
PYTHONPATH=/Users/renhao/git/github/renquant-pipeline/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python \
  -m renquant_pipeline.kernel.portfolio_qp.patchtst_replay_loader \
  --experiment e2 \
  --predictions /Users/renhao/git/github/renquant-model/artifacts/diagnostics/oos_ic/hf_patchtst_all_seed44_model_20260610T193556Z/predictions.parquet \
  --clean-oos-manifest /Users/renhao/git/github/renquant-model/doc/evidence/2026-06-10-pt07-clean-oos-ic/manifest.json \
  --sim-db /Users/renhao/git/github/RenQuant/data/sim_runs.db \
  --horizons 1 5 20 40 60 \
  --out-dir /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E2_clean_post76 \
  --repo-pin renquant-pipeline=/Users/renhao/git/github/renquant-pipeline \
  --repo-pin renquant-model=/Users/renhao/git/github/renquant-model
```

Agent-Origin: Codex
