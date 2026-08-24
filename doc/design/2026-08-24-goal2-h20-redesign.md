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

## 3. Stage 0b, third design [codex r2: recipe SELECTION is itself leakage]

Round-2 review was right that a pre-corpus TRAINING cutoff is not enough: the
leg recipes (feature sets, hyperparameters, the model families themselves)
were selected using 2024–2026 training/validation outcomes. Retraining those
recipes on pre-2024 data moves the leakage from fitted weights into recipe
selection; "one fit, no retries" cannot undo a selection that already
happened. And no demonstrably pre-2024 recipe exists — every leg was designed
in 2026.

**The one window untouched by BOTH weight fitting and recipe selection is the
pre-corpus past.** Recipe selection consumed 2024–2026 outcomes only; nothing
in 2016–2023 was ever an input to any leg's development [provenance recorded
per leg in 0b-α: selection window, the WF/GOAL runs that chose it]. So:

  * **train replicas on 2016-01..2019-12** (frozen recipes, one fit each);
  * **evaluate EXCLUSIVELY on 2020-01..2023-12** — four years the recipes'
    development never saw, in either direction;
  * the 2024–2026 corpus is NOT evaluated at all in Stage 0b/1 — it is
    development-contaminated and stays quarantined.

Ceiling at h=20 over 2020–2023: ~16 non-overlapping blocks ≥ the bar of 12;
the kill applies to the ASSEMBLED panel as before. The window contains 2020 —
one of the concentration years the slow-state hypothesis is about — and
2021–2023 as contrast. Feature availability for 2016+ is checked in 0b-α
(the universe-extension survey already established ~609 full-recipe tickers;
coverage is verified, not assumed, with its own kill).

**What this can and cannot license, sharpened:** survival says the leg
FAMILY's slow-state conditioning carried information in a fully quarantined
window. It says nothing about 2024–2026 — deliberately, because no honest
test of that window exists with these recipes. The promotion path is
unchanged: re-fit on the live legs' accruing shadow panel, whose first
labeled multi-leg rows land ~2026-09 and whose own ESS clock applies.

**Ex-ante sensitivity rule [codex r2, label semantics corrected r4], frozen
in the Stage-1 prereg BEFORE any outcome is inspected:** with the assembled
n_eff (known at 0b-β end, before any conditional result), the prereg fixes
α=0.05, target power 0.80, and computes the standardized minimum detectable
effect from those constants and n_eff alone. The MDE describes the DESIGN's
sensitivity — it is not an equivalence test, and the observed effect size
never selects the interpretation of a null. Labels, fixed ex ante:

- Every outcome is reported as **estimate + interval**, whatever the label.
- Survival of the preregistered test → the Stage-1 claim, no more.
- Nonsurvival → **NOT-DEMONSTRATED**. That is the terminal scientific label
  when the preregistered MDE ≤ the minimum effect of interest (the design
  was sensitive enough, and still nothing was demonstrated).
- Nonsurvival with preregistered MDE > the minimum effect of interest →
  **UNDERPOWERED-NULL** (the design could not have seen the effect it
  cares about; the null carries no information).
- **NO-EFFECT is not an available label in this design.** Claiming absence
  would require a SESOI and an equivalence test (e.g. TOST) frozen before
  outcomes; this prereg deliberately does not include one — the operational
  consequence of nonsurvival (the kill) does not need the absence claim.

The minimum effect of interest is frozen with the rest of the prereg
(Stage-1 table) before 0b-β outcomes exist. No post-hoc power or MDE is
computed or cited — the rule exists before the data speaks, or the label
does not attach. The operational kill below is unchanged by the label:
nonsurvival kills the line either way.

KILL (0b-α): any leg's recipe provenance cannot demonstrate a 2024–2026-only
selection window; or feature coverage < 80% on either the training or the
evaluation window.
KILL (0b-β): assembled 2020–2023 panel n_eff at h=20 < 12.

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
