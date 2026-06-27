# renquant105 — repointed to multi-period trend-signal recall + precision

2026-06-27.

## What & why
renquant105's prior intraday / day-trading design suite was wrong-framing and is
closed (#199, #416 closed; #198 to be superseded). The operator confirmed the
real goal: catch MORE real trends (recall) and MORE-ACCURATELY (precision),
traded as multi-day holds for the trend's duration — NOT intraday / HF /
day-trading. This doc records that grounded direction so the next session starts
from the evidence, not the closed framing.

**This RFC is a PROPOSAL and a pre-registration SCHEMA / measurement PLAN — NOT a
completed pre-registration. It does NOT authorize retraining and does NOT
establish a lever ranking.** It records corrected (regraded) evidence, marks
model-vs-gate UNDETERMINED, gives the objective its measurement *schema* (exact
event/horizon/thresholds NOT frozen here), instantiates the validation spine, and
specifies a factorial + data-audit CONTRACT. **Execution is GATED on a separate,
versioned, immutable pre-registration artifact that must receive its own review
and merge before any experiment arm runs.** (Round-2 per Codex CHANGES_REQUESTED
on PR #201 — round-1 reframed evidence + withdrew the lever order; round-2 makes
the RFC accurately a measurement-schema, fixes the stale unblock rule to match
#200, isolates Arm A to vintage only, fully specifies the factorial/inference, and
gates model-vs-gate on faithful replay.)

## State (single durable record)
- Design doc: `doc/design/2026-06-27-renquant105-trend-signal-direction.md` —
  the corrected evidence-graded direction (goal, regraded evidence table,
  UNDETERMINED model-vs-gate, operational objective, instantiated spine,
  pre-registered factorial + data audit, denominator reconciliation, 104
  reliability track). Do not duplicate it here.
- Evidence grades were CORRECTED to match the cited papers' estimand:
  - **[VERIFIED]** now covers ONLY the literal in-scope claim — raw HF returns
    are microstructure-noise-dominated **for integrated-variance / volatility
    estimation** (Aït-Sahalia–Mykland–Zhang; Zhang–Mykland–AS; Bandi–Russell).
    AMZ explicitly note modeling the noise can make as-fast-as-possible optimal.
  - **[SCOPED PRIOR]** (regraded DOWN from [VERIFIED]): "minute features cannot
    improve multi-day directional forecasts" and "HF's only proven
    cross-sectional value is volatility/risk." The variance-estimation papers do
    NOT study return prediction; Gu–Kelly–Xiu use monthly chars and do not test
    intraday features. Parking minute input is an empirical ABLATION decision,
    not a theorem.
  - **[SOURCED·UNVERIFIED]**: slow predictors / momentum dominance / structurally
    low baseline IC (Gu–Kelly–Xiu; Lou–Polk–Skouras) — adversarial vote did not
    complete; sourced, not confirmed.
  - **[THEORY]** with stated limit: Fundamental Law (IR = IC·√breadth); breadth =
    INDEPENDENT bets after correlation/turnover constraints, NOT feature-family
    count. The "orthogonal > input-frequency" ORDERING is DELETED and replaced by
    a measured marginal-utility experiment.
  - **[DATA·THIN]**: PR #200 ledger too short/impaired (fwd_20d ≈ 9 aged dates ≈
    0.45 effective non-overlapping blocks — ~1 independent observation; fwd_60d =
    0; scorer-mixture not PatchTST-primary; sim rows unfaithful/excluded);
    per-horizon significance now uses #200's on-cohort shuffled-label placebo, and
    the old 0.036 floor is a FOREIGN reference, NOT a pass/fail bar; the
    killed-winner decomposition is parameter-dependent / scorer-mixed / non-causal
    (ratio ≈ [0.91, 2.80], reverses) → does NOT set a stable model-vs-gate ratio.

## Decision / direction
- **Model vs gate = UNDETERMINED.** The "MODEL ~3.6× bottleneck" ordering is
  withdrawn. Defensible conclusions only: (a) provenance inadequate, (b) live
  gate often admits nothing, (c) model quality unmeasured. Observability + gate
  correctness may proceed IN PARALLEL with model work; neither establishes a
  ranking. **Any future model-vs-gate ORDERING is gated on a faithful homogeneous
  scorer/artifact cohort (PatchTST-only with production provenance) + a STATEFUL
  production replay of the ordered gate stack — consistent with #200 finding 1.
  More raw history alone does NOT unlock the synthetic-threshold decomposition.**
- **No asserted lever order.** Replaced by a FACTORIAL SCHEMA — a **2×2 freshness
  × label** design (A old-cutoff baseline REBUILT through the B pipeline / B
  fresh-data-only / C trend-label-only / D both) + E orthogonal analyst feature
  evaluated on UNTOUCHED data AFTER the base winner is selected. **Arm A is rebuilt
  from the OLD cutoff using the EXACT pinned B pipeline (code/config/data
  construction), first proven to PARITY with the production artifact within
  declared tolerances** — so A-vs-B isolates VINTAGE only; production-artifact
  performance is a SEPARATE observational reference. Named primary contrasts
  (freshness main effect, label main effect, interaction), a pre-registered
  selection rule, **nested outer evaluation**, and a named correction family +
  method (**Holm–Bonferroni FWER** across confirmatory contrasts + PBO /
  Deflated-Sharpe over the policy-return surface). Secondary horizons (fwd_10/20,
  triple-barrier, multi-horizon) are pre-registered ALTERNATIVES, not
  trial-multipliers. One shared trial ledger, identical folds/universe/cost/
  turnover. "Fresher retrain" and "new label" are SEPARATE factors, never bundled.
  Training internals run in `renquant-model` (CLAUDE.md boundary).
- **Objective operationally defined:** one primary trend EVENT + holding policy
  (event start/end, horizon, entry time, exit/time barrier, capacity, turnover,
  cost) and a constrained-PR / utility objective. fwd_10/20d + triple-barrier /
  multi-horizon are PRE-REGISTERED alternatives, counted in the trial ledger —
  not hidden trials.
- **Validation spine INSTANTIATED** for overlapping multi-day labels (split
  geometry + embargo > overlap, point-in-time inputs with release lags,
  effective-N/power, full trial accounting, stateful portfolio replay, measured
  costs, promote/kill thresholds). DSR on daily returns does NOT substitute for
  event recall/precision uncertainty.
- **Analyst-revision data DOWNGRADED** from "ready (283/291)" to a CANDIDATE that
  requires a DATA AUDIT + placebo first (point-in-time timestamps, vendor
  revision history, restatements, coverage-by-date, lag policy, survivorship,
  freshness, train/live parity) before it becomes an experiment factor.
- **Gate = operational CORRECTNESS problem first** (sign / calibration /
  threshold units / demean universe / train-live parity), repaired regardless of
  model strength; any change to its economic selectivity is SEPARATELY validated.
  The "~0/84" vs #200's "5.5/date overall, ~13.2 aged" denominators must be
  reconciled against the exact production stack.
- **Minute/intraday input — parked** as the LAST ablation (E-class), per the
  [SCOPED PRIOR], not asserted as a proof.

## Blocked / re-measure
A conclusive model-vs-gate split, any lever ranking, and any absolute net-edge
claim are BLOCKED on the **shared effective-sample contract** (RFC §11, matching
#200): a conservative overlap-ratio descriptor now; the real unblock is a
**pre-registered minimum-effect/power calc + an empirical dependence estimator on
a FAITHFUL homogeneous cohort — NO calendar date is implied before that calc
exists.** Sufficiency is scored in **effective non-overlapping blocks**
(`n_dates / horizon_n`, #200 `--min-eff-blocks` default 6; 30 adjacent overlapping
20-day dates ≈ 1.5 blocks → insufficient; today ≈ 0.45 blocks), with
multiple-regime coverage + block-bootstrap CIs, AND a faithful per-name PatchTST
cohort + provenance wired (#133). The earlier "≥30 fwd_20d dates (~mid-Aug-2026)"
raw-date unblock is WITHDRAWN. Re-run the PR #200 baseline only once that contract
is met.

## Scope
Direction + design only — no code/runtime change. Live tree and canonical prod
inputs untouched.
