# 2026-07-12 — Multi-panel ensemble: open-source framework references

## Bottom line

Surveyed open-source implementations for the 5 papers cited in the multi-panel
ensemble architecture design (model PR #45). None released code. Two frameworks
are directly useful: MarketRegimeNet (regime-aware multi-model ensemble, closest
architectural analog) and Qlib (production-grade quant ML infra we already share
Alpha158 features with). All experiment code must be written from scratch.

## What this PR contains

- `doc/research/2026-07-12-multi-panel-opensource-references.md` — structured
  reference index: 5 papers (arXiv links, code status), 4 open-source frameworks
  (repo URLs, stars, architecture, relevance assessment), and implementation
  guidance for Phase 2 experiments.

## Key findings

1. Zero papers released code — implementation is from published descriptions only
2. MarketRegimeNet = primary code reference for regime-conditional gating + WF
3. Qlib = infrastructure reference for nested WF harness + Alpha158 features
4. AlphaMix has an unofficial fork worth examining for two-stage MoE pattern

## Verification

- Research-only: no code, config, or behavioral change. `[VERIFIED]`
- All repo URLs verified via web search. `[VERIFIED]`
