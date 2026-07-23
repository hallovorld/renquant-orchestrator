# 2026-07-23 — tiered_screen: generic power-first existence/increment primitive   (PR #568)

STATUS:    delivered
WHAT:      Adds `src/renquant_orchestrator/tiered_screen/` — a generic,
           model-family-agnostic power/MDE calculator (`power.py`) plus a
           tiered existence/increment evaluation harness (`harness.py`) that
           composes existing `expkit` primitives (per-date IC, shifted-label
           placebo, paired deltas, gap-respecting block bootstrap). No
           statistics reimplemented. Carries no experiment-specific policy
           (no expert names, no fixed alpha, no frozen spec) — every public
           entrypoint requires the caller to pass its own `alpha_one_sided`
           explicitly (no default), and 12 tests pin the power-law arithmetic
           and the harness controls (positive/negative control, no
           false-positive on a null score, paired increment fires only on
           real dominance).
WHY/DIR:   PR #568 originally shipped this as a GOAL-4 (XGB+PatchTST
           ensemble)-specific frozen prereg living in this repo. Codex review
           (2026-07-23) correctly flagged that as a repo-placement BLOCKER:
           per `RENQUANT_REPOS.md`, model-family research/evaluation design
           (concrete experts, frozen spec, evidence) belongs in
           `renquant-model` beside the score producers, not in the
           orchestrator, which only consumes models by `artifact_path`. Two
           review rounds also found the G4-specific kill-gate logic
           internally inconsistent (Tier-1 claimed to evaluate both experts
           while the PatchTST corpus stays gated behind an undefined "60d
           lead") and the progress doc's power-analysis claim did not match
           its own arithmetic once the Bonferroni-corrected alpha was
           applied. Rather than carry a broken G4-specific design into
           `renquant-model` as-is, this PR is narrowed to exactly what Codex
           said may stay here: the genuinely generic primitive, with zero
           XGB/PatchTST/G4 policy. The G4-specific frozen spec, design doc,
           and evidence are dropped from this PR entirely; a correctly
           specified version belongs beside the score producers in
           `renquant-model` as separate future work.
EVIDENCE:
  artifact:      src/renquant_orchestrator/tiered_screen/power.py,
                 src/renquant_orchestrator/tiered_screen/harness.py,
                 tests/test_tiered_screen.py
  prod or exp:   experiment (generic library code — pure functions over
                 caller-supplied score/close/bench frames; no production
                 path touched, no live model score, no experiment-specific
                 claim)
  existing data: n/a — no model/data performance claim is made by this PR;
                 correctness is pinned against textbook one-sided z-values
                 (`z_.95 + z_.80 = 2.486475`) and synthetic-panel control
                 behavior only.
  best-known?:   n/a — not a model result.
  scope:         "this is generic library code (power.py MDE calculator +
                 harness.py tiered evaluation), unit-tested against textbook
                 one-sided z-values and synthetic-panel controls in
                 tests/test_tiered_screen.py. It makes NO model-family or
                 live-performance claim; any concrete experiment (which
                 experts, which horizons, which frozen alpha) is left
                 entirely to the caller's own pre-registered spec."
  `[VERIFIED — pytest tests/test_tiered_screen.py -q, 2026-07-23, 12/12 passed]`
NEXT:      A correctly-specified GOAL-4 frozen prereg (concrete XGB/PatchTST
           hypotheses, kill-gate decision tree, evidence) is future work in
           `renquant-model`, beside the score producers and the Phase-A
           converter, composing this primitive rather than duplicating it.

## What changed from the original PR
- Renamed `g4_ensemble/` → `tiered_screen/`; dropped `spec.py` (the frozen
  G4 `FrozenSpec` with XGB/PatchTST hypotheses) and
  `doc/research/2026-07-23-g4-ensemble-prereg.md` +
  `doc/research/evidence/2026-07-23-g4-ensemble/frozen_spec.json` (the
  G4-specific design doc + frozen evidence).
- `harness.py`'s three public entrypoints (`evaluate_existence`,
  `evaluate_increment`, `positive_control_recovery`) now require
  `alpha_one_sided` explicitly — no default — so a caller cannot silently
  run at a looser alpha than their own spec froze (the alpha-mismatch MED
  finding from review). `test_public_entrypoints_require_explicit_alpha`
  pins this.
- Removed all GOAL-4/XGB/PatchTST references from docstrings; the module
  now documents itself as a generic tiered existence/increment primitive.

## Reuse discipline
No statistics reimplemented — `expkit` (#287, codex-reviewed) already ships
IC / placebo / paired-delta / block-bootstrap. Only the power/MDE calculator
was genuinely new; kept as a sibling module, not folded into `expkit`'s
already-narrowed surface (2026-07-04 narrowing, PR #287 round 2) absent
concrete duplication evidence for it.

## Review
Not self-merged; Codex review is the merge gate.
