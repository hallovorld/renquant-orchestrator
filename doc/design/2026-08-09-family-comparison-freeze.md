# Design freeze: served blend vs WF-recipe xgb — realized 5d outcomes on the shared window

STATUS: DESIGN FREEZE (pre-outcome). This document fixes every choice
BEFORE the outcome join is computed. The runner may not add, remove, or
tune anything the tables below do not specify. Task #26's next increment;
feeds the qp re-enable evidence chain (the 05-23 recorded condition:
"re-enable only after WF shows benchmark-relative alpha survives the
strict admission gate") — this comparison is DIAGNOSTIC input to that
chain, not the gate itself, and it must not feed promotion directly.

## 1. Question (one sentence)

On the days live actually scored, did the scores live ACTED ON (the
served family) select names with better or worse realized 5-day excess
returns than the scores the validated replay family would have produced
on the same days and the same universe?

## 2. The two arms (both already exist; nothing is trained for this)

| arm | score source | identity |
|---|---|---|
| SERVED | `ticker_daily_state.panel_score`, canonical run per date (the orch#949/#950-verified record) | as recorded live |
| REPLAY | the frozen xgb_mom_60d v2 harness model, trained by the committed harness recipe on the FROZEN corpus (folds/params/features frozen at model#213), scored on the extension panel | fold-8 (train ≤ 2025-12-31), the only fold whose training data predates the whole window; the REPLAY score is the MEAN of the three boosters trained with the harness's frozen seed tuple (42, 43, 44) — the tuple is frozen in the harness, so no seed is chosen here |

Rationale for fold-8: its training labels end ≥ 91 days before the
comparison window starts — no leakage into ANY comparison date; and it is
the fold the v2 verdict's own gate arithmetic scored strongest in 2026.
No other fold, no retrain, no ensemble.

## 3. Frozen comparison table

| item | frozen value |
|---|---|
| window | 2026-05-20 .. 2026-07-31 (the last date whose fwd_5d label realizes within the extension build ending 08-07) |
| days | canonical-run days with ≥ 30 live-scored names (no other day filter) |
| universe per day | the INTERSECTION of live-scored names and replay-scorable names (per-day, recorded with counts + asymmetric diffs, the #950 coverage discipline) |
| k | 5 (matches the live top-5 surfaces measured throughout #26); NO other k is computed |
| outcome | mean fwd_5d_excess of each arm's top-k, minus the intersection-universe mean that day (both arms pay the same benchmark) |
| label source | the extension build's fwd_5d_excess (orch#948 recipe). Boundary-date labels are NOT in the window (last label date needed = 08-07, the build's edge — the 05-07 boundary-label exception does not intersect this window's labels; asserted in the runner) |
| aggregation | per-day arm difference (SERVED top-k mean − REPLAY top-k mean), then the mean and median across days; sign + magnitude reported with a stationary-bootstrap CI (block 5, B 2000, seed 99 — the condact harness's frozen bootstrap, block shortened to the 5d horizon) |
| ties | `nlargest` deterministic order (index order after sort); no tie-breaking randomness |
| missing | a day where either arm scores < k names in the intersection is SKIPPED and counted in the coverage table |
| verdict authority | NONE. This is a diagnostic table. No PASS/KILL. Any serving-change proposal citing it must run its own prereg. |

## 4. What is deliberately NOT in scope

* No k sweep, no horizon sweep, no regime/sector conditioning, no
  Sharpe — one k, one horizon, one pooled table. (Conditioning variants
  are NEW preregs; this document may not be amended to add them.)
* No 60d outcomes: fwd_60d labels cover only 432 extension rows
  (orch#948) — out of reach until the calendar delivers; a 60d version
  is a NEW dated design when labels exist.
* No counterfactual portfolio/P&L: selection-quality only, upstream of
  sizing/admission — those gates are measured elsewhere (orch#943).
* The REPLAY arm is the momentum family the operator ordered (xgb_mom),
  NOT the 148-feature panel WF family; a panel-family arm is a NEW
  design if wanted (stated so the scope cannot silently widen).

## 5. Freeze surface

The runner must ast-read FEATS/CUTS/params from the committed v2 harness
(model#213 frozen text), assert the frozen corpus sha against the
harness pin before training fold-8, and record: fold-8 booster training
row count, extension-parquet sha256, per-day coverage (counts + both
asymmetric-diff name lists), and the skipped-day count. Evidence files
must be the runner's verbatim outputs (the #949/#950 review lessons,
applied from the start). Any deviation from the tables above voids the
run and requires a NEW dated design document — this one may not be
edited after its PR merges (post-merge edits = a new freeze).
