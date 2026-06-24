# 2026-06-24 — Fundamentals/macro ablation experiment plan

STATUS: plan only, for review before execution (not run yet).

WHAT: `doc/research/2026-06-24-fundamentals-macro-ablation-plan.md` — a
falsifiable ablation plan to test whether the panel-LTR scorer gains from its
non-technical features (fundamentals / sentiment / PEAD-SUE) or is ~entirely an
alpha158 technical model. Variants A (full 172) vs B (alpha158-only, 159) vs C
(+fund) vs D (leave-one-group-out), through the per-regime placebo WF gate, ≥5
seeds, decision on placebo-clean IC DIFFERENCES.

WHY-DIR: operator asked whether fundamentals + macro are meaningful to the model
and to plan an experiment. Verified macro is NOT in the scorer (regime-only);
fundamentals are 5/172 (~8% gain) and were stale+corrupt without changing picks
— plausibly dead weight, but unproven.

EVIDENCE:
- `[VERIFIED]` live artifact feature_cols = 159 alpha158 + 5 fund + 3 sentiment
  + 5 PEAD/SUE; 0 macro in the scorer.
- `[DESIGN]` harness is the same per-regime placebo WF gate validated in
  #171/#176/#177; honest power caveat documented (can reject, weak-null).

NEXT: on approval, run the 6 variants × 5 seeds on the post-backfill regime
dataset; report placebo-clean differences only. Strategic payoff: if
fundamentals don't earn IC, retire the (bug-prone) fundamentals pipeline.
