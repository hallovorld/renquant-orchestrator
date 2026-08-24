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

## 3. Stage 0b, redesigned PIT-safe [codex: the first draft measured memorization]

The first draft proposed scoring the 2024-2026 corpus with TODAY'S pinned
artifacts. That places most or all evaluation dates INSIDE each leg's
training/validation/selection window, and neither gap-blocking nor a
shuffled-label placebo detects upstream score leakage — Stage 1 would have
measured memorization as conditional skill. Withdrawn.

**The three PIT-safe options, dispositioned against this system's reality:**

| option | disposition |
|---|---|
| (a) artifacts as-of each date | IMPOSSIBLE for the legs: the momentum/clf legs were first trained Jul–Aug 2026; no 2024-vintage artifacts exist |
| (b) evaluate only post-cutoff dates | EMPTY: leg cutoffs are ≥ 2026-07 and the labeled corpus ends 2026-07 — near-zero genuinely OOS dates |
| **(c) study-only leg replicas, pre-corpus cutoff** | **CHOSEN** — the only option that yields a non-empty OOS panel |

**Stage 0b-α (availability + freeze, BEFORE any training or scoring):**
1. For each of the 3 core legs, freeze a STUDY RECIPE: the leg's feature set
   and learner hyperparameters as pinned today, with ONE change — training
   data ends at the STUDY CUTOFF `2023-12-29`. Recorded per leg: recipe hash,
   the pinned artifact it mirrors, the cutoff.
2. Verify feature availability for the training window AND the 2024+
   evaluation window from the local OHLCV store, per leg, per ticker; record
   coverage. **KILL (0b-α): any leg untrainable at the study cutoff, or
   evaluation coverage < 80% of corpus dates.** All of this is committed
   before a single model is trained — the availability check codex required
   before compute.

**Stage 0b-β (train + score + assemble):**
3. Train each study replica ONCE on data ≤ 2023-12-29. No selection loop, no
   retries, no peeking: one recipe, one fit, frozen. (A replica that fails to
   converge is recorded and its leg drops; the panel proceeds only if ≥ 2
   legs survive — a 1-leg "panel" has no weighting question.)
4. Score 2024-01..corpus-end with the replicas. EVERY ROW records: leg
   replica artifact sha256, its train cutoff, the evaluation date — so the
   OOS property of each row is checkable, not asserted.
5. Recompute ESS on the ASSEMBLED OOS panel at h=20. **KILL (0b-β): n_eff <
   12.**

**What the replicas do and do not stand for, stated now:** Stage 1 on this
panel tests whether SLOW-STATE CONDITIONING of this leg FAMILY carries
information out of sample. It does not certify today's pinned artifacts —
those differ from the replicas by training window. If Stage 1 survives, the
promotion path re-runs the weighting fit on the live legs' own accruing
shadow panel before anything ships (and that panel's own ESS clock applies).
This limitation is accepted because the alternative — waiting for the live
panel — is the mid-2027 path.

**The ESS bar, re-derived rather than inherited [codex]:** 12 is a
MINIMUM-INDEPENDENT-BLOCKS validity floor for a block-t (single-digit blocks
make the t reference meaningless — the borrowed-critical-values failure), not
a power claim, and it is horizon-independent by construction. What changes
with h=20 is the detectable effect size: with n_eff ≈ 30 (the plausible
assembled range), a block-t at α=0.05 has ~80% power only for effects ≥
~0.52σ of the per-block statistic. Stage 1's prereg will therefore state the
post-hoc minimum detectable effect ALONGSIDE any result, and a "null" verdict
below that sensitivity is recorded as UNDERPOWERED-NULL, not as evidence of
no effect.

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
