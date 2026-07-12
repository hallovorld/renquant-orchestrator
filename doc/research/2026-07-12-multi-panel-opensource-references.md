# Multi-Panel Ensemble Architecture: Open-Source References

**Date:** 2026-07-12
**Context:** Operator requested open-source framework and literature references for
the multi-panel ensemble architecture designed in
`renquant-model/doc/research/2026-07-12-multi-panel-ensemble-architecture.md`
(model PR #45, merged).

---

## Papers cited in the design memo

None of the five papers released public code.

| Paper | Year | arXiv | Key Idea | Code Status |
|---|---|---|---|---|
| MIGA — Mixture-of-Experts with Group Aggregation | 2024 | [2410.02241](https://arxiv.org/abs/2410.02241) | 63 style-group experts + group attention; IC=0.052, 24% AR on CSI300 | No public repo |
| AlphaMix — Uncertainty-Aware Trading Experts | 2022 | [2207.07578](https://arxiv.org/abs/2207.07578) | Two-stage MoE: train experts independently, then learn routing | Unofficial fork only ([johnson7788/AlphaMix](https://github.com/johnson7788/AlphaMix)) — partial, Chinese-language |
| PPFM — Projection-Penalized Factor Model | 2025 | [2507.16433](https://arxiv.org/abs/2507.16433) | Cross-sector factor transfer via penalized PCA; solves small-sector sample size | No public repo (very recent) |
| AlphaCrafter — Multi-Agent Cross-Sectional Trading | 2025 | [2605.05580](https://arxiv.org/abs/2605.05580) | Regime-conditional factor ensemble reweighting; 18.27% AR, positive live Q1 2026 | No public repo |
| Two-Level Uncertainty for Safe Deployment | 2025 | [2603.13252](https://arxiv.org/abs/2603.13252) | Strategy-level regime gate + position-level epistemic cap | No public repo |

## Open-source frameworks with runnable code

### MarketRegimeNet — closest architectural analog

- **Repo:** [lu8848/MarketRegimeNet](https://github.com/lu8848/MarketRegimeNet)
- **Stars:** Small (research project)
- **Architecture:** 4-model ensemble (2x Transformer + LSTM-GRU + LightGBM),
  regime-aware gating, Kelly sizing, walk-forward cross-validation
- **Features:** Uses Alpha158 features (same as our system)
- **Relevance:** The regime-conditional multi-model ensemble pattern is directly
  applicable to our Phase 2 (fixed regime weights) implementation. The walk-forward
  CV harness is a reference for our nested WF protocol design.
- **Limitation:** Small-scale research project, not production-grade infrastructure.

### Microsoft Qlib — production-grade quant ML infrastructure

- **Repo:** [microsoft/qlib](https://github.com/microsoft/qlib)
- **Stars:** ~17,000+
- **Architecture:** Full quant ML pipeline — data, features, training, backtest,
  portfolio construction. Has DoubleEnsemble, multi-model benchmarks
  (LightGBM/LSTM/GRU/GATs/SFM/TFT).
- **Features:** Alpha158 feature set (we already use this), walk-forward evaluation
  framework, standardized model benchmarking.
- **Relevance:** Infrastructure reference for WF harness and feature engineering.
  No built-in sector-panel or MoE module, but the data pipeline and evaluation
  framework are production-grade.
- **Limitation:** No sector-panel, no regime-conditional gating, no MoE routing.

### Microsoft RD-Agent — automated quant R&D

- **Repo:** [microsoft/RD-Agent](https://github.com/microsoft/rd-agent)
- **Stars:** Active development
- **Architecture:** Multi-agent automated factor discovery + model co-optimization.
  NeurIPS 2025. Reports ~2x returns vs Alpha158 baseline with 70% fewer factors.
- **Relevance:** Not MoE-specific, but relevant as automated experiment
  infrastructure. Could inform how we automate Phase 1-3 experiment sweeps.
- **Limitation:** LLM-agent-driven, different paradigm from our manual experiment
  protocol.

### FinRL — reinforcement learning for finance

- **Repo:** [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL)
- **Stars:** ~10,000+
- **Architecture:** RL-focused, has ensemble DRL agents combining PPO/A2C/DDPG.
- **Relevance:** Low — RL paradigm is different from our supervised learning +
  regime gating approach. Listed for completeness.
- **Limitation:** No MoE, no sector-panel, no walk-forward gate integration.

## Assessment

**For our Phase 2 experiment implementation:**

1. **MarketRegimeNet** is the primary reference — its regime-aware multi-model
   ensemble with walk-forward is structurally closest to what we're building.
   Worth reading its gating logic and WF harness code before writing ours.
2. **Qlib** is the infrastructure reference — its Alpha158 features (which we
   share), DoubleEnsemble pattern, and evaluation framework inform our nested
   WF protocol design.
3. All five papers' architectures must be implemented from scratch using their
   published descriptions, since no code is available.
4. The AlphaMix unofficial fork may have partial training code worth examining
   for the two-stage MoE pattern (train experts independently, then learn
   routing), but quality is uncertain.
