# GOAL-2v3 Stage I-2 — preregistration of the stacked meta-learner

Status: **PREREGISTRATION — frozen before any I-2 fit.** Declared 2026-08-29,
after the Stage I-1 DEV RUN result (#1088, run
`i1-dev-20260829T113813Z-666484a7`) and before any meta-learner is trained.
Parent design: `doc/design/2026-08-27-goal2v3-intraday-granularity.md`
(§ "Stage I-2 — the stacked meta-learner"). Every number here is a frozen
constant; a change after the first `--dev-run` is a new attempt, recorded as
such.

## 0. Bottom line

- The I-1 trigger fired **by the letter and by 0.087 block-t units** (B2
  3.5915 vs B0 3.5042 `[VERIFIED #1088 report bases.*.overall.block_t]`).
  The same report shows that B2's mean block IC is *lower* than B0's
  (0.009603 vs 0.010911) and that the naive reference s₀ = −r13 scores
  **4.1861**, above every learned base (3.18–3.59) `[VERIFIED #1088 report
  s0_reference.overall.block_t]`.
- Therefore the I-2 pass bar is set **harder than the parent design's
  minimum**: the stacked model must beat the best surviving base **and** s₀
  on the *same* meta-OOF rows (§4). A stack that only beats B0 but not the
  naive reversal has earned nothing that a one-line feature already
  delivers, and must not graduate to the sealed evaluation window.
- Outcome space (§4.4) is enumerated now: PASS → confirmatory prereg on the
  sealed window; FAIL-A (beats bases, not s₀) / FAIL-B (beats nothing) →
  attempt recorded, line pauses for an operator decision. No other outcome
  can be declared.

## 1. Inputs (frozen)

1. **Base OOF predictions** from a *re-fit* of B0, B1, B2, B3 exactly as
   preregistered in I-1 (same constants, seeds, folds, row cap, store). The
   I-1 bundle does not persist per-row predictions (its audit carries block
   series), so I-2 re-fits the bases and **fails closed unless every re-fit
   reproduces the I-1 overall block-t to 4 decimals** (B0 3.5042, B1 3.1837,
   B2 3.5915, B3 3.2394) and the same `n_blocks` (622/511/622/619). A
   mismatch is a determinism defect, not a result.
2. **Slow state** as of the prior close, exactly the I-1 definitions: K5
   regime one-hot (`B1_STATE_LAG_SESSIONS = 1`), B3 slow-leg sign
   (`B3_SLOW_SESSIONS = 60`), sector code as used by B2 (post-fold-into-OTHER
   mapping of the fold in which the row is OOF), and `slot`.
3. **Nothing else.** In particular s₀ is *not* a meta-feature (it is the
   reference the stack is measured against; r13 is already inside every
   base's feature set F).

Binding: the I-2 harness binds to the I-1 bundle the way I-1 bound to I-0 —
frozen `ACCEPTED_I1_BUNDLE` constants (run_id, source commit 666484a7,
report/audit sha256, consumed-bar aggregate `4addcbe2…`), verified on disk
before any bar is read; `--dev-run` refuses otherwise (exit 2), refuses a
dirty tree, refuses an existing output bundle, and writes
`doc/research/data/<date>-g2v3-i2/<run_id>/` with the same provenance block
and validator standard as I-1 (#1084 r2/r3).

## 2. Nested out-of-fold discipline (frozen)

The I-1 folds are `FOLDS[0..4]` (6-month OOF halves 2022H1 … 2024H1). Base
OOF predictions exist only on those OOF halves. The meta-learner is trained
and scored **strictly forward-chaining on top of them**:

| meta-fold | meta-train rows (base-OOF halves) | meta-OOF half |
|---|---|---|
| M1 | 2022H1 | 2022H2 |
| M2 | 2022H1–2022H2 | 2023H1 |
| M3 | 2022H1–2023H1 | 2023H2 |
| M4 | 2022H1–2023H2 | 2024H1 |

- 2022H1 is never meta-scored (it has no prior base-OOF training data).
  The **meta-OOF period is 2022-07-01..2024-06-30**; all I-2 comparisons
  (§4) are computed on exactly these rows for every series.
- 13-bar purge at every meta train/OOF boundary, satisfied by construction
  on the A1 grid as in I-1 (within-session labels).
- The base model that produced a row's meta-feature never saw that row
  (I-1 OOF property); the meta-learner never sees its own OOF half. No base
  is refit inside the meta loop.

## 3. The meta-learner (frozen)

- **M_xgb**: XGBoost `reg:squarederror`, `max_depth=2`, `n_estimators=200`,
  `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=1.0`,
  `min_child_weight=50`, `tree_method="hist"`, `random_state=20260829`,
  `n_jobs=8`. Row cap 4,000,000 per meta-fit, sampled without replacement,
  seed `20260829 + 1000·meta_fold`.
- Meta-features (11): `p_B0, p_B1, p_B2, p_B3` (raw OOF predictions; NaN
  where the base abstained — XGBoost's native missing handling, plus one
  indicator `n_abstain` = count of NaN bases), `regime_{BEAR,BULL_CALM,
  BULL_VOLATILE,CHOPPY}` one-hot, `b3_slow_sign` ∈ {−1,+1}, `slot`.
  Sector enters only through `p_B2` (no sector one-hot; 11+ dummies on a
  depth-2 tree would be a second model, not a stack).
- **M0 diagnostic (not gated)**: the unweighted z-sum of the available base
  predictions per row (z-scored within each session×slot cross-section),
  reported beside M_xgb so the reader sees whether fitting earned anything
  over the served-blend convention. M0 is never the pass decision.
- Label: the I-1 h=13 forward log return at the same bar-times
  (`SCREEN_SLOTS` t = 13..25). Blocks, ρ̂₁, n_eff_adj, block-t: the A1/I-1
  machinery unchanged (`MIN_NAMES_PER_IC=100`, `MIN_PAIRS=8`, ρ̂₁ floored at
  0 with raw reported).

## 4. Pass bar (frozen — harder than the parent design's minimum)

All series below are scored on the **identical meta-OOF row set** (rows
where M_xgb has a prediction; a base's abstain rows are excluded from
*every* series for the common-sample comparison, and the excluded fraction
is reported).

- **P1 life**: M_xgb block-t ≥ 1.0 overall @ h=13 on dependence-adjusted
  units; BEAR n_eff_adj ≥ 30 re-verified on M_xgb's own OOF IC.
- **P2 earns its complexity**: M_xgb block-t > max(B0, B1, B2, B3 block-t)
  on the common sample.
- **P3 beats the naive reversal**: M_xgb block-t > s₀ block-t on the common
  sample.

`stage_i2_pass = P1 ∧ P2 ∧ P3`. Strict inequalities on point estimates, as
in the parent design; **no margin is claimed and none is required** — the
prose must state the margins as numbers. Per-regime block-t is reported for
every series and never gates.

### 4.4 Outcome register (enumerated before the run)

| outcome | condition | consequence |
|---|---|---|
| PASS | P1 ∧ P2 ∧ P3 | graduate: write the confirmatory prereg against the SEALED window 2024-07-01..2026-06-30 (its own PR; the window stays untouched until that prereg is merged) |
| FAIL-A | P1 ∧ P2 ∧ ¬P3 | stacking works but nothing in this line beats −r13 at h=13; record as a failed attempt; line PAUSES for an operator decision (candidates for that decision, not for this run: promote s₀ itself to a confirmatory prereg, or close the line) |
| FAIL-B | ¬(P1 ∧ P2) | record as a failed attempt; line pauses for an operator decision |
| REFUSED | any fail-closed guard (§1 binding, determinism, dirty tree, store manifest) | no result; defect fixed, new attempt |

No third meta-learner, no feature added to the stack, and no change to the
bar after observing the run. A second I-2 attempt (if the operator asks for
one) is a new prereg with its own number.

## 5. Interpretations declared now (copied verbatim into the report)

1. "Surviving bases" = every base whose I-1 `passes_life_bar` is true; all
   four survived, so all four enter the stack.
2. Base abstain rows (I-1 interpretation 8) become NaN meta-features, never
   imputed; `n_abstain` carries the count; the common-sample comparison
   excludes rows where *any* series lacks a prediction.
3. Sector code for the slow state = the B2 post-fold mapping of the fold in
   which the row is OOF (the mapping the base actually used).
4. M0's per-row z-scoring uses the cross-section of names present at that
   session×slot; a row with fewer than `MIN_NAMES_PER_IC` names in its
   cross-section has no M0 value (and is therefore excluded from the common
   sample for M0's diagnostic line only).
5. Determinism guard tolerance: block-t equal to 4 decimals and n_blocks
   equal; any drift beyond that refuses the run (XGBoost `hist` with fixed
   seeds and single-process fitting is deterministic on one machine; a
   cross-machine rerun is a new attempt).
6. Secondary horizons h=1, h=3 are reported for M_xgb exactly as in I-1 —
   diagnostic only, never gating.

## 6. What this stage cannot show

- Nothing about the sealed evaluation window; nothing about live serving
  (Stage I-3, own PRs, S3-c remains an explicit operator ask).
- Nothing about costs: block-t on OOF IC is a signal-quality screen, not a
  net-of-cost claim; the Phase −1 result (intraday alpha net-edge NEGATIVE
  at IC 0.03) is the standing prior that any graduated model must later
  clear on its own.
- The meta-OOF period is four half-years (≈500 blocks); BEAR blocks after
  dropping 2022H1 are fewer than I-1's 191 — the P1 BEAR n_eff_adj ≥ 30
  re-verification is therefore a real gate, not a formality.

## 7. Execution plan

1. This prereg merges (codex review) **before** the harness PR.
2. Harness PR: `scripts/experiments/g2v3_stage_i2_stack.py` implementing
   §1–5 literally, frozen constants at module top, synthetic smoke default,
   `--dev-run` fail-closed on the I-1 binding + determinism guard, tests for
   every guard and for the pass-bar arithmetic (P1/P2/P3, common sample,
   outcome register).
3. One `--dev-run` from a clean main worktree; record PR with the bundle +
   descriptive research doc; the outcome register row is quoted, the
   margins are stated as numbers.
