# 2026-07-23 — GOAL-4 ensemble: power-first prereg + tiered harness   (PR #568)

STATUS:    delivered
WHAT:      Freezes a pre-registered, power-first, tiered experiment design
           (Tier 0 harness validation / Tier 1 existence screen / Tier 2 paired
           increment / Tier 3 reserved forward test) for the GOAL-4 XGB+PatchTST
           two-expert ensemble question, plus the power/MDE calculator and
           harness that compose existing `expkit` prereg primitives. No
           statistics reimplemented, no real scorer wiring, no Modal spend.
WHY/DIR:   Corrects a prior attempt that fired a $32 Modal walk-forward run to
           read a 60d-horizon IC that this design's own power analysis shows is
           structurally under-powered. The frozen spec + Tier-1 kill gate is
           the process fix so future G4 compute is spent only where the
           measurement can actually detect the effect.
EVIDENCE:
  artifact:      src/renquant_orchestrator/g4_ensemble/power.py,
                 tests/test_g4_ensemble.py::test_min_detectable_ic_matches_closed_form,
                 tests/test_g4_ensemble.py::test_effective_blocks_is_non_overlapping_count
  prod or exp:   experiment (design-time power/MDE calculation; no live model
                 score, no production path touched)
  existing data: the prior $32 Modal run reported a retracted PatchTST
                 60d-horizon IC of "+0.13" (cited in
                 doc/research/2026-07-23-g4-ensemble-prereg.md L18-19). At the
                 60d horizon, ~600 usable trading days over 2.3y give
                 K = effective_blocks(600, 60) == 10 independent blocks
                 (asserted by test_effective_blocks_is_non_overlapping_count).
                 With sigma_ic ~= 0.10 (placeholder, doc L34), the one-sided
                 z-test MDE at 10 blocks is min_detectable_ic(10, 0.10) ==
                 0.078630 (pytest.approx, abs=1e-4, checked against textbook
                 z_.95 + z_.80 = 2.486475) — i.e. the retracted "+0.13" sits
                 well inside noise range for that sample size.
  best-known?:   first power-gated design for G4; there is no competing gated
                 variant — it supersedes the prior ungated $32 spend, not a
                 better-performing model result.
  scope:         "this is a design-time MDE calculation (power.py, experiment,
                 not a live model IC), unit-tested against textbook one-sided
                 z-values in tests/test_g4_ensemble.py — 13/13 passed locally
                 2026-07-23 (`pytest tests/test_g4_ensemble.py -q`). It makes
                 NO live model-performance claim; PatchTST/XGB scorer wiring
                 and any Modal spend stay gated behind a Tier-1 existence lead."
NEXT:      Wire real PatchTST/XGB scorers into `harness.score` and run
           Tier-0/Tier-1 on real data. Tier-2 paired increment and the Tier-3
           forward sequential test stay gated behind a Tier-1 existence lead.

## Deliverables
- `doc/research/2026-07-23-g4-ensemble-prereg.md` — the design/prereg.
- `doc/research/evidence/2026-07-23-g4-ensemble/frozen_spec.json` — commit-1
  frozen spec (`sha256=4126b04c…`), built + validated (R3/R4) via
  `expkit.prereg.FrozenSpec`.
- `src/renquant_orchestrator/g4_ensemble/`
  - `power.py` — the one missing primitive: MDE / required-blocks /
    achieved-power (closed-form, one-sided z; scipy).
  - `harness.py` — Tier-0/1/2 evaluators, pure *composition* of `expkit`
    (`per_date_ic`, `shifted_label_placebo`, `paired_deltas`,
    `block_bootstrap_conditional_mean`, `summarize_boot`). Scoring is an
    injected wide-frame → runnable on synthetic, wireable to real models later.
  - `spec.py` — the frozen G4 spec builder + writer.
- `tests/test_g4_ensemble.py` — 13 tests, green: power vs textbook z-values;
  positive control recovers a known ρ=0.8 signal; null score yields no false
  positive; paired increment fires only on real dominance; spec hashes stably.

## Design one-liner
Power analysis first → screen for existence where power exists (5/20d) →
paired increment for the ensemble question → the un-powerable 60d go/no-go is
explicitly reserved for a Tier-3 forward sequential test. Every dollar of
Modal spend is gated behind a Tier-1 lead.

## Reuse discipline
No statistics reimplemented — `expkit` (#287, codex-reviewed) already ships
IC / placebo / paired-delta / block-bootstrap / freeze-first prereg. Only the
power/MDE calculator was genuinely new; kept in the g4 package (not bloated
into `expkit`) per the #287 narrowing.

## Not done (deliberately gated)
- Wiring real PatchTST/XGB scorers into `score` (compute-gated follow-up).
- Any Modal spend (unlocked only after Tier-1 shows a 60d-relevant lead).
- Tier-3 forward-test prereg (a separate frozen spec when reached).

## Review
Design PR — not self-merged; Codex is the gate. Design modifications are the
operator's per the design-review-is-personal rule.
