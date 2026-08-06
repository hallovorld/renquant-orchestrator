# Two fail-close guards exist only in the SERVED twin   (PR #873)

STATUS:   delivered — measurement only; no code ships and no production surface is touched.

WHAT:     Records that two fail-close guards are present in `renquant_pipeline/panel_scoring.py`
          (the twin production runs) and absent from
          `kernel/panel_pipeline/job_panel_scoring.py`, and that the twin divergence
          is bidirectional rather than kernel-is-the-superset.

WHY/DIR:  GOAL-3. orch#867 ended on an open question for the pipeline owners —
          *which twin is canonical?* — and named two opposite remedies. This adds a
          hard constraint to one of them: re-pointing the runtime at the kernel twin
          would silently remove two guards that protect live decisions today.

EVIDENCE:
artifact:      `renquant_pipeline/panel_scoring.py` and
               `renquant_pipeline/kernel/panel_pipeline/job_panel_scoring.py`,
               read from the PINNED runtime
               `RenQuant/.subrepo_runtime/repos/renquant-pipeline/src/`
prod or exp:   prod — these are the two implementations behind the five lazily-mapped
               public symbols; `panel_scoring.py` is the one `pp_inference.py:334`
               imports, i.e. the one production executes.
existing data: orch#867 established 0 production importers for the kernel twin and 28
               test files importing it; orch#833 established 19 of 20 public exports
               resolve to the non-kernel twin. Neither examined guard parity.
best-known?:   yes for guard PRESENCE, by source inspection of both implementations.
               Not a behavioural equivalence check — see the limits below.

          Measured `[VERIFIED — this session, 2026-08-06]`:

          | symbol | guard present only in SERVED | what it blocks |
          |---|---|---|
          | `BuildFeatureMatrixTask` | `feature_contract_missing` | `validate_feature_contract(..., policy="error")` fails — the candidate's feature row is missing required columns |
          | `ApplyScoresTask` | `missing_panel_score` | `score is None` — the candidate has no panel score |

          Searched the kernel twin for an equivalent under four plausible alternative
          spellings (`feature_contract`, `panel_score is None`, `missing_panel`,
          `contract_missing`): **none present**.

          Size asymmetry runs BOTH ways, so neither twin is the superset:

          | symbol | served | kernel | |
          |---|---:|---:|---|
          | `LoadScorerTask` | 17 | 231 | 13.6× kernel |
          | `ApplyScoresTask` | 68 | 616 | 9.1× kernel |
          | `VetoWeakBuysTask` | 70 | 369 | 5.3× kernel |
          | `PanelScoringJob` | 37 | 93 | 2.5× kernel |
          | **`BuildFeatureMatrixTask`** | **36** | **20** | **0.56× — served is bigger** |

          `tests/test_panel_scoring_twin_domain_lockstep.py` pins one guard
          (`_rank_score_domain`) plus the `RANK_SCORE_DOMAIN_*` constants — roughly one
          of at least three known asymmetries, and none of the bidirectional ones.

NEXT:     If the twin question resolves toward the kernel implementation, these two
          guards must be ported FIRST, and a test must pin their presence in whichever
          twin ends up served — the lockstep test's shape, extended past the one guard
          it covers today. Decision belongs to renquant-pipeline (repo boundary).

## What this does NOT establish

- **Not that the kernel twin is unsafe.** It may enforce these conditions earlier,
  structurally, or not need them given how it is called. Four alternative spellings
  were searched and none found — that is evidence of absence in the source, not proof
  the protection is missing in effect.
- **Not that the served twin is the better implementation.** It is 9–13× smaller on
  three symbols; what that difference contains is unexamined here.
- **Not a recommendation between orch#867's two remedies.** That is the pipeline
  owners' call. This adds one hard constraint to remedy 1, nothing more.
