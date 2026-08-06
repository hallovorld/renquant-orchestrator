# GOAL-3: two fail-close guards exist only in the SERVED twin — so one of the two candidate remedies would remove them

STATUS:   complete for this scoping question; not a recommendation between the two
          remedies orch#867 named.
WHAT:     documents that two fail-close guards — `feature_contract_missing` in
          `BuildFeatureMatrixTask` and `missing_panel_score` in `ApplyScoresTask` —
          are present in the served twin (`panel_scoring.py`) and were not found
          under four searched spellings in the kernel twin
          (`kernel/panel_pipeline/job_panel_scoring.py`), and that the served/kernel
          divergence runs in both directions, not just the one the lockstep test
          pins.
WHY/DIR:  orch#867 ended on "which twin is canonical?" and named two opposite
          remedies. Remedy 1 ("`job_panel_scoring` is canonical, re-point the
          runtime") would silently remove two live fail-close guards if adopted
          as a one-line re-point — this finding turns it into a migration with
          two named preconditions, not a recommendation for either remedy.

## Two fail-close guards, served-only

| symbol | guard, served-only | what it blocks |
|---|---|---|
| `BuildFeatureMatrixTask` | `feature_contract_missing` | `validate_feature_contract(..., policy="error")` fails → the candidate's feature row is missing required columns |
| `ApplyScoresTask` | `missing_panel_score` | `score is None` → the candidate has no panel score |

Checked for an equivalent under another name in the kernel twin
(`feature_contract`, `panel_score is None`, `missing_panel`, `contract_missing`):
none present as a named, fail-close guard.

## The divergence is bidirectional, which the lockstep test does not reflect

| direction | example | covered by `test_panel_scoring_twin_domain_lockstep`? |
|---|---|---|
| kernel-only guard | `#219` unit guard (the incident that produced the test) | **yes** — that one guard |
| **served-only guard** | `feature_contract_missing`, `missing_panel_score` | **no** |

And the size asymmetry runs both ways too, so neither twin is the superset:

| symbol | served | kernel | |
|---|---:|---:|---|
| `LoadScorerTask` | 17 | 231 | 13.6× kernel |
| `ApplyScoresTask` | 68 | 616 | 9.1× kernel |
| `VetoWeakBuysTask` | 70 | 369 | 5.3× kernel |
| `PanelScoringJob` | 37 | 93 | 2.5× kernel |
| **`BuildFeatureMatrixTask`** | **36** | **20** | **0.56× — served is bigger** |

The lockstep test pins one guard and the `RANK_SCORE_DOMAIN_*` constants. It
covers roughly **one of at least three** known asymmetries, and none of the
bidirectional ones.

## What this does NOT establish

- **Not that the kernel twin is unsafe.** It may enforce these conditions
  earlier, structurally, or not need them given how it is called. Four
  searched spellings finding nothing is evidence of absence in the source,
  not proof the protection is missing in effect.
- **Not that the served twin is the better implementation.** It is 9–13× smaller
  on three symbols; whatever that difference contains is unexamined here.
- **Not a recommendation between the two remedies.** That is the pipeline
  owners' call. This adds one hard constraint to remedy 1, nothing more.

EVIDENCE:
artifact:      `renquant-pipeline/src/renquant_pipeline/panel_scoring.py` (served
               twin, lines 158 `feature_contract_missing` / 218+354
               `missing_panel_score`) vs.
               `renquant-pipeline/src/renquant_pipeline/kernel/panel_pipeline/job_panel_scoring.py`
               (kernel twin). `[VERIFIED — grep re-check this session, 2026-08-06]`
prod or exp:   n/a — documentation only, read-only source comparison. No test,
               config, schedule, or production surface touched.
existing data: orch#867 (twin-divergence audit) and
               `test_panel_scoring_twin_domain_lockstep` (pins one kernel-only
               guard plus the `RANK_SCORE_DOMAIN_*` constants, not the two
               served-only guards named here).
best-known?:   yes for the scoping question asked ("does either candidate
               remedy for #867 have a hidden precondition?"); not a verdict on
               which twin should be canonical.
scope:         this repository only documents the two source files; no scorer,
               training, backtest, or execution behavior changes.

## Next

If the twin question is resolved toward the kernel implementation, these two
guards must be ported **first**, and a test must pin their presence in whichever
twin ends up served — the same shape as the lockstep test, extended beyond the
one guard it currently covers.

NEXT:     pipeline owners resolve the #867 canonical-twin question with these
          two served-only guards as a named precondition of remedy 1; extend
          `test_panel_scoring_twin_domain_lockstep` (or a successor) to cover
          both served-only guards, not just the one kernel-only guard it pins
          today.
