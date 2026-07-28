# Shadow staleness gate vs label horizon — design memo (operator decision)

Date: 2026-07-28
Status: DECISION NEEDED (two options, recommendation included)
Owner: claude · Reviewer: codex

## The problem: a freshness gate no fwd60 model can ever pass

The shadow health record (renquant-pipeline#211) and the shadow-scorer
sentinel judge actionability by `staleness_days` measured from
`effective_train_cutoff_date`, threshold 28d. But a model labeled with a
60d forward return CANNOT have a training cutoff closer than
`label_horizon + embargo` behind today — the label for the last training
row must have fully resolved.

Live evidence (both flags today are this artifact of the metric, not a
process failure):

| model | trained | effective cutoff | staleness flag | freshest possible |
|---|---|---|---|---|
| topdecile_clf (fwd60) | 2026-07-27 | 2026-04-28 | `stale_91d_limit_28d` | ~82–91d by construction |
| fresh PatchTST fold 2026-03-02 (fwd60) | 2026-07-28 | 2025-12-05 | (would flag) | same bound |

A model retrained THIS MORNING flags stale on arrival. The gate conflates
two different axes:

- **training recency** (`trained_date` age) — what the freshness
  governance policy (RFC #210, "no model >28 days") actually governs;
  fully controllable by retrain cadence.
- **data-cutoff lag** (`effective_train_cutoff_date` age) — bounded below
  by `horizon + embargo` (~82–90d for fwd60); NOT controllable; only its
  EXCESS over that bound signals a problem (stopped retraining, broken
  panel refresh).

## Option A (recommended): two-axis check, horizon-aware bound

Health record + sentinel gate on BOTH:
1. `trained_age = today − trained_date` ≤ 28d (aligns with RFC #210).
2. `cutoff_lag = today − effective_train_cutoff_date` ≤ `label_horizon +
   embargo + slack` (fwd60 with ~30d embargo and 28d slack → 118d).

Record carries both numbers; `actionable=false` only when either breaches.
The 622d legacy lane still flags (622 ≫ 118) — true positives preserved.
Requires: producer change in renquant-pipeline (label horizon read from
the artifact/config, not hardcoded), sentinel threshold via the existing
env, one config field per shadow lane. Recipe keys already carry
`effective_train_cutoff_date`, so no schema change — only the verdict rule.

## Option B (minimal): switch the existing single check to trained_date

Keep one axis: `trained_date` age ≤ 28d. One-line producer change, no new
config. Loses the cutoff-lag tripwire — a broken panel refresh that
freezes `effective_train_cutoff_date` while retrains keep succeeding
would go undetected (this is the fund-freshness bug class we have
actually had). Cheaper but blinder.

## Recommendation

Option A. The two axes fail for different root causes we have BOTH
experienced (stale model = per-ticker tournament frozen since April;
frozen cutoff = fund-freshness serving-axis clip). One number cannot
watch both. Cost is one reviewed pipeline PR + a sentinel env default.

Until decided, the `stale_91d` flag on the clf lane stays — correctly
reported, known benign, documented here.
