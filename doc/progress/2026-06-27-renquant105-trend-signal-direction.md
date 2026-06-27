# renquant105 — repointed to multi-period trend-signal recall + precision

2026-06-27.

## What & why
renquant105's prior intraday / day-trading design suite was wrong-framing and is
closed (#199, #416 closed; #198 to be superseded). The operator confirmed the
real goal: catch MORE real trends (recall) and MORE-ACCURATELY (precision),
traded as multi-day holds for the trend's duration — NOT intraday / HF /
day-trading. This doc records that grounded direction so the next session starts
from the evidence, not the closed framing.

**This RFC is a PROPOSAL. It does NOT authorize retraining and does NOT
establish a lever ranking.** It records corrected (regraded) evidence, marks
model-vs-gate UNDETERMINED, operationally defines the objective, instantiates the
validation spine, and pre-registers a factorial experiment + data-audit contract
that will MEASURE the direction. (Reframed per Codex CHANGES_REQUESTED on PR
#201 — the earlier draft overstated the literature and asserted a lever order on
evidence it admitted was too thin.)

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
  - **[DATA·THIN]**: PR #200 ledger too short/impaired (fwd_20d = 11 aged dates,
    ~1–2 independent blocks; fwd_60d = 0; sim rows unfaithful/excluded); IC
    at/below the ~0.036 shuffled floor; the killed-winner decomposition is
    parameter-dependent / scorer-mixed / non-causal → does NOT set a stable
    model-vs-gate ratio.

## Decision / direction
- **Model vs gate = UNDETERMINED.** The "MODEL ~3.6× bottleneck" ordering is
  withdrawn. Defensible conclusions only: (a) provenance inadequate, (b) live
  gate often admits nothing, (c) model quality unmeasured. Observability + gate
  correctness may proceed IN PARALLEL with model work; neither establishes a
  ranking.
- **No asserted lever order.** Replaced by a pre-registered FACTORIAL (A baseline
  / B fresh-data-only / C trend-label-only / D both / E orthogonal analyst
  feature on the winning base) under one shared trial ledger, identical folds /
  universe / cost / turnover, paired OOS policy returns + recall/precision lift
  with multiplicity control. "Fresher retrain" and "new label" are SEPARATE
  factors, never bundled. Training internals run in `renquant-model` (CLAUDE.md
  boundary).
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
claim are BLOCKED until live ages to ≥30 fwd_20d dates (~mid-Aug-2026) OR
faithful per-name PatchTST score history + provenance is wired (#133
follow-through). Re-run the PR #200 baseline then.

## Scope
Direction + design only — no code/runtime change. Live tree and canonical prod
inputs untouched.
