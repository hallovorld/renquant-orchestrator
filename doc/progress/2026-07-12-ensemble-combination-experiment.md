# 2026-07-12 — Ensemble combination experiment design

## Bottom line

Design doc for multi-model score combination: staged L1→L4 ladder (equal-weight
→ inverse-variance → linear stacking → regime-conditional static weights).
Explicitly excludes sector panels, learned gating, and hard routing (per-ticker
model selection), with literature justification. Each level has a pre-registered
go/no-go gate.

## What this PR contains

- `doc/design/2026-07-12-ensemble-combination-experiment.md` — full experiment
  design: problem statement, literature evidence against hard routing (§2),
  4-level combination ladder (§3), nested WF protocol (§4), prerequisites and
  phasing (§5), explicit exclusions with rationale (§6), relationship to prior
  design PR #45 (§7), 15+ references (§8).

## Key design choices

1. Soft combination (weighted average), not hard routing (per-ticker model
   selection) — 50+ years of forecast combination literature
2. Staged ladder with pre-registered go/no-go at each level
3. Linear-only meta-model (no neural/tree stacking) — QuantBench 2025
4. Regime weights by grid search on inner folds, not learned gating
5. Sector panels excluded at 104-stock scale (insufficient sample)
6. Supersedes combination method from model PR #45; retains model-building
   vision and experiment protocol

## Verification

- Design-only: no code, config, or behavioral change. `[VERIFIED]`
- All literature citations checked against source. `[VERIFIED]`
