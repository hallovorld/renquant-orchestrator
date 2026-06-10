# E1 on the clean PatchTST signal — corrected verdict

**Date:** 2026-06-10 · **Experiment:** E1 transfer-coefficient decomposition on the placebo-clean PatchTST OOS signal (IC→Sharpe RFC §5/E1; RFC §7.1 prerequisite #1 now met).
**Status:** Strong diagnostic evidence that the current decision stack under-captures the clean IC, but not a production-decision-grade result because of the scope caveats below. Run dir `RenQuant/.../ic_to_pnl/E1_clean_longonly_v3/20260610T172113Z/` (manifest + tidy CSV committed alongside this doc).

This is a Codex follow-up to the original #67 evidence. The prior verdict overstated step 6: the replay loader's minimal snapshot allowed short exposure, so `current_qp` was measuring an invalid near-unconstrained QP path and reported Sharpe −4.19. The corrected loader is long-only (`w_lower=0`) and validates the clean-OOS manifest before it will emit E1 evidence.

## Inputs (all verified, not assumed)

- **Signal:** `pt07 strict_trainfit_embargo60 seed_44` predictions from the P0 export (renquant-model #37). **Placebo-clean OOS IC +0.0724** (median +0.094), sanity battery PASS (shuffled +0.0014, timeshift placebo @120d −0.0192 ≪ +0.0927 threshold; leak-free monotone decay). The operator's "IC ≈ 0.1" premise is corrected to +0.072; E1 runs on the real number.
- **PnL driver:** raw `fwd_1d` from `sim_runs.db::ticker_forward_returns` (real return units, no 60d overlap).
- **190 bars**, 2025-05-08 → 2026-02-10, ≥20 names/bar, 5 bp cost, `basis=replay_net_of_cost` (gross of tax).
- **Input integrity:** `--clean-oos-manifest` was required and validated. The manifest pins the expected predictions parquet, `oos_contract.passed=true`, `sanity_battery.passed=true`, the manifest SHA256, and the predictions SHA256.

## Result — the TC-decomposition ladder

Steps 0 and 1 are measurement instruments, not deployable books. They intentionally express a decile long/short ceiling and therefore record `cap_violations=190` under the long-only cap. Promotion logic must ignore them; deployable interpretation starts at step 2.

| step | book | Sharpe | TC | Δ Sharpe |
|---|---|---:|---:|---:|
| 0 | measurement A0 decile L/S, zero cost | **1.07** | 0.70 | — |
| 1 | measurement A0 + 5bp cost | 0.17 | 0.70 | −0.90 |
| 2 | A2 long-only α-tilt | **1.85** | 0.92 | +1.68 |
| 3 | + vol/dd scalar overlay | **1.87** | 0.92 | +0.02 |
| 4 | + admission floor (q=0.55) | 1.46 | 0.67 | −0.42 |
| 5 | + single-day-loss stop | 0.26 | 0.54 | −1.20 |
| 6 | current QP, minimal long-only snapshot | 0.21 | 0.48 | −0.05 vs step 5 |

## What this says about the operator's question

The clean signal is economically usable in a simple deployable book: **A2 long-only α-tilt produces Sharpe 1.85**, and the scalar overlay is TC-neutral and slightly Sharpe-positive. That supports the RFC's Stage-A/Stage-B separation: map rank to long-only weights first, then apply scalar risk control.

The corrected result no longer supports the stronger claim that "current QP turns the signal negative." It supports a sharper, more defensible claim: **the current production-style stack captures almost none of the A2 alpha in this minimal replay**. Step 6 has Sharpe 0.21, cumulative return 0.19%, max drawdown −0.59%, and mean turnover 0.0013. That is not catastrophic negative performance; it is near-non-deployment of a signal that earns Sharpe 1.85 in the direct long-only allocation.

The largest measured destroyer is the **single-day-loss stop**: step 4 → step 5 drops Sharpe 1.46 → 0.26 and TC 0.67 → 0.54. The admission floor is the second material tax: step 3 → step 4 drops Sharpe 1.87 → 1.46 and TC 0.92 → 0.67. These are the immediate redesign targets before making a broad "QP is bad" retirement claim.

One honest negative for the measurement ceiling remains: A0 decile L/S at daily 5 bp cost collapses from Sharpe 1.07 to 0.17 because daily-rebalanced decile L/S churns. This is an E2 horizon-held question, not a contradiction of A2: A2 survives cost because it is long-only and less fragile to the daily cost model.

## Caveats (scope — do not over-read)

1. **Minimal snapshot, not a production reproduction.** PatchTST has only run sell-only in production, so there is no PatchTST production decision trace to reproduce. Step 6 measures a current-QP-shaped allocation on the clean signal under a minimal long-only snapshot, not a replay of a real PatchTST production book.
2. **Single fixed holdout, not walk-forward.** The P0 export is one OOS window. Promotion still gates on WF + DSR/PBO; this is strong diagnostic evidence, not a promotion stamp.
3. **Daily rebalance.** A0/A1 ceilings need the E2 horizon-held wrapper before their absolute Sharpe is trusted. The relative ladder ordering of the deployable rungs is still informative.

## Pre-registered next actions (RFC §5.6)

- Do not retire QP from this E1 alone. Use this result to prioritize fixes: stop demotion/safety-only handling, admission-floor redesign, and a production snapshot replay.
- Promote the next experiment as **A2 long-only + scalar overlay** through E2 horizon-held and WF/step-4g with DSR/PBO before any production-path change.
- Re-run the corrected E1 after renquant-pipeline #73 lands on `main`, so the manifest can pin the merged commit rather than the review branch commit.

Reproduction:
```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a
RENQUANT_REPO_ROOT=$PWD PYTHONPATH=/Users/renhao/git/github/renquant-pipeline/src \
  .venv/bin/python -m renquant_pipeline.kernel.portfolio_qp.patchtst_replay_loader \
  --predictions <renquant-model>/artifacts/diagnostics/oos_ic/hf_patchtst_all_seed44_model_20260610T165959Z/predictions.parquet \
  --clean-oos-manifest <renquant-model>/doc/evidence/2026-06-10-pt07-clean-oos-ic/manifest.json \
  --sim-db data/sim_runs.db --fwd-horizon-days 1 \
  --out-dir backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E1_clean_longonly_v3
```

Agent-Origin: Codex
