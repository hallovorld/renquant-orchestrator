# GOAL-3: two fail-close guards exist only in the SERVED twin — so one of the two candidate remedies would remove them

**Date:** 2026-08-06
**Lane:** GOAL-3 (architecture compliance audit)

## Bottom line

orch#867 ended on a question for the pipeline owners: **which twin is canonical?**
and named two opposite remedies. This measures something that decides between
them `[VERIFIED — this session]`:

> **Two fail-close guards are present in `panel_scoring.py` (the twin production
> runs) and absent from `kernel/panel_pipeline/job_panel_scoring.py`.**

| symbol | guard, served-only | what it blocks |
|---|---|---|
| `BuildFeatureMatrixTask` | `feature_contract_missing` | `validate_feature_contract(..., policy="error")` fails → the candidate's feature row is missing required columns |
| `ApplyScoresTask` | `missing_panel_score` | `score is None` → the candidate has no panel score |

Checked for an equivalent under another name in the kernel twin
(`feature_contract`, `panel_score is None`, `missing_panel`, `contract_missing`):
**none present.**

## Why this decides the #867 question

orch#867 laid out the two remedies:

1. *if `job_panel_scoring` is canonical* → the runtime is wired to the wrong
   module and `pp_inference.py:334` is the bug;
2. *if `panel_scoring.py` is canonical* → 4350 lines and 28 test files guard
   something that never runs.

**Remedy 1 would silently remove two live fail-close guards from production.**
Re-pointing the runtime at the kernel twin does not merely change which
implementation runs — it drops `feature_contract_missing` and
`missing_panel_score`, both of which are protecting live decisions today.

That does not make remedy 1 wrong. It makes it a **migration with two named
preconditions**, not a one-line re-point.

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
  earlier, structurally, or not need them given how it is called. I searched for
  four plausible alternative spellings and found none — that is evidence of
  absence in the source, not proof that the protection is missing in effect.
- **Not that the served twin is the better implementation.** It is 9–13× smaller
  on three symbols; whatever that difference contains is unexamined here.
- **Not a recommendation between the two remedies.** That is the pipeline
  owners' call. This adds one hard constraint to remedy 1, nothing more.

## Next

If the twin question is resolved toward the kernel implementation, these two
guards must be ported **first**, and a test must pin their presence in whichever
twin ends up served — the same shape as the lockstep test, extended beyond the
one guard it currently covers.
