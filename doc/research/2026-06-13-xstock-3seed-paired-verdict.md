# Cross-Stock Attention: 3-Seed Paired Verdict (#106-2.1)

Status: EXPERIMENT VERDICT (epic branch — experiments never merge to main).
Date: 2026-06-13. Owner: claude. Decision requested from: operator.
Protocol: #106 model roadmap §"cross-stock as highest-variance structural
lead" + #109-errata DSR/PBO discipline (paired per-seed deltas, no
mean-only claims; the WF gate, not IC, remains the sole promotion
authority).

## Setup

Identical strict_trainfit recipe (cut=all, val_tail_pct=0.10,
embargo_days=60, fwd_60d_excess, seq_len 24, d_model 64, 2 layers,
lr 1e-4, wd 0.3) ± `--cross-stock-attn`, seeds {44, 45, 46}, same
dataset `transformer_v4_wl200_clean.parquet`, same machine/env.
Metric = `eval_min_regime_ic` (the production selection metric; CHOPPY
is the binding regime in all six runs).

Artifacts: `artifacts/patchtst_shadow/{prod_recipe,xstock_strict_trainfit}_seed{44,45,46}/`
(summaries carry full training contracts). One operational note: the
seed-45/46 cross-stock runs survived a chain crash + a brief
double-training race (killed; single clean process finished each run).

## Results

| seed | prod (baseline) | cross-stock | paired Δ |
|---|---|---|---|
| 44 | 0.0307 | 0.0522 | **+0.0215** |
| 45 | 0.0258 | 0.0270 | +0.0012 |
| 46 | **−0.0015** | 0.0237 | **+0.0252** |
| mean | 0.0183 | 0.0343 | **+0.0160** |

Paired statistics (n=3): mean Δ = +0.0160, sd(Δ) = 0.0129,
paired t = 2.14 (df 2), one-sided p ≈ 0.083; sign test 3/3 positive,
p = 0.125. Per-regime: cross-stock improves the binding CHOPPY IC in
all three seeds and never degrades BEAR/BULL_VOLATILE.

## Honest reading

1. **The effect survived the de-winnering test it was given.** After
   seed 45 (Δ ≈ 0) the seed-44 result looked like luck; seed 46 restored
   a consistent picture: **3/3 positive paired deltas**.
2. **Not statistically conclusive at n=3** (p ≈ 0.08–0.13). Under the
   #109 DSR/PBO discipline this does NOT clear a promotion bar by
   itself — and was never going to: IC deltas are evidence FOR running
   the gate, not a substitute for it.
3. **The variance story may matter more than the mean.** The baseline
   produced a dead seed (46: −0.0015 — a coin-flip model); cross-stock
   produced none (min 0.0237). If replicated, "fewer failed trainings"
   is operationally more valuable than +1.6 IC pts: it derisks every
   future retrain (relevant to the 576-day staleness retrain now queued).
4. Caveats: same dataset/val-year for all runs (panel ESS ≈ 5,901 —
   these six numbers share most of their information); MPS
   nondeterminism means seed alone does not pin the trajectory; metric
   is val-tail IC, not gate-grade walk-forward evidence.

## Decision options (operator)

- **A (recommended): run the real gate now.** Take the cross-stock
  candidate through `run_wf_gate.py` (3-cut + §5.2 sanity battery +
  trade-monotonicity). ~1 GPU-day. The gate is the promotion authority;
  with 3/3 positive deltas the experiment has earned a gate run, and
  gate evidence supersedes anything more we'd learn from seeds 47/48.
  If it passes, promotion flows through the normal alias-moving
  `promote()` path; if it fails, we shelve with the verdict attached.
- **B: two more seed pairs first** (47/48, ~10 GPU-h) → n=5 paired
  (sign test 5/5 would reach p = 0.031). Buys statistical comfort,
  delays gate evidence, and the retrain-on-fresh-data action item (the
  P-MODEL-STALENESS warning) arguably outranks it on the same GPU.
- **C: fold into the staleness retrain.** The queued fresh-data retrain
  must happen regardless; train it ± cross-stock (2 runs) and gate the
  better one — combines the decisions and answers "does the edge hold
  on fresh data", at the cost of conflating two changes.

GPU is idle as of this note. Awaiting operator pick (A/B/C) before any
further training is queued.
