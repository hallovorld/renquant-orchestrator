# GOAL-2 redesign: conditional blend weights at h=20 — a NEW estimand, openly

STATUS: design for review. Supersedes the h=60 design (#1027) whose Stage 0
killed itself by its own frozen bar (#1031: meta-panel n_eff=0; re-score
ceiling 11 < 12). Per that kill's own text, a shorter horizon is a NEW
estimand requiring design review — this is that review, not a quiet re-run.

## 1. The multiple-comparisons question, answered first

Changing the horizon AFTER a failed ESS check is exactly the move the kill bar
exists to police, so the justification must be independent of any return
outcome — and it is: **the horizon is chosen from realized holding periods,
measured before any conditional result exists to peek at.**

| cohort | n | median hold | p25 | p75 |
|---|---:|---:|---:|---:|
| live sells | 35 | **10d** | 6 | 11 |
| sim corpus sells | 5,989 | **25d** | 14 | 40 |

[VERIFIED — trades.hold_days, runs DB, 2026-08-24]

The book's capital turns over in ~2 weeks live and ~5 weeks in sim. The 60d
label was inherited from the MODEL's training label, not from how the
portfolio holds. h=20 brackets both cohorts; it is the economics of the
estimand, not statistical convenience. No return-conditional quantity was
examined in choosing it, and Stage 1's comparison is frozen before any
conditional-skill table is computed (same ESS-first ordering as before).

## 2. Estimand v2

Does w(state) — per-leg weights on the existing z-blend, slow-state
conditioned — beat uniform weights on **20-trading-day** forward
DGTW-adjusted returns of the blended cross-sectional score? Null = uniform =
production. Output form, state variables, bounded-failure clamping: unchanged
from #1027.

## 3. Why this needs Stage 0b (history re-scoring), stated with its cost

Accrual cannot reach the bar: the multi-leg panel gains ~1 non-overlapping
h=20 observation per month; n_eff=12 arrives mid-2027. The only real unlock
is the one #1031 priced as "ceiling 34": re-score the 2024-01..2026-05
labeled corpus (584 dates) with each leg's pinned artifact.

**Stage 0b scope**: rebuild the alpha158 feature frames for the corpus dates
(routine — the training pipelines do this weekly for 146 tickers), score each
of the 3 core legs' pinned artifacts over them, assemble the meta-panel.
Local compute, no spend. **The ESS is then recomputed on the ACTUAL assembled
panel** — 34 is the ceiling under perfect coverage, and the kill bar of 12
applies to what is actually assembled, not to the ceiling.

KILL (Stage 0b): assembled-panel n_eff at h=20 < 12 ⇒ stop, record.
KILL (Stage 1): fails placebo or fails to beat uniform ⇒ line closed.

## 4. Stage 1 (unchanged discipline, h=20 statistic)

Ridge / depth-≤2 xgb only; prereg frozen BEFORE the run — folds,
fold-defining constants, block-t on non-overlapping blocks with gap ≥ 20,
never a borrowed 1.96; the WF gate's placebo discipline. Both arms carry ALL
legs (the dilution trap stays excluded by construction).

## 5. Explicitly unchanged / not in scope

No 10-minute data; no 105 coupling pre-survival; no transformer before
Stage-1 survival; no new base legs. The h=60 line stays closed — this does
not reopen it, and if h=20 also dies, the finding stands on two horizons.

## 6. Review

codex (haorensjtu-dev). Stage 0b implementation only after this design is
approved.
