# renquant105 — repointed to multi-period trend-signal recall + precision

2026-06-27.

## What & why
renquant105's prior intraday / day-trading design suite was wrong-framing and is
closed (#199, #416 closed; #198 to be superseded). The operator confirmed the
real goal: catch MORE real trends (recall — the conviction gate currently admits
~0/84) and MORE-ACCURATELY (precision — fewer false signals), traded as
multi-day holds for the trend's duration — NOT intraday / HF / day-trading. This
doc records that grounded direction so the next session starts from the
evidence, not the closed framing.

## State (single durable record)
- Design doc: `doc/design/2026-06-27-renquant105-trend-signal-direction.md` —
  the evidence-graded direction (goal, graded evidence table, prioritized
  levers, reused methodology spine, 104 reliability track, first steps + what's
  blocked). Do not duplicate it here.
- Evidence is GRADED on purpose and the grades must not be conflated:
  - **[VERIFIED]** (adversarial 3-verifier vote complete): HF input data is
    microstructure-noise-dominated → minute/intraday input is NOT a multi-day
    lever; HF's proven value is volatility/risk, not directional multi-day alpha.
  - **[SOURCED·UNVERIFIED]** (primary source + quote, but the adversarial vote
    did NOT complete — deep-research hit a monthly spend limit mid-run →
    abstained, NOT refuted): slow predictors / momentum dominance / structurally
    low baseline IC (Gu–Kelly–Xiu; Lou–Polk–Skouras).
  - **[THEORY]**: Fundamental Law (IR = IC·√breadth) → at low IC, orthogonal
    low-correlation breadth beats input-frequency refinement.
  - **[DATA·THIN]**: our PR #200 ledger is too short to settle anything
    (fwd_20d = 11 aged dates; fwd_60d = 0; sim rows excluded as unfaithful);
    directional IC at/below the ~0.036 shuffled floor; killed-winner
    decomposition → MODEL is the ~3.6× dominant bottleneck, gate secondary.

## Decision / direction
Prioritized levers: (1) fresher data + RETRAIN (cheapest + prerequisite; training
internals live in `renquant-model`, not the orchestrator); (2) trend/momentum
target via triple-barrier / multi-horizon labels; (3) orthogonal alpha =
analyst-estimate revisions (data ~283/291 harvested); (4) gate redesign — AFTER
the model ranks better; (5) minute/intraday input — parked, not a lever.
Methodology spine reused from the closed intraday suite, target repointed.

## Blocked / re-measure
A conclusive model-vs-gate split and any absolute net-edge claim are BLOCKED
until live ages to ≥30 fwd_20d dates (~mid-Aug-2026) OR faithful per-name
PatchTST score history + provenance is wired (#133 follow-through). Re-run the
PR #200 baseline then.

## Scope
Direction + design only — no code/runtime change. Live tree and canonical prod
inputs untouched.
