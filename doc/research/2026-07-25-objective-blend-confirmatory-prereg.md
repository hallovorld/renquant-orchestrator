# Prereg — CONFIRMATORY: tail-aware blend objective vs production rank:pairwise

Date: 2026-07-25
Status: PREREGISTRATION — decision rule frozen at this commit, BEFORE the run.
Script: `scripts/research_objective_blend_confirm.py`
Screen provenance: 2026-07-24 six-arm objective A/B (memo §9 / scratchpad
`objective_ab_result.json`) — all three cross-sectional tail-aware arms beat
the production objective by +21–28% on the harvest statistic (each ns alone);
the absolute-threshold arm failed. This is the single pre-named confirmatory
test that screen earns. No other arm may be promoted from that screen.

## Hypothesis (one, named, frozen)

**H:** `blend` — per-date z(rank:pairwise@fwd_60d) + z(top-decile-membership
classifier@fwd_60d) — produces a higher clean top-10 spread than the
production `rank:pairwise` objective, same features, folds, embargo.

Mechanism (stated before data, carried from the 07-24 memo): the book
harvests top-10 only and the alpha is tail-carried; rank:pairwise spends
its loss budget ordering the ~90% of the cross-section the book never
trades. The classifier aims the loss at tail membership; the rank leg
preserves stability. The screen's asymmetry (relative-tail arms positive,
absolute-threshold arm negative) matches the mechanism's prediction.

## Design

| element | value |
|---|---|
| arms | `blend` vs `rank60` baseline; each with its own matched within-date shuffled-label placebo |
| seeds | **10** (42–51) — screen CI width was seed-noise-dominated at 3 |
| folds / embargo | the same 5 purged walk-forward folds, 60d embargo |
| statistic | per-date paired difference of clean top-10 spread (arm − its placebo), blend − rank60 |
| inference | moving-block bootstrap, block 60, B=10,000, seed 20260725, 90% CI |
| guards | (a) seed stability: ≥8/10 seeds positive mean diff; (b) winsorized-±50% diff must be ≥ 0 (rejects lottery-only artifact) |

## Decision rule — FROZEN

- **CONFIRMED**: CI lower bound > 0 AND both guards pass → next step is a
  SHADOW deployment proposal (separate design PR; wires the blend scorer
  through the existing shadow-scorer infra; forward clean-spread telemetry
  is the decisive evidence; NO production config change from this result).
- **REFUTED**: point estimate ≤ 0 → record NULL in the memo; the
  objective-mismatch line closes; no re-pitch without new mechanism.
- **INCONCLUSIVE**: CI spans 0 with positive point estimate → the corpus
  verdict is "at resolution limit"; the decision moves to shadow-forward
  evidence with a reduced burden (pre-committed: shadow slot is justified
  by mechanism + consistent screen family + this run's direction, and the
  shadow readout rule is defined in the follow-up design PR, not here).

## Boundaries

Survivorship panel (levels inflated; paired diffs robust). One model
family. Historical corpus resolution ≈ ±0.05–0.07 on this statistic —
INCONCLUSIVE is the likely outcome and is planned for, not an escape hatch.
