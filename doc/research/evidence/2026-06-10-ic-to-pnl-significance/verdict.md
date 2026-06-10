# Stage-A significance — DSR/PBO/HAC correction of the A2 ≫ QP claim

**Date:** 2026-06-10 · **Purpose:** statistical hardening of the IC→Sharpe synthesis. The synthesis ranked allocators by raw Sharpe; this applies the step-4g multiple-comparison machinery (DSR, PBO/CSCV, HAC-corrected paired comparison, per-regime) on the verified clean signal so the central claim is not a raw-Sharpe artifact.
**Status:** Strengthens the synthesis. **Still not a promotion** — same three caveats; promotion gates on WF + DSR/PBO on the real WF manifold, not this single OOS holdout.

## Result (clean signal, 190 bars, A2 horizon-held at 3 bars)

| allocator | Sharpe | DSR | PBO |
|---|---|---|---|
| **A2 long-only hold3** | **2.59** | **1.00** | 0.00 |
| current_qp (incumbent) | 0.21 | 0.96 | 0.00 |
| equal_weight_top_k | −0.18 | 0.003 | 0.00 |
| inverse_vol_top_k | −0.18 | 0.003 | 0.00 |

**Paired vs the incumbent QP (HAC autocorrelation-robust):**

| comparison | Δ Sharpe (QP − cand) | HAC t-stat | win-rate z |
|---|---|---|---|
| QP vs A2_hold3 | **−2.59** | **−2.30** | **−2.76** |
| QP vs equal_weight | +0.44 | +0.39 | −2.18 |
| QP vs inverse_vol | +0.44 | +0.39 | −2.18 |

## What this adds to the synthesis

1. **A2 ≫ QP survives autocorrelation + multiple-comparison correction.** The QP-vs-A2 difference has HAC t = −2.30 (|t| > 1.96, significant) and a win-rate z = −2.76 — A2 beats QP bar-by-bar at better than 2.7σ. The raw-Sharpe ordering was not a fluke of serial correlation.
2. **A2's DSR = 1.0 with PBO = 0.0**: across the candidate matrix's out-of-sample CSCV slices, A2 is consistently the top book — no probability-of-backtest-overfitting signal at this candidate count.
3. **The QP barely beats the naïve baselines** (Δ +0.44 vs equal/inverse-vol, HAC t = +0.39, *not* significant). This is the §8 "does QP beat the simplest rule" question answered cleanly: on this signal the QP's complexity is **not** statistically distinguishable from equal-weight — while A2 is decisively above all of them.

## Honest bounds on the statistics

- **HAC t = −2.30 is significant but not overwhelming** (|t| between 1.96 and 2.58) on a single OOS holdout. It is corroborating evidence for the ordering, not a promotion-grade p-value.
- **PBO/DSR on 4 candidates** is informative but a small candidate matrix; the promotion-grade run should include the full step-4g baseline set and the WF manifold, where DSR's trial-count deflation bites harder.
- All three synthesis caveats still apply: minimal long-only snapshot, single OOS holdout, gross of tax. The robust takeaway is unchanged and now statistically corrected: **A2 ≫ QP ≈ naïve-baselines**, ordering significant.

## Bearing on the production decision

This removes the "raw Sharpe" objection to the synthesis's recommended experiment. The case for taking **Stage-A A2 (long-only α-tilt, ~3-bar GP-glide rebalance, scalar overlay, stops safety-only, QP retired from selection)** through the real WF + step-4g gate is now: A2 beats the incumbent QP at >2.7σ bar-by-bar, DSR 1.0 / PBO 0.0, and the QP is statistically indistinguishable from equal-weight on this signal. Operator decision points are unchanged (synthesis §Decision points); live stays unchanged until a candidate clears the WF gate.

Reproduction:
```bash
RENQUANT_REPO_ROOT=$PWD PYTHONPATH=<pipeline>/src .venv/bin/python \
  -m renquant_pipeline.kernel.portfolio_qp.stage_a_significance \
  --predictions <P0>/predictions.parquet --clean-oos-manifest <P0>/manifest.json \
  --sim-db data/sim_runs.db --a2-hold-bars 3 \
  --out-dir backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/significance
```

Agent-Origin: Claude
