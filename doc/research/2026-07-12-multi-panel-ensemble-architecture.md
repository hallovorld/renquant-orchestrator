# Multi-Panel Ensemble Architecture: Deep Research

**Date:** 2026-07-12
**Origin:** Operator request — "我们可以搞多个板块的panel模型+大panel+ticker，
多搞出来一些，然后互相参考，我相信学术界和工业界有类似的架构！"
**Status:** Research memo (not an implementation RFC)
**Scope:** Academic/industry survey + architecture proposal for RenQuant-104
**Companion:** `2026-06-12-ensemble-primary-proposal.md` (two-model ensemble),
`2026-06-11-regime-detection-hmm-markov-switching-rfc.md` (HMM regime)

---

## 1. Bottom line

The operator's vision — sector panels + large cross-sectional panel + per-ticker
models, cross-referencing and regime-conditional — is well-grounded in recent
academic literature and mirrors (at scale) what WorldQuant/Two Sigma operate.
Five papers from 2022–2025 provide directly applicable architectures. The key
design question is not "should we do this" but "how to stage it given a
104-stock universe where per-sector sample sizes are 5–15."

Proposed architecture: **Hierarchical MoE with Regime-Conditional Gating** —
three prediction levels (per-ticker, sector-panel, cross-sectional panel) whose
outputs are combined by a learned gating network conditioned on HMM regime state
and sector membership. Staged implementation in four phases over the model
research track.

---

## 2. Academic foundations

### 2.1 MIGA — Mixture-of-Experts with Group Aggregation (2024)

**Source:** Li et al., "MIGA: Mixture-of-Experts with Group Aggregation for
Stock Market Prediction," arXiv:2410.02241 (Oct 2024).

**Architecture:**
- 63 experts organized into 7 groups of 9 experts each
- Router encodes cross-sectional stock features → Top-K (K=8) expert selection
  via softmax
- **Group Aggregation:** within each group, expert outputs are concatenated and
  processed through multi-head self-attention — experts within the same group
  share information and collaborate
- Style-based routing: stocks with similar characteristics (momentum/value/size)
  route to the same expert cluster

**Training:**
- Expert loss = IC (information coefficient) instead of MSE — directly
  optimizes ranking quality
- Router loss = load-balancing term to prevent expert collapse
- Combined: L = α·L_Router + β·L_Expert (α=2e-3, β=1)

**Results (CSI300 long-only):**
- IC=0.052, ICIR=0.265, RankIC=0.079, RankICIR=0.365
- 24% excess annual return (AR), IR=1.80
- +33% AR improvement over prior SOTA (ModernTCN: 18%)

**Relevance to us:** MIGA's "style groups" map directly to our sector panels.
The group aggregation mechanism (attention between experts in the same group) is
how sector panels would cross-reference. The Top-K routing is the gating layer.

### 2.2 PPFM — Projection-Penalized Factor Model (2025)

**Source:** Fan, Wu, Yang, "Adaptive Multi-task Learning for Multi-sector
Portfolio Optimization," arXiv:2507.16433 (Jul 2025).

**Architecture:**
- Each sector m has its own factor model: R_m = B_m · F_m + ε
- Cross-sector transfer via projection penalty:
  L = Σ(prediction errors) + (λ/T) · Σ‖P^(m) − P^(m')‖²_F
  where P = projection matrix of the factor space
- λ controls information sharing intensity: λ=0 → independent sectors;
  λ→∞ → identical factors (pooled)
- Algorithm converges within ~10 iterations

**Key insight:** The penalty is data-adaptive. Sectors that share similar latent
factors (e.g. tech and semiconductors) naturally transfer more information.
Heterogeneous sectors (e.g. utilities vs biotech) remain approximately
independent. This solves our small-sector problem: a 5-stock sector borrows
strength from related sectors without being forced into a one-size-fits-all
model.

**Results:** Superior aggregated Sharpe ratios on Russell 3000 multi-sector
portfolios vs both independent and pooled approaches.

**Relevance to us:** This is the theoretical foundation for cross-sector
regularization when training sector-specific models on a 104-stock universe. It
answers "how do you train a tech panel with only 12 stocks?" — you regularize
against the large panel's factor space.

### 2.3 AlphaMix — Uncertainty-Aware Trading Experts (2022)

**Source:** Cong et al., "Quantitative Stock Investment by Routing
Uncertainty-Aware Trading Experts: A Multi-Task Learning Approach,"
arXiv:2207.07578 (Jul 2022).

**Architecture:**
- **Stage 1:** Train multiple independent trading experts with individual
  uncertainty-aware loss functions. Each expert specializes on a subset of
  market conditions.
- **Stage 2:** Train neural routers that dynamically deploy experts on an
  as-needed basis — the router acts as a portfolio manager selecting which
  expert(s) to trust for each stock at each time step.

**Key insight:** The two-stage training prevents expert collapse — experts are
trained independently first (each develops genuine specialization), then the
router learns to select among them. This is critical: jointly trained MoE
systems often collapse to using 1–2 experts for everything.

**Relevance to us:** Our current system already has independently trained models
(XGB panel, PatchTST panel, per-ticker tournament). AlphaMix's architecture
validates treating these as pre-trained experts and learning a routing layer on
top, rather than retraining everything jointly.

### 2.4 AlphaCrafter — Multi-Agent Cross-Sectional Trading (2025)

**Source:** "AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional
Quantitative Trading," arXiv:2605.05580 (May 2025).

**Architecture (three agents):**
1. **Miner:** Continuously expands factor library, validates via IC and stability
2. **Screener:** Assesses market regime → constructs regime-conditioned factor
   ensembles with dynamic weights and directional biases
3. **Trader:** Translates ensemble into executable strategy under risk constraints

**Regime-aware ensemble:**
- Evaluates trend direction, volatility, correlation structure
- Ranks factors by regime-conditional suitability scores
- Assigns directional weights (w_f, d_f) based on regime compatibility
- "Dynamically reweights information sources without retraining"

**Results:** 18.27% AR / 1.53 Sharpe (CSI300), maintained positive returns in
live trading (2026.01–04) — most baselines went negative live despite positive
backtests.

**Relevance to us:** The Screener's regime-conditional reweighting is exactly
what our HMM regime state should do. In BULL_CALM the system trusts sector
fundamentals; in BULL_VOLATILE it emphasizes momentum; in BEAR it
de-emphasizes everything and cuts exposure. AlphaCrafter proves this approach
works live.

### 2.5 Two-Level Uncertainty for Safe Deployment (2025)

**Source:** "When Alpha Breaks: Two-Level Uncertainty for Safe Deployment of
Cross-Sectional Stock Rankers," arXiv:2603.13252 (Mar 2025).

**Architecture (two levels):**
1. **Strategy-level regime gate:** Monitors distributional shift → decides
   whether the ranking model remains reliable in current conditions. If
   regime-trust < threshold → halt trading entirely.
2. **Position-level epistemic cap:** Uses ensemble disagreement to quantify
   per-stock prediction confidence → high-uncertainty predictions receive lower
   weights or are excluded.

**Key insight:** Separation of concerns — the regime gate answers "should we
trade at all?" while the position cap answers "how much should we trust this
specific recommendation?" This prevents both system-wide degradation (regime
mismatch) and position-level overconfidence.

**Relevance to us:** This directly maps to our F4 Option A design. The regime
gate = HMM regime detection → if the primary model is known to fail in
BULL_VOLATILE, demote it in that regime. The position cap = per-stock uncertainty
from ensemble disagreement between our panel and per-ticker models.

### 2.6 Industry practice: WorldQuant / Two Sigma

**Architecture (public disclosures):**
- WorldQuant deploys ~4 million individual alpha signals. Each is an independent
  predictive rule. A separate portfolio construction team combines signals into
  models, multiple models into funds.
- Signals are evaluated against the entire deployed alpha population's
  correlation structure
- **Regime stability tests**: production signals must demonstrate consistent
  performance across multiple distinct market regimes
- Two Sigma: comparably large signal library built over 20 years; edge comes
  from combining weakly predictive signals whose errors are uncorrelated

**Relevance to us:** Our system is miniature (2–3 models vs 4M signals), but the
architectural principle is identical: no single model is reliable enough to trade
in isolation; the edge comes from ensemble + regime conditioning. The scale
difference actually simplifies our gating problem — we're routing among 3–5
experts, not millions.

---

## 3. Our current system (as-built)

| Component | Status | Strength | Weakness |
|---|---|---|---|
| XGB panel scorer | Primary (re-promoted 06-23) | Gate-passing WF stamp, tabular SOTA | Compressed mu range, no sequence modeling |
| PatchTST panel scorer | Shadow (demoted) | Distributional σ head, sequence modeling | 1 retrain, 2/3 WF cuts unexecutable |
| Per-ticker tournament | Frozen since April | Captures idiosyncratic patterns | 600s timeout → 0 candidates; stale |
| HMM regime detector | Active (3-state) | BULL_CALM/BULL_VOLATILE/BEAR | Binary-ish confidence; no per-model trust |
| Ensemble | SHELVED (06-12) | Measured IC improvement in dead windows | Never implemented; no gating |

**Critical gap:** All models see the same cross-sectional feature set with no
sector specialization. The XGB panel treats AAPL and XOM as interchangeable
feature vectors. Sector-specific dynamics (tech momentum clustering, energy
macro sensitivity, healthcare regulatory events) are lost in the
cross-sectional average.

---

## 4. Proposed architecture

### 4.1 Overview: Hierarchical MoE with Regime-Conditional Gating

```
                    ┌─────────────────────┐
                    │   Regime Router     │ ← HMM state + volatility
                    │   (gating network)  │
                    └──────┬──────────────┘
                           │ weights w_r(regime, sector)
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ Level 3    │ │ Level 2   │ │ Level 1  │
     │ Large Panel│ │ Sector    │ │ Per-Ticker│
     │ (XGB/PTST)│ │ Panels    │ │ Experts  │
     └────────────┘ └───────────┘ └──────────┘
           │              │             │
           └──────────────┼─────────────┘
                          ▼
                 ┌─────────────────┐
                 │ Position-Level  │ ← ensemble disagreement
                 │ Uncertainty Cap │
                 └────────┬────────┘
                          ▼
                    Final Score μ̂
```

**Three prediction levels:**

**Level 1 — Per-Ticker Experts:**
- Existing per-ticker tournament models (once unfrozen)
- Each ticker has its own specialized model
- Captures: idiosyncratic mean-reversion, earnings patterns, stock-specific
  momentum signatures
- Input: ticker-specific features (price history, volume, fundamentals)

**Level 2 — Sector Panel Models:**
- NEW: sector-grouped panel models (5–7 sector groups)
- Grouping by GICS sector with minimum group size = 10 stocks (merge small
  sectors: e.g., Energy+Materials, Comm.Services+Discretionary)
- Training: shared feature encoder (alpha158 base) + sector-specific prediction
  heads (per MIGA architecture)
- Cross-sector regularization via PPFM penalty (sectors with similar factor
  spaces share more information)
- Captures: within-sector relative value, sector-specific factor loadings,
  industry momentum clustering

**Level 3 — Large Cross-Sectional Panel:**
- Existing XGB and PatchTST panel scorers
- Sees all 104 stocks simultaneously
- Captures: broad cross-sectional patterns, market-wide factor premia,
  inter-sector rotation signals

### 4.2 Regime-Conditional Gating

The gating network outputs weights w = (w₁, w₂, w₃) for the three levels,
conditioned on:
- HMM regime state (one-hot: BULL_CALM, BULL_VOLATILE, BEAR)
- Regime confidence (HMM posterior probability)
- Rolling volatility and correlation features
- Sector membership of the target stock

**Regime-specific behavior (hypothesized, to be validated):**

| Regime | Large Panel | Sector Panel | Per-Ticker | Rationale |
|---|---|---|---|---|
| BULL_CALM | High | High | Low | Cross-sectional patterns stable; sector rotation active |
| BULL_VOLATILE | Medium | Low | High | Dispersion high; idiosyncratic signals dominate |
| BEAR | High (defensive) | Medium | Low | Flight-to-quality is cross-sectional; sector rotation |

### 4.3 Position-Level Uncertainty (per arXiv:2603.13252)

After the gated ensemble produces μ̂ for each stock:
- Compute ensemble disagreement = std(Level1_score, Level2_score, Level3_score)
- If disagreement > threshold → reduce position weight or exclude from buy list
- If all three levels agree → high-conviction position
- This replaces the current binary VetoWeakBuys with a continuous confidence
  measure

### 4.4 Cross-Reference Mechanism (per MIGA Group Aggregation)

Within sector groups, use attention-based cross-reference:
- Sector panel scores for all stocks in a sector are concatenated
- Multi-head self-attention produces refined scores that account for
  within-sector relationships
- Example: if AAPL scores high but MSFT/GOOGL score low in the same tech group,
  the attention mechanism can flag AAPL as an outlier (potentially contrarian
  opportunity or data anomaly)

Between levels, use residual connections:
- Level 2 (sector) receives Level 3 (large panel) scores as additional input
- Level 1 (per-ticker) receives both Level 2 and Level 3 scores
- Each level's output = its own prediction + learned residual from higher levels
- This prevents lower levels from contradicting the cross-sectional picture
  without strong evidence

---

## 5. Practical constraints and design choices

### 5.1 Sample size problem

With 104 stocks across ~11 GICS sectors, the smallest sectors (Real Estate,
Utilities, Materials) may have 3–5 stocks. Options:

| Approach | Pros | Cons |
|---|---|---|
| **A. Merge small sectors** (5–7 groups of 10–20) | Sufficient samples; simple | Loses sector granularity for merged groups |
| **B. PPFM regularization** (11 sectors, penalized) | Preserves all sectors; data-adaptive | More complex; λ tuning |
| **C. Multi-head single model** (shared encoder + sector heads) | Parameter-efficient; one training run | Sector heads may not fully specialize |
| **D. Sector embedding** (sector as a feature, not a model split) | No sample split; continuous | Not truly separate sector models |

**Recommendation:** Start with A (merged groups), graduate to C (multi-head)
after proving the concept. PPFM (B) is the eventual target for cross-sector
regularization but adds significant complexity.

Proposed grouping (merge to ~7 groups):
1. Tech + Communication Services (~25 stocks)
2. Healthcare (~15 stocks)
3. Financials (~15 stocks)
4. Consumer Discretionary (~12 stocks)
5. Industrials (~15 stocks)
6. Consumer Staples (~8 stocks)
7. Energy + Materials + Utilities + Real Estate (~14 stocks)

### 5.2 Model architecture for sector panels

Given our XGB-primary stack, sector panels should also be tree-based (not neural)
to maintain interpretability and infrastructure compatibility.

**Option: XGB with sector-specific training sets + shared hyperparameters**
- Train one XGB per sector group on the sector's stocks only
- Share hyperparameter search results across sectors (but allow per-sector
  tuning within bounds)
- Feature set: same alpha158 base, but sector panels can add sector-specific
  features (e.g., oil price for energy, yield curve for financials)
- Prediction target: same fwd_60d label
- Walk-forward validation: same 3-cut protocol per sector (smaller cuts due to
  fewer stocks)

**Concern:** XGB on 10–20 stocks × ~250 trading days × 5 years = 12,500–25,000
samples per sector. This is adequate for a shallow tree (max_depth=4–6, ~50
leaves) but not for a deep model. The PPFM regularization from §2.2 helps
here — the sector model borrows statistical strength from the full-panel model.

### 5.3 Gating implementation

**Simple gating (Phase 2):** Fixed regime-conditional weights, no learned gating.
```python
REGIME_WEIGHTS = {
    "BULL_CALM":     {"panel": 0.5, "sector": 0.3, "ticker": 0.2},
    "BULL_VOLATILE": {"panel": 0.3, "sector": 0.2, "ticker": 0.5},
    "BEAR":          {"panel": 0.6, "sector": 0.3, "ticker": 0.1},
}
```
Weights selected by HMM regime state. Validated by replaying historical regimes
and measuring ensemble IC vs component ICs.

**Learned gating (Phase 4):** A small network (2-layer MLP, ~100 params) that
maps (regime_features, sector_one_hot) → softmax weights. Trained on historical
IC data with the same walk-forward discipline as the scorers. Risk: overfitting
the gating network to regime history (only ~3 regime transitions per year on 5y
data = ~15 training points for regime weights). Mitigated by strong
regularization + leave-one-regime-out cross-validation.

### 5.4 WF gate integration

Every new model (sector panels, gating network) must pass the existing
walk-forward gate independently before serving. The ensemble output must ALSO
pass the gate — a passing component + failing ensemble = no deploy.

Sector panels have fewer stocks per WF cut → noisier gate metrics. Consider a
pooled gate (sector panels evaluated jointly) alongside per-sector gates.

---

## 6. Staging plan

### Phase 1: Unfreeze per-ticker + baseline measurement (prerequisite)
- Fix the per-ticker tournament timeout (600→3600s, already identified)
- Retrain per-ticker models on current data
- Measure: per-ticker IC vs panel IC by sector and regime
- This tells us whether per-ticker models ADD information vs the panel
- If per-ticker IC ≤ panel IC everywhere → skip Level 1, focus on Level 2
- **Dependency:** None. Can start immediately on model repo.

### Phase 2: Sector panels with fixed gating
- Train sector-grouped XGB panels (7 groups per §5.1)
- Measure: sector panel IC vs large panel IC, by sector
- Implement fixed regime-conditional weights (§5.3 simple gating)
- Validate: historical replay showing ensemble IC > best component IC
- Walk-forward gate each sector panel independently
- **Dependency:** Phase 1 measurement (to know if Level 1 adds value)
- **Deliverable:** Sector panels serving in shadow alongside primary panel

### Phase 3: Cross-reference and uncertainty
- Implement MIGA-style group aggregation within sector groups
- Add position-level uncertainty cap (ensemble disagreement)
- Replace binary VetoWeakBuys with continuous confidence measure
- Validate: does cross-reference improve IC? Does uncertainty cap reduce
  drawdowns?
- **Dependency:** Phase 2 sector panels operational

### Phase 4: Learned gating + full regime-conditional serving
- Train gating network on historical component ICs × regime states
- Implement F4 Option A: in degraded regimes, primary panel demoted to shadow,
  gating shifts weight to sector panels or per-ticker experts
- Full regime-conditional model serving as the operator envisioned
- **Dependency:** Phase 3 validated; sufficient regime transition history
- **Risk:** gating network overfitting to few regime transitions

---

## 7. Connection to F4 Option A (PR #479)

The operator's F4 request (regime-conditional model serving) is Phase 4 of this
architecture. The current #479 design was too narrow — it only considered
shadow-demoting the primary panel, but couldn't answer "demote to WHAT?" because
we had no alternative models.

This multi-panel architecture provides the answer:
- **In normal regimes:** Large panel is primary (current behavior)
- **In degraded regimes:** Gating shifts weight from large panel to sector
  panels and/or per-ticker experts that are validated in that regime
- **Fallback chain:** Large panel → sector panels → per-ticker → equal-weight
  (each level serves as fallback for the one above)

This resolves the reviewer's objection on #479 ("do not merge an amendment to
the operator freshness policy without an actual operator decision") by reframing
F4 as a consequence of the multi-panel architecture, not a standalone policy
amendment.

---

## 8. Open questions for operator

1. **Sector grouping:** The proposed 7 groups (§5.1) — acceptable? Or prefer
   GICS Level 1 (11 sectors) with PPFM regularization for small groups?

2. **Model architecture:** Sector panels as XGB (infrastructure-compatible) or
   explore neural (LSTM/Transformer) for sectors where sequence modeling matters
   (tech momentum)?

3. **Priority vs. existing work:** This is a multi-phase research program. Where
   does it sit relative to G1 (cash drag), G2 (crypto), and the two-arm
   experiment?

4. **Per-ticker tournament:** Phase 1 requires unfreezing the per-ticker
   tournament (fix timeout + retrain). Is this authorized given the model repo's
   current state?

---

## Sources

- [MIGA: Mixture-of-Experts with Group Aggregation (2024)](https://arxiv.org/abs/2410.02241)
- [Adaptive Multi-task Learning for Multi-sector Portfolio Optimization (2025)](https://arxiv.org/abs/2507.16433)
- [AlphaMix: Routing Uncertainty-Aware Trading Experts (2022)](https://arxiv.org/abs/2207.07578)
- [AlphaCrafter: Multi-Agent Cross-Sectional Trading (2025)](https://arxiv.org/abs/2605.05580)
- [When Alpha Breaks: Two-Level Uncertainty for Safe Deployment (2025)](https://arxiv.org/abs/2603.13252)
- [Multi-Layer Hybrid MTL Structure (2025)](https://arxiv.org/abs/2501.09760)
- [WorldQuant signal architecture](https://youngandcalculated.substack.com/p/how-quant-hedge-funds-actually-build)
