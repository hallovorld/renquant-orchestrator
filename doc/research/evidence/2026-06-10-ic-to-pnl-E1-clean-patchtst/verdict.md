# E1 on the clean PatchTST signal — verdict

**Date:** 2026-06-10 · **Experiment:** E1 transfer-coefficient decomposition on the placebo-clean PatchTST OOS signal (IC→Sharpe RFC §5/E1; RFC §7.1 prerequisite #1 now met).
**Status:** Strong directional evidence on the question "does the decision tree waste the IC", but not a production-decision-grade result because of the three scope caveats in §Caveats. Run dir `RenQuant/.../ic_to_pnl/E1_clean/20260610T170952Z/` (manifest + tidy CSV committed alongside this doc).

## Inputs (all verified, not assumed)

- **Signal:** `pt07 strict_trainfit_embargo60 seed_44` predictions from the P0 export (renquant-model #37). **Placebo-clean OOS IC +0.0724** (median +0.094), sanity battery PASS (shuffled +0.0014, timeshift placebo @120d −0.0192 ≪ +0.0927 threshold; leak-free monotone decay). The operator's "IC ≈ 0.1" premise is **corrected to +0.072** — E1 runs on the real number.
- **PnL driver:** raw `fwd_1d` from `sim_runs.db::ticker_forward_returns` (real return units, no 60d overlap).
- **190 bars**, 2025-05-08 → 2026-02-10, ≥20 names/bar, 5 bp cost, `basis=replay_net_of_cost` (gross of tax).

## Result — the TC-decomposition ladder

Step 0 is a measurement ceiling, not a deployable book. The committed CSV records
`cap_violations=1` on both A0 rows, so treat the 1.07 Sharpe as an upper-bound
measurement benchmark rather than a feasible production target.

| step | book | Sharpe | TC | Δ Sharpe |
|---|---|---|---|---|
| 0 | A0 decile L/S, zero cost | **1.07** | 0.70 | — (the IC ceiling) |
| 1 | A0 + 5bp cost | 0.17 | 0.70 | **−0.90** |
| 2 | A2 long-only α-tilt | **1.85** | 0.92 | +1.68 |
| 3 | + vol/dd scalar overlay | 1.87 | 0.92 | +0.02 |
| 4 | + admission floor (q=0.55) | 1.46 | 0.67 | **−0.41** |
| 5 | + single-day-loss stop | 0.26 | 0.54 | **−1.20** |
| 6 | current QP allocator | **−4.19** | 0.80 | **−4.45** |

## What this says about the operator's question

**"The decision tree wastes the IC" is strongly supported — and under this measurement setup it is worse than waste.** The clean signal's deployable ceiling (A2 long-only) is a respectable **Sharpe 1.85**, but the measured step-5/step-6 path drives it to **−4.19**. The ladder localises where the value dies:

1. **The single-day-loss stop is the largest single-step destroyer in the additive ladder (1.46 → 0.26, −1.20 Sharpe; TC 0.67 → 0.54).** This is the quantitative form of the live +3.6pp post-exit-regret finding and the RFC §2.2 hypothesis: a daily path-dependent stop on a 60-day-horizon thesis is pure whipsaw in a calm-bull window (Han-Zhou-Zhu: stops help in momentum-crash states, not this one).
2. **The current QP turns the signal negative (−4.19).** Under the minimal-snapshot measurement setup, this is strong directional evidence that the optimizer's complexity is not paying for itself on this signal. It is not, by itself, enough to claim the live PatchTST production path would realize the same magnitude because §Caveat 1 explicitly says this is not a production decision-trace reproduction.
3. **A2 long-only α-tilt (1.85) beats every more-complex rung.** The RFC's central thesis — a direct monotone map from rank to weight, held, with only a scalar risk overlay — is the best deployable book in this experiment. Stage A is not just cleaner; it is higher-Sharpe.
4. **The admission floor costs 0.41 Sharpe and 0.25 TC** — the second-largest destroyer, consistent with E3's independent finding that it collapses effective breadth 2.44 → 1.58 bets.
5. **H-B holds (step 2→3): the scalar overlay is TC-neutral (0.92 → 0.92) and slightly Sharpe-positive.** Risk control done as a scalar does not tax the signal — vindicating the Stage-A/Stage-B separation.

**One honest negative for the Stage-A ceiling:** A0 decile L/S at realistic cost collapses to 0.17 (step 0→1, −0.90) because daily-rebalanced decile L/S churns. This is the E2 horizon-held question (PR #69): the ceiling must be re-measured held-at-horizon before A0 is read as "the IC is only worth Sharpe 1." A2 long-only's low turnover is why it survives cost; A0's does not, daily-rebalanced.

## Caveats (scope — do not over-read)

1. **Minimal snapshot, not a production reproduction.** PatchTST has only ever run sell-only, so there is no PatchTST production decision-trace to reproduce. Step 6 measures QP-on-the-clean-signal under a near-unconstrained snapshot; the −4.19 is QP's own behaviour on this signal, not a replay of a real PatchTST production book.
2. **Single fixed holdout, not walk-forward.** The P0 export is one OOS window (the PatchTST WF-gate path is still broken, renquant-backtesting follow-up). Promotion still gates on WF + DSR/PBO; this is a strong directional result, not a promotion stamp.
3. **Daily rebalance.** A0/A1 ceilings need the E2 horizon-held wrapper before their absolute Sharpe is trusted; the *relative* ladder ordering (which gate destroys most) is robust to this.

## Pre-registered next actions (RFC §5.6)

- Treat this run as the directional input to the §5.6 "A0 strong" branch, not the final trigger by itself: replace the gates only after the horizon-held rerun and WF gate confirm the same ranking.
- Re-run E1 + E2 horizon-held on the clean signal to settle the A0-cost question.
- The stop layer and the QP allocator are the two ranked redesign targets. Recommended next experiment: A2 long-only + scalar overlay, stops demoted to safety-only, through the WF gate + step-4g replay for a DSR/PBO-clean promotion decision before any production-path retirement claim.

Reproduction:
```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a
RENQUANT_REPO_ROOT=$PWD PYTHONPATH=/Users/renhao/git/github/renquant-pipeline/src \
  .venv/bin/python -m renquant_pipeline.kernel.portfolio_qp.patchtst_replay_loader \
  --predictions <renquant-model>/artifacts/diagnostics/oos_ic/hf_patchtst_all_seed44_model_20260610T165959Z/predictions.parquet \
  --sim-db data/sim_runs.db --fwd-horizon-days 1 \
  --out-dir backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E1_clean
```

Agent-Origin: Claude
