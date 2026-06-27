# renquant105 milestone M1 — model + validation (the make-or-break gate)

2026-06-27. Part of the renquant105 suite. **This is the GO/NO-GO milestone for H1 intraday
ALPHA.**

> ## ⛔ STATUS — M1 (H1 intraday-ALPHA) is **PARKED** (reversible)
> **Phase -1 (PR #199) MEASURED the load-bearing σ_oc and the net edge is NEGATIVE at plausible
> IC** (σ_oc 152.5 std / 114-115 robust vs 220-367 bps breakeven; net −6.4 bps @ IC 0.03 / −3.4
> bps @ IC 0.05). **Do NOT build M1 absent a concrete, falsifiable reason to expect IC ≫ 0.05.**
> M1's content is **retained, not deleted** — it is the pre-registered experiment to run **only
> if** the H1-alpha path is un-parked (master §0 banner). The active path needs no M1: it is M0
> (dual-use data) + H2 (execution-timing) + the safety fixes. Treat the rest of this doc as the
> frozen design for that future un-park, not as an authorized build.

**If un-parked, this is the FIRST live-capital-relevant MEASUREMENT** of a deployable open→close
alpha edge; a measured FAIL is an acceptable, honest outcome, not a project failure.

## Objective + scope
Train an intraday model (GBDT primary + PatchTST shadow) on **open→close** triple-barrier
labels and **validate the DEPLOYABLE H1 POLICY net-of-cost** (the frozen stateful admission
path replayed on **nested outer-fold OOS** predictions; finding 1) on the **M0-CALIBRATED
MEASURED cost model — consumed here, NOT produced here; see Dependencies + finding 5**, with
**nested CPCV** / probabilistic PSR-DSR / PBO / placebo. Offline only — no shadow run, no
orders. The output is a single decision: does a placebo-clean, cost-clearing **open→close**
intraday edge exist *under the deployable stateful policy* at this size/data, yes or no — the
estimand is the policy's realized performance, NOT a per-row quantile mean (which is
diagnostic). **This is the H1 (intraday-alpha) experiment;** the H2 (execution-timing/risk)
experiment is independent and has its own milestone doc `…-H2-execution-timing.md` (master §7).

## Requirements
**Functional:**
- F1.1 Triple-barrier label builder (σ-scaled profit/stop + time barrier = the **session
  close**); **single primary horizon = open→close** (finding 2); 30min/2hr are *secondary
  diagnostics only*. **Separate overnight from intraday** (overnight gap excluded from
  label + features + PnL). Labels + forward returns are **bar-timestamped + session-aware**
  off the M0 session-horizon surface (the daily `fwd_5d`/`fwd_60d` surface is insufficient).
- F1.1b **EVENT-TIME CONTRACT — NO same-bar look-ahead (finding 1, holistic; sharpens round-3
  #1/#4).** The label and the entry are priced at the **first conservative next-executable
  quote/fill AT OR AFTER `first_eligible_fill_ts`** of the event-time chain
  (`bar_close_ts → data_available_ts → decision_ts → submit_ts → broker_ack_ts →
  first_eligible_fill_ts`; master §3), **never** the `bar_close_ts` price that produced the
  score — pricing at the closed bar inflates every IC/quantile/barrier/PnL while still passing
  purge/CPCV (the inflation is causal, not a CV artifact). The open→close return is measured from
  `first_eligible_fill_ts` to the session close. **A DELAYED-ENTRY SENSITIVITY analysis is
  mandatory:** sweep the assumed latency through the chain (best / expected / worst
  `decision→fill` lag) and report how the GO metrics degrade — a GO that survives only the
  zero-latency case is NOT a GO. **A HARD PARITY TEST** asserts training, the M1 replay, shadow,
  and live all use the **identical** event-time contract (same ts fields, same
  first-executable rule). **Until this contract holds, M1 cannot measure tradable alpha.**
- F1.2 **Embargo = the open→close label horizon IN BARS, rounded to a session boundary**
  (session-aware) + overnight-gap purge (the single most important leakage fix — getting it
  wrong reproduces the inflated-IC bug). The block scheme for the **overlapping** labels
  defines **effective-independent observations** (feeds the sample-size requirement below).
- F1.3 Train GBDT (`rank:pairwise`) primary + PatchTST/PatchTSMixer ranker shadow on the
  M0 intraday panel.
- F1.4 **Consume the M0-CALIBRATED cost model (finding 5 — NOT circular).** The cost model
  is **calibrated in M0** from the measured arrival/quote/fill sample (spread + slippage +
  IEX adverse-selection by ticker × time-of-day; impact ≈ 0 at this size) using existing 104
  fills + paper-order probes — it is an **M0 artifact that exists before M1 runs**. M1 only
  *consumes* it; the §A `11 bps` is a placeholder, **NOT** a fixed gate. Every metric reported
  **net of the measured cost model**.
- F1.4b **PRIMARY GO metric = the FROZEN H1 POLICY REPLAY on outer-fold OOS predictions in a
  NESTED CV (finding 1 — the estimand must match the deployable policy).** The pinned H1 policy
  (master §7) is a **stateful admission path**, not a per-row bucket: first-passage gate
  selection at closed-bar boundaries, a session entry cap, **no-replacement / no-reentry**,
  σ-scaled barrier exits, exhausted top-k capacity under scarcity, and repeated same-name
  opportunities. A per-row `E[return | score quantile]` mean can **PASS while the deployable
  policy LOSES** (different return AND cost distributions). Therefore:
  - The GO bar's net-Sharpe / IC / DSR / CI criteria below apply to the **exact frozen H1
    policy replayed on the OUTER-FOLD OOS predictions of a NESTED CPCV** — score calibration,
    gate thresholds, and policy selection are fit **ONLY inside each training (inner) fold**;
    the **outer fold is never seen by any fitting step** and is evaluated by replaying the
    frozen stateful policy on it (correct decision timestamps, session entry cap,
    no-reentry, barrier exits, exhausted capacity, **cost charged from the realized stateful
    path** per `H1Policy`, not `rebalances_per_day=1`).
  - **Quantile mapping is DIAGNOSTIC-ONLY.** `E[open→close return | score quantile]` from the
    purged-OOS predictions is still computed (it surfaces per-decile calibration and replaces
    the §A Gaussian edge prior with a *measured* conditional mean), but it is a diagnostic — it
    does **NOT** gate H1. Only the policy replay does.
  - **Replay/live parity contract tests (gating).** A test suite must prove the M1 replay and
    the live H1 execution path agree on: the **full event-time chain** (`bar_close_ts →
    data_available_ts → decision_ts → submit_ts → broker_ack_ts → first_eligible_fill_ts`;
    finding 1 — entry priced at `first_eligible_fill_ts`, never `bar_close_ts`), **decision
    timestamps** (closed-bar boundaries), the **session entry cap**, **no-reentry /
    one-open-per-name**, **barrier exits** (σ-scaled profit/stop + session-close time barrier),
    and **cost charging** (same `H1Policy` stateful round-trip count + the M0 cost model). A
    replay that does not match the live path on the event-time contract is not evidence for the
    live path.
- F1.5 **NESTED CPCV** harness (finding 1): score calibration + gate thresholds + policy
  selection are fit ONLY inside each inner training fold; the **frozen H1 policy is replayed on
  the held-out outer fold** to produce the OOS-Sharpe distribution. **Probabilistic PSR/DSR ≥
  0.95** (Bailey & López de Prado Deflated Sharpe — a *probability*, reconciled with PSR; the
  old vacuous "DSR>0" is dropped) on the policy-replay returns, fed the **full trial universe**
  (below), **PBO** (CSCV) on the policy-replay metric, shuffled-label + time-shift **placebo**
  — all **gating**, all on the policy replay (not the per-row quantile mean).
- F1.6 **Full trial-universe ledger (finding 3).** N counts EVERY trial across:
  horizons × labels × features × seeds × models × gate variants, **plus the prior 104/105
  trials** (the ~70–81 PatchTST runs already carry into N). This N feeds the DSR/PSR
  deflation and the multiple-testing haircut (t≈3, Harvey-Liu-Zhu).
- F1.7 **Power / MinTRL PRE-REGISTRATION — ONE frozen algorithm + immutable artifact (finding 3,
  Codex round-4: SINGULAR choices, no "e.g." / no "equivalently", required-N computed + published
  BEFORE any fitting).** The selection **ALGORITHM** and every input are fixed by this design and
  emitted as an **immutable pre-registration artifact** (hashed, committed, timestamped) **BEFORE
  any training**. Round-4 #3 corrections are folded in: the false equivalence is deleted, and each
  "alternative" choice is collapsed to exactly one:
  - **Target effect size = a net-of-cost Sharpe of 1.0 (the GO bar). NO IC equivalence is
    claimed.** *(Round-4 #3 — DELETED the false "Sharpe 1.0 ≡ IC 0.03" claim: a Sharpe↔IC
    equivalence is FALSE without a fixed score→position mapping, breadth, transfer coefficient,
    return vol, turnover, AND cost — those are not all pinned here, so no equivalence is asserted.
    IC ≥ 0.03 remains a **SEPARATE, independently-stated** acceptance threshold on the policy-
    replay rank IC, not a restatement of the Sharpe bar.)* The power calculation targets the
    **Sharpe 1.0** effect on the policy-replay net-return series, full stop.
  - **Alpha / power:** α = **0.05** (one-sided), power **1−β = 0.80**. (Pinned.)
  - **ONE moments-estimation window (pinned):** the per-observation net-return mean/variance and
    skew/kurtosis for the MinTRL non-normality correction are estimated on **the full aged
    pre-registered policy-replay return series, in ONE pass** (no rolling/expanding choice, no
    sub-window selection). Until M0 lands, the §A priors seed these inputs; **the ESTIMATOR and
    the decision rule are FROZEN NOW** and the M0-measured moments are substituted into the
    *same* frozen estimator when M0 lands (the *procedure*, *window definition*, and *decision
    function* are immutable — only the input numbers update, and the substitution is recorded).
  - **ONE block-length selector (pinned, NOT "e.g."):** the moving-block length `b` is set by the
    **Politis–White (2004) automatic selector** evaluated **once** on the pre-registered policy-
    replay return series, then **rounded UP to a whole open→close session boundary** (the F1.2
    embargo-in-bars scheme). No alternative selector and no `b ∝ n^{1/3}` fallback — the
    Politis–White output (session-rounded) is the block length, period.
  - **ONE non-normal correction (pinned):** the **Bailey & López de Prado MinTRL** skew/kurtosis
    adjustment (the PSR/DSR non-normality term) is the sole correction; no second adjustment is
    applied or chosen between.
  - **Immutable timing:** the artifact is hashed + committed + timestamped **BEFORE any model is
    fit and before any OOS prediction is generated**. The required **N_eff is COMPUTED AND
    PUBLISHED at pre-registration time** from the frozen (α, power, moments-estimator, block
    selector, MinTRL) tuple — **not** "before training" in the abstract: a concrete number is in
    the committed artifact. When M0 supplies measured moments, N_eff is **recomputed by the same
    frozen estimator** and the new number recorded; the rule that compares N_eff to available
    history is **immutable** and was fixed here.
  - **Resulting N_eff:** the MinTRL minimum track-record length in **effective-independent
    observations** that the frozen tuple implies, NOT a raw date count.
  - **FALLBACK when required N exceeds available history (mandatory):** if the published N_eff
    exceeds the available aged history, **declare the experiment UNDERPOWERED → do NOT run M1 /
    re-scope** (extend the aged window, widen the universe, or stop). **Never shrink the bar to
    fit the data.** The underpowered declaration is recorded in the artifact.
  Phase gates use **CIs + effective N** against this pre-registered N_eff.
**Non-functional:** reproducible; deseasonalized targets (intraday U-shape); average-
uniqueness weighting on overlapping labels.

## Deliverables
Intraday model artifacts (GBDT + PatchTST) + calibrator + WF-gate metadata; the
Alpaca/IEX cost model; the **frozen H1 policy-replay harness + the replay/live parity contract
tests (finding 1)**; the **validation report** (nested-CPCV policy-replay OOS-Sharpe
distribution, DSR, PBO, placebo deltas, net-of-cost Sharpe, IC + decay, **plus the
diagnostic-only `E[return|quantile]` calibration table**) with the trial count.

## Metrics / KPIs
**Primary (gating):** the FROZEN H1 POLICY-REPLAY metrics on nested outer-fold OOS — policy-
replay OOS rank IC at the **open→close** horizon (placebo-clean), policy-replay net-of-cost
Sharpe, probabilistic **PSR/DSR**, PBO, policy-replay hit-rate, cost-as-%-of-gross-alpha
(charged from the stateful path), IC decay half-life — all at the open→close horizon (NOT
`fwd_5d`). **Diagnostic-only (non-gating):** `E[open→close return | score quantile]` per-decile
calibration.

## Acceptance criteria (the GO bar — ALL must pass)
**All net-Sharpe / IC / DSR / CI criteria are measured on the FROZEN H1 POLICY REPLAY on
NESTED outer-fold OOS predictions (F1.4b), NOT on the per-row `E[return|quantile]` mean (which
is diagnostic-only).** The bar is the deployable stateful policy's realized performance.
| Criterion | Threshold |
|---|---|
| **Policy-replay** OOS rank IC @ **open→close** horizon | ≥ **+0.03**, placebo-clean (above the shuffled-label floor by a clear margin) |
| **Policy-replay** net-of-cost Sharpe (nested CPCV, **measured** cost charged from the stateful path) | ≥ **1.0** |
| **Probabilistic PSR/DSR** (Bailey & LdP) on the policy-replay returns, at the full trial N | **≥ 0.95** (the old "DSR>0" is dropped as vacuous) |
| PBO (CSCV) on the policy-replay metric | **< 20%** |
| **Policy-replay** net-PnL block-bootstrap 95% CI | lower bound **> 0** (block ≥ open→close label horizon) |
| Sample | ≥ the **power/MinTRL-derived minimum in effective-independent observations** (F1.7), not a raw date count |
| **Event-time contract + delayed-entry sensitivity** (F1.1b, finding 1) | label/entry priced at `first_eligible_fill_ts` (NOT `bar_close_ts`); GO metrics survive the delayed-entry latency sweep (best/expected/worst), not just zero-latency |
| **Replay/live parity** (contract tests, F1.4b) | the full **event-time chain**, timestamps, session cap, no-reentry, barrier exits, and cost charging MATCH between the M1 replay and the live H1 path |
| Quantile mapping `E[return|quantile]` | **diagnostic-only** (reported for calibration; does NOT gate) |

## Expected outcome (预期) + kill condition
**Honest prior (§A): UNDETERMINED / marginal.** The unit-corrected open→close prior is
*marginal-to-plausibly-viable* (top-pick gross edge ≈ or > the ~11 bps cost at IC 0.03–0.05 /
σ_oc in the assumed sensitivity range ~200 bps; the FL net-Sharpe lens is more pessimistic — the
**HONEST band is ~−1.30 to −0.98 over the honest IC band 0.01–0.03 ONLY** (upper bound ≈
0.476−1.455 ≈ −0.98); the **−0.66** figure is a **SEPARATE optimistic IC=0.05 reference**, NOT
the band's upper bound — finding 6). So M1 is a real test with a genuinely uncertain result —
NOT a foregone FAIL and NOT a foregone GO. **KILL CONDITION:** if the measured GO bar is not
cleared (on the **policy replay**, finding 1), **STOP — intraday
alpha trading stays OFF**, and the project falls back to the defensible residual (H2
execution-timing + intraday risk on the daily book; master §0). Do NOT ship a cost-negative
book. A measured pass unlocks M2.

## Dependencies / inputs
M0 (clean intraday panel **+ the M0-calibrated measured cost model + the measured
arrival/quote/fill sample** — finding 5, so the cost gate is not circular); `renquant-common`
CPCV / purged-CV / WF tooling; the trials ledger.

## Risks (FMEA subset)
Overfitting (multiple-testing across ~70–81 prior PatchTST trials → DSR mandatory);
overlapping-label leakage (purge/embargo in bars); the IEX adverse-selection penalty
(1–3 bps/leg) eating the entire net edge → may need SIP before a fair test.

## Effort
~3–5 weeks (label design + cost model + CPCV harness + train + the validation report).
The validation discipline, not the training, is the work.
