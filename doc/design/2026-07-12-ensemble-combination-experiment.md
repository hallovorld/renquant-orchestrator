# Ensemble Combination Experiment Design

**Date:** 2026-07-12
**Status:** DESIGN — awaiting operator review. Do not implement until approved.
**Owner:** Orchestrator (experiment harness + evaluation); Model (scorer
training); Pipeline (WF gate integration).
**Scope:** How to combine existing and new models into a single trading signal.
This document decides the combination METHOD, not the models themselves.

---

## 1. Problem statement

We have (or will have) multiple models that each score the same 104-stock
universe:

| Model | Status | Type |
|---|---|---|
| XGB panel scorer | Primary (live) | Cross-sectional panel |
| PatchTST panel scorer | Shadow (demoted) | Cross-sectional panel |
| Per-ticker tournament | Frozen since April (timeout) | Per-ticker |
| Sector panel models | Not built | Sector-grouped panel |

The question is: **how should we combine their scores into a single
buy/sell/hold signal?**

The operator's initial vision was **hard routing** — for each ticker, pick the
one model with the best backtest and only listen to that model. This document
explains why that approach is statistically fragile, presents the
literature-backed alternative (soft combination), and defines the experiment
plan to validate it.

---

## 2. Why hard routing (model selection) fails

### 2.1 The operator's proposed approach

> "每个 ticker 都有一个对应的最适合的模型。A 的 ticker 模型一直很好，今天
> ticker 说买 A 那我们就买 A。半导体模型认为 mu 该买，且 mu 最好的模型是
> 半导体，那就买 MU。"

This is **hard routing**: for each ticker, select the single best-performing
model based on backtest data, and route that ticker's decisions exclusively
through that model.

### 2.2 Why it doesn't work (literature evidence)

Hard routing is a well-studied failure mode in forecast combination. The core
problem: **selecting the "best" model on backtest data selects for noise, not
signal.**

**Winner's curse (selection bias):** With K models and N tickers, you run K×N
comparisons. For each ticker, the model with the highest backtest IC is
disproportionately likely to have benefited from favorable noise rather than
genuine predictive superiority. With 5 models × 104 tickers = 520 comparisons,
the false discovery rate is severe.

Numerical example: suppose 5 models all have true IC = 0.03 for ticker AAPL,
but backtest noise produces observed ICs of {0.00, 0.02, 0.03, 0.04, 0.08}.
Hard routing selects the 0.08 model. Out of sample, it reverts to 0.03 — the
same as every other model. The "selection" captured noise, not edge.

**Non-stationarity:** The best model for a ticker changes over time. AAPL may
be best predicted by a sector panel during semiconductor cycle phases (2024)
and by the overall panel during macro-driven phases (2025). Hard routing to one
model based on historical performance cannot adapt to this.

**Insufficient statistical power:** To reliably distinguish model A from model
B for a single ticker requires far more out-of-sample data than we have.
5 years × 250 days = 1,250 observations per ticker. Distinguishing IC = 0.04
from IC = 0.03 at 95% confidence requires ~2,500+ observations (power
analysis; the difference is 0.01 in a noisy signal). We cannot reliably select
per-ticker.

### 2.3 Literature consensus

The forecast combination literature (50+ years, hundreds of studies)
consistently finds:

> "Combination dominates selection in virtually all contexts."
> — Timmermann (2006), "Forecast Combinations"

> "Equal weights are surprisingly hard to beat out of sample."
> — Genre et al. (2013), Forecast Combination 50-Year Review

Key papers:

| Paper | Year | Finding |
|---|---|---|
| Smith & Wallis | 2009 | Selection amplifies estimation error; combination averages it out. The mathematical explanation for why simple averaging beats sophisticated selection. |
| Timmermann | 2006 | Systematic review: combination > selection across macroeconomic forecasting, financial returns, volatility, density forecasts. |
| Claeskens, Magnus, Vitale & Zenber | 2016 | Model selection's OOS performance is systematically lower than model averaging because selection variance is underestimated. |
| Gu, Kelly & Xiu | 2020 | 30,000 US equities: ensemble average of tree + neural network models outperforms any single best model. IR 0.4–0.6 vs 0.35. The foundational empirical asset pricing paper. |
| Forecast Combinations 50-Year Review | 2022 | arXiv:2205.04216. Equal weights "surprisingly hard to beat" across 50 years of evidence, especially in small-sample / non-stationary settings — exactly our regime. |
| MoE Comprehensive Survey | 2025 | arXiv:2503.07137. Documents MoE failure modes: expert collapse (>99% representation similarity), load imbalance, gating overfitting. |

### 2.4 Hard routing vs soft combination — side by side

| Dimension | Hard routing (select one) | Soft combination (weighted average) |
|---|---|---|
| Error handling | One model wrong → fully exposed | One model wrong → diluted by others |
| Noise sensitivity | Selects the noisiest backtest winner | Averages out noise across models |
| Adaptability | Locked to historical winner | Weights can shift (L2+) |
| OOS degradation | Systematic (winner's curse) | Minimal (errors cancel) |
| Statistical requirement | High (must distinguish per ticker) | Low (just needs models to be somewhat uncorrelated) |
| Literature support | Dominated in virtually all contexts | 50+ years of evidence |

---

## 3. Design: staged soft combination

### 3.1 Maturity ladder

The experiment follows a strict ladder. Each level is tested against the
previous level. Advancing requires statistically significant OOS improvement
measured on held-out data never seen during any model training, weight
selection, or hyperparameter tuning.

```
L1: Equal-weight average
 ↓ beats frozen champion?
L2: Inverse-variance weighted
 ↓ beats L1?
L3: Linear stacking (meta-model)
 ↓ beats L2?
L4: Regime-conditional static weights
 ↓ beats L3?
STOP (no learned gating, no attention, no neural routing)
```

Levels beyond L4 are explicitly excluded from this experiment program:

| Excluded | Why |
|---|---|
| L5: Sector panels | 104 stocks / 7 groups = 8–25 per group; insufficient sample for per-sector models. Revisit only if universe expands to 300+. |
| L6: Learned MoE gating | ~15 regime transitions in 5 years = insufficient training data for a gating network; documented expert collapse risk. |
| L7: Hierarchical MoE + attention | Zero production evidence at any scale. |

### 3.2 Level 1 — Equal-weight average

**What:** For each ticker on each date, compute:

```
μ_ensemble = (1/K) × Σ μ_k
```

where μ_k is the score from model k. All available models contribute equally.

**Models included:** Start with XGB panel + PatchTST panel (the two we have
today). Add per-ticker tournament scores when unfrozen (Phase 1 prerequisite:
timeout fix 600→3600s, already verified to produce 0→114 candidates).

**Why start here:** Equal-weight is the strongest baseline in the forecast
combination literature. If it doesn't beat the frozen champion (XGB alone),
no fancier combination method will either — we save all downstream work.

**Implementation:** A scoring combination script that reads existing model
outputs (XGB panel scores + PatchTST panel scores from the daily inference
pipeline) and computes the simple average. No new model training. Estimated
effort: 1–2 days.

**Evaluation:** Nested walk-forward (§4) comparing ensemble vs frozen champion
(XGB alone) on IC, RankIC, net-of-cost simulated return, and Sharpe ratio.

### 3.3 Level 2 — Inverse-variance weighted

**What:** Weight each model by the inverse of its recent forecast error
variance:

```
w_k = (1 / σ²_k) / Σ (1 / σ²_j)
μ_ensemble = Σ w_k × μ_k
```

where σ²_k is model k's rolling forecast error variance over the trailing
window (e.g., 60 trading days). Models that have been more accurate recently
get higher weight.

**Why:** Standard portfolio theory applied to forecasts. A model going through
a bad patch (high error variance) is automatically down-weighted without any
explicit regime detection.

**Implementation:** Same combination script, plus a rolling variance
computation on each model's residuals. Estimated effort: 0.5 days incremental
on top of L1.

**Evaluation:** Same nested WF as L1, additionally comparing L2 vs L1.

**Advance criterion:** L2 must beat L1 (equal-weight) OOS. If it doesn't, the
literature predicts this is likely — equal-weight is hard to beat — and we
deploy L1 instead.

### 3.4 Level 3 — Linear stacking

**What:** Train a linear regression meta-model:

```
μ_ensemble = β₀ + β₁·μ_XGB + β₂·μ_PatchTST + β₃·μ_ticker + ε
```

The meta-model learns the optimal linear combination of base model scores.
Critically: **linear only** — no trees, no neural networks, no interaction
terms. This is deliberate. A linear meta-model has minimal capacity to overfit
to the inner-fold data, which is the dominant risk at this sample size.

**Why linear, not nonlinear:** QuantBench 2025 (industrial benchmark) reports
that production quant systems deliberately use linear regression as meta-model
specifically to avoid overfitting. At our scale (104 stocks, 5 years, 3–5 base
models), a nonlinear meta-model has more capacity than the signal supports.

**Implementation:** Requires the nested walk-forward harness (§4) — the
meta-model's coefficients must be fit on inner folds only, never touching
outer-fold test data. Estimated effort: 2–3 days (most of which is the harness,
reusable for L4).

**Evaluation:** Same nested WF, additionally comparing L3 vs L2 and L1.

**Advance criterion:** L3 must beat L2 OOS. If it doesn't, deploy L2 (or L1).

### 3.5 Level 4 — Regime-conditional static weights

**What:** A fixed weight table indexed by HMM regime state:

```python
REGIME_WEIGHTS = {
    "BULL_CALM":     {"xgb": 0.45, "patchtst": 0.35, "ticker": 0.20},
    "BULL_VOLATILE": {"xgb": 0.30, "patchtst": 0.20, "ticker": 0.50},
    "BEAR":          {"xgb": 0.50, "patchtst": 0.35, "ticker": 0.15},
}
```

The weight values above are illustrative. The actual values are selected by
grid search on inner-fold data (§4.2) with a coarse grid (weights in 0.05
increments, summing to 1.0). The grid is small enough (~200 combinations per
regime × 3 regimes) that exhaustive search is feasible without optimization
algorithms.

**Why static, not learned:** ~3 regime transitions per year × 5 years = ~15
training points for regime-conditional behavior. A learned gating network
would have far more parameters than training points. A fixed table with
grid-searched values on inner folds is the most that this data can support.

**Literature support:** RegimeFolio (2024, arXiv:2510.14986) validated this
exact pattern — regime-aware sector-specific ensemble with static weights —
on 34 US large-cap stocks (comparable scale to our 104) and achieved
Sharpe 1.17, +20% forecast accuracy vs regime-agnostic combination.

**Implementation:** Extends the L3 harness with regime-state indexing.
Estimated effort: 2–3 days incremental.

**Evaluation:** Same nested WF, additionally comparing L4 vs L3.

**Advance criterion:** L4 must beat L3 OOS. If it doesn't, deploy L3 (or
whichever level won).

---

## 4. Experiment protocol

### 4.1 Nested walk-forward

The standard single-model WF split (train → embargo → test) is insufficient
when a combination layer sits on top of base models. The combination layer's
weight selection is a **second fitting step** that can leak outer-fold
information if naively cross-validated.

```
Outer fold (never touched during any fitting):
  ├── Outer-train window
  │     ├── Inner-train: base model training + combination weight fitting
  │     ├── Inner-embargo: gap (same convention as existing WF gate)
  │     └── Inner-test: combination weight validation / selection
  ├── Outer-embargo: gap
  └── Outer-test: FINAL evaluation (H1 comparison only)
```

**Critical discipline:** The combination weights (L2 variance window, L3
coefficients, L4 regime-weight table) are fit/selected using ONLY inner-fold
data. The outer-test window is touched exactly once, for the final comparison.
No iteration, no "let me try different weights and see which works on the
outer fold."

### 4.2 Leakage controls

| Leakage vector | Control |
|---|---|
| Base model sees outer-test data | Standard WF embargo (existing convention) |
| Combination weights see outer-test data | Nested inner/outer split (§4.1) |
| Weight selection grid-searched on outer data | Grid search on inner-test ONLY |
| Regime labels leak future | HMM regime state is computed using data strictly before the prediction date (online/causal HMM, no smoothing) |
| Multiple comparisons (L1 vs L2 vs L3 vs L4) | Bonferroni correction on the final comparison; the primary hypothesis is "best level beats frozen champion," not "which level is best" |

### 4.3 Evaluation metrics

All metrics computed on outer-test windows only:

| Metric | Definition | Purpose |
|---|---|---|
| IC | Pearson correlation between predicted μ and realized fwd_60d return | Ranking accuracy |
| RankIC | Spearman rank correlation | Robust ranking accuracy |
| ICIR | IC / std(IC) across outer windows | Stability of ranking accuracy |
| Net return | Simulated portfolio return after transaction costs (existing sim infrastructure) | Economic value |
| Sharpe ratio | Annualized net return / annualized volatility | Risk-adjusted return |
| Turnover | Monthly portfolio turnover rate | Cost of implementation |

### 4.4 Advance criteria (pre-registered)

Each level comparison uses the outer-test windows. The primary test:

- **H0:** The candidate level's mean IC ≤ the comparison level's mean IC
  (one-sided).
- **H1:** The candidate level's mean IC > the comparison level's mean IC.
- **Test:** Paired t-test on per-window IC differences (each outer window is one
  observation), with Bonferroni correction for the number of comparisons (3:
  L1 vs champion, best-L vs L1, best-L vs champion).
- **Significance level:** α = 0.05 after Bonferroni correction (i.e.,
  per-comparison α = 0.05/3 ≈ 0.017).
- **Minimum effect size:** ΔIC ≥ 0.005 (below this, the improvement is not
  economically meaningful given our transaction cost regime).

A level that beats its predecessor with p < 0.017 AND ΔIC ≥ 0.005 advances.
Otherwise, deploy the previous level.

---

## 5. What we need before running experiments

### 5.1 Prerequisites

| Prerequisite | Status | Blocking? |
|---|---|---|
| XGB panel scorer producing daily scores | Live (primary) | No |
| PatchTST panel scorer producing daily scores | Shadow (demoted, but scoring) | No — scores exist |
| Per-ticker tournament unfrozen | Blocked on timeout fix (600→3600s verified) | Blocks L3/L4 (not L1/L2) |
| Nested WF harness | Not built | Blocks L3/L4 |
| Existing sim/backtest infrastructure | Available | No |

### 5.2 Experiment phases

| Phase | Scope | Prerequisites | Est. effort | Deliverable |
|---|---|---|---|---|
| **Phase A** | L1 (equal-weight XGB+PatchTST) vs frozen champion | XGB + PatchTST scores | 1–2 days | IC/return comparison; go/no-go for ensemble |
| **Phase B** | L2 (inverse-variance) vs L1 | Phase A code | 0.5 days | Incremental comparison |
| **Phase C** | Unfreeze per-ticker tournament | Timeout fix deployed | 1 day | 114+ candidates producing scores |
| **Phase D** | L3 (linear stacking, 3 models) + L4 (regime weights) | Nested WF harness + Phase C | 3–5 days | Full ladder comparison |

### 5.3 Go/no-go decision tree

```
Phase A: L1 vs champion
  ├── L1 loses → ensemble does not help at this scale. STOP.
  │              Deploy champion alone. Do not build more models for
  │              combination purposes.
  └── L1 wins  → Phase B: L2 vs L1
                    ├── L2 loses → deploy L1 (equal-weight)
                    └── L2 wins  → Phase C+D: unfreeze per-ticker, build
                                   harness, test L3/L4
                                     ├── L3 loses L2 → deploy L2
                                     └── L3 wins → test L4
                                                     ├── L4 loses → deploy L3
                                                     └── L4 wins  → deploy L4
```

At every node, the decision is binary and pre-registered. No "let's try one
more thing" after a negative result.

---

## 6. What this design explicitly does NOT include

| Excluded | Rationale |
|---|---|
| Sector panel models | Insufficient sample (8–25 stocks per group). Revisit if universe grows to 300+. |
| Learned gating network | ~15 regime transitions in training data; documented expert collapse risk. |
| Attention-based cross-reference | Zero production evidence. |
| Hard routing (per-ticker model selection) | Dominated by soft combination in 50+ years of literature (§2). |
| Nonlinear meta-model | Overfitting risk at our scale; production systems deliberately use linear (QuantBench 2025). |

These exclusions are **not permanent** — they are scoped to this experiment
program. If the universe expands, if more data accumulates, or if a specific
paper demonstrates transferability to our setting, any of these can be
reopened with a new design doc and its own pre-registered hypothesis.

---

## 7. Relationship to prior design (model PR #45)

The multi-panel ensemble architecture memo (model PR #45, merged) proposed a
more ambitious 4-phase program including sector panels, cross-reference
attention, and learned gating. This document **supersedes the combination
method** in that design:

| PR #45 proposed | This document |
|---|---|
| Sector panels (Phase 2) | Excluded — insufficient sample at 104 stocks |
| Fixed regime weights (Phase 2) | Kept as L4, but sequenced AFTER proving L1–L3 first |
| Cross-reference attention (Phase 3) | Excluded — zero production evidence |
| Learned gating (Phase 4, contingent) | Excluded — insufficient regime transitions for training |

The model-building vision (per-ticker experts, multiple panel scorers) from
PR #45 remains valid — the change is in how their outputs are combined.
PR #45's experiment protocol (nested WF, leakage controls, pre-registered
metrics) is adopted here with minor refinements.

---

## 8. References

### Primary (combination method)

| Ref | Paper | Year | Key finding |
|---|---|---|---|
| [T06] | Timmermann, "Forecast Combinations" | 2006 | Combination dominates selection across virtually all contexts |
| [SW09] | Smith & Wallis, "A Simple Explanation of the Forecast Combination Puzzle" | 2009 | Selection amplifies estimation error; combination averages it out |
| [FC22] | Wang et al., "Forecast Combinations: An Over 50-Year Review" | 2022 | arXiv:2205.04216. Equal weights surprisingly hard to beat OOS |
| [GKX20] | Gu, Kelly & Xiu, "Empirical Asset Pricing via Machine Learning" | 2020 | RFS. Ensemble average > any single best model on 30k equities |
| [C16] | Claeskens et al., "The Forecast Combination Puzzle" | 2016 | Model selection OOS systematically worse than model averaging |

### Supporting (architecture and failure modes)

| Ref | Paper | Year | Key finding |
|---|---|---|---|
| [RF24] | RegimeFolio, "Regime Aware Sectoral Portfolio Optimization" | 2024 | arXiv:2510.14986. Regime+sector ensemble, Sharpe 1.17, 34 US large-caps |
| [QB25] | QuantBench, "Benchmarking AI for Quant Investment" | 2025 | arXiv:2504.18600. Production systems use linear meta-model deliberately |
| [MoE25] | MoE Comprehensive Survey | 2025 | arXiv:2503.07137. Expert collapse, representational collapse, load imbalance |
| [AF24] | AlphaForge, "Mine and Dynamically Combine Formulaic Alphas" | 2024 | AAAI 2025. Dynamic temporal weighting > fixed weights |
| [CFA25] | CFA Institute, "Ensemble Learning in Investment" | 2025 | Industry-standard recognition of ensemble ML in practice |

### Open-source references

| Framework | Repo | Relevance |
|---|---|---|
| MarketRegimeNet | github.com/lu8848/MarketRegimeNet | Closest runnable analog: 4-model regime-aware ensemble + WF + Alpha158 |
| Qlib | github.com/microsoft/qlib | Production-grade quant ML infra; DoubleEnsemble, Alpha158 |
| RD-Agent | github.com/microsoft/rd-agent | Automated factor+model co-optimization (NeurIPS 2025) |

### Papers from prior design (model PR #45, combination method superseded)

| Ref | Paper | Year | Status in this design |
|---|---|---|---|
| MIGA | arXiv:2410.02241 | 2024 | Excluded (learned MoE, CSI300 only, no code) |
| AlphaMix | arXiv:2207.07578 | 2022 | Excluded (two-stage MoE, no official code) |
| PPFM | arXiv:2507.16433 | 2025 | Excluded (cross-sector transfer, insufficient sample at 104) |
| AlphaCrafter | arXiv:2605.05580 | 2025 | Excluded (LLM-agent-based, different paradigm) |
| Two-Level Uncertainty | arXiv:2603.13252 | 2025 | Position-level uncertainty cap concept retained as optional future add-on if L1–L4 demonstrates ensemble disagreement is informative |
