# 2026-07-12 — Multi-panel ensemble architecture: deep research

## Bottom line

Comprehensive research memo surveying 5 academic papers (2022–2025) and
industry practice (WorldQuant/Two Sigma) that validate and inform the
operator's multi-panel ensemble vision: sector panel models + large
cross-sectional panel + per-ticker experts, cross-referencing via
regime-conditional gating.

## What this PR contains

- `doc/research/2026-07-12-multi-panel-ensemble-architecture.md` — the
  research memo: academic survey (MIGA, PPFM, AlphaMix, AlphaCrafter,
  Two-Level Uncertainty), current system assessment, proposed Hierarchical
  MoE architecture with 3 prediction levels and regime-conditional gating,
  practical constraints (104-stock universe, sector sample sizes), and a
  4-phase staging plan.
- This progress note.

## Key findings

1. **MIGA (2024):** 63 style-based experts in 7 groups with group
   aggregation (attention). IC=0.052, +24% excess return on CSI300. Maps
   to our sector panels + cross-reference.
2. **PPFM (2025):** Cross-sector factor transfer via projection-penalized
   PCA. Solves the small-sector sample problem — a 5-stock sector borrows
   strength from related sectors adaptively.
3. **AlphaMix (2022):** Two-stage MoE — train experts independently, then
   learn routing. Validates using our pre-trained models (XGB, PatchTST,
   per-ticker) as experts with a learned gating layer.
4. **AlphaCrafter (2025):** Regime-conditional factor ensemble reweighting.
   18.27% AR / 1.53 Sharpe, maintained positive live returns (2026 Q1).
5. **Two-Level Uncertainty (2025):** Strategy-level regime gate + position-
   level epistemic cap. Directly maps to F4 Option A.

## Connection to PR #479

F4 Option A (regime-conditional model serving) is Phase 4 of the proposed
multi-panel architecture. The narrow #479 design could not answer "demote
to WHAT?" — this research provides the answer (sector panels + per-ticker
experts as fallback chain). #479 should reference this memo.

## Verification

- Research-only: no code, config, or behavioral change. `[VERIFIED]`
- All paper citations checked against source URLs. `[VERIFIED]`
