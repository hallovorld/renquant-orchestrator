# Cash Drag Prospective Experiment Protocol

**Status:** design for review. This document authorizes neither a strategy
configuration change nor broker activity. It defines the evidence that must exist
before either can be proposed.

**Scope:** strategy 104 sizing-fidelity measurement and strategy 105 measurement
readiness. It replaces neither the Deployment Governor preregistration nor the
strategy-104 risk controls.

## 1. Decision framing

The cash-drag problem contains separate causal questions. They must not be
collapsed into a single "more invested is better" metric.

| Question | Current evidence | Decision status |
| --- | --- | --- |
| Is 104 idle cash material? | 65% mean cash over eight normal-flow sessions in the 2026-06-23 through 2026-07-09 diagnostic window ([binding-constraint memo](../research/2026-07-09-cash-drag-binding-constraints-update.md)) | Measured descriptively, not a deployment target |
| Does whole-share quantization suppress otherwise eligible 104 candidates? | The corrected replay found 7 rescued candidate-events in 6 of 11 unambiguous canonical sessions; it is retrospective and uses daily closes ([sealed-evidence interpretation](../research/2026-07-11-enablement-evidence-floor-stops-fractional.md)) | Hypothesis supported; not enable-grade |
| Did the concentration sweep identify an exposure setting? | No. It ran a QP/XGB configuration while production used greedy Kelly/PatchTST and did not vary the QP upper bound ([design-flaw audit](../progress/2026-07-09-sweep-design-flaw-audit.md)) | Void for production decisions |
| Can 105 measure pre-quantization drops? | No. Its current shadow contract records realized intents and skips but not `target_notional` ([105 scorecard record](../progress/2026-07-07-105-cash-drag-scorecard.md)) | Not measurable yet |

The proposed experiment therefore has two separate products:

1. a **104 paired, production-mirror shadow** that establishes the mechanical
   effect and safety of a one-share initiation floor; and
2. a **105 instrumentation contract** that makes the analogous estimand
   measurable before anyone proposes a 105 sizing change.

Neither product is a deployment mandate. Residual cash from a healthy but weak
signal slate is not a failure, and is handled by the separately governed parking
sleeve / Deployment Governor work.

## 2. Causal estimands and non-claims

### 2.1 104 primary estimand: sizing-fidelity delta

For every frozen, post-admission candidate decision `i`, define paired arms from
identical input state:

```
q0_i = current whole-share quantity with floor OFF
q1_i = quantity with the one-share floor ON
R_i  = 1[q0_i == 0 and q1_i == 1 and all eligibility, cap, reserve,
          normal-buy reservation, and cash checks pass]
delta_notional_i = (q1_i - q0_i) * executable_reference_price_i
```

The primary estimand is `sum(delta_notional_i) / opening_equity` over a frozen
future-only session set, reported with the count and notional of `R_i`. It measures
removal of a quantization artifact. It does **not** estimate alpha, expected return,
or the economic value of forced deployment.

The hard safety estimand is the count of ordinary buys displaced by the deferred
floor pass. Its required value is exactly zero for every valid pair. A candidate
that would violate a per-name cap, cash reserve, or the already-reserved ordinary
buy budget is not a rescue.

### 2.2 104 secondary estimand: virtual economic increment

For a rescued event, both virtual portfolios are marked from the same frozen entry
quote and future reference-price series. The event-level net difference is

```
delta_pnl_i(h) = pnl_floor_on_i(h) - pnl_floor_off_i(h) - C_i
```

where `h` is a predeclared holding horizon and `C_i` is a sealed, conservative
round-trip cost estimate derived from the pre-treatment quote/fee artifact. This
is a secondary, future-only estimate. It cannot be inferred from the retrospective
floor replay or from a higher deployed fraction.

Before the first pair is collected, the PR that arms the shadow must commit a
content-addressed cost-bound artifact containing the quote source, fee schedule,
calculation, quantile, and the non-inferiority margin. A missing artifact means
the economic endpoint is **report-only**, never enable-grade. This prevents an
author from selecting a loss tolerance after observing marks.

### 2.3 105 estimand: currently unavailable

105 cannot calculate either `q0_i` or the pre-quantization zero-drop rate from
its present records. Its scorecard correctly reports that `target_notional` and
`true_zero_drop_pre_quantization` are unavailable. No 105 cash-drag treatment,
including a one-share floor or fractional sizing, may be evaluated or enabled until
the Phase 0 contract below is present.

## 3. Frozen 104 paired-shadow design

### 3.1 Unit, arms, and input identity

The unit is one future NYSE session and its ordered decision ledger. The shadow
runner emits both arms from exactly the same:

- strategy, model, data, pipeline, execution, and orchestrator fingerprints;
- input cash, positions, open orders, risk state, session calendar, and quote
  snapshot;
- candidate order, post-admission set, and ordinary-buy reservation;
- price/cost convention and session timestamp.

The only permitted arm difference is the semantic configuration field
`sizing.one_share_floor_enabled`: baseline `false`, treatment `true`. The run
bundle must contain canonicalized configuration JSON and prove that its
field-level diff is exactly this one field. A production-mirror scorer and
admission configuration are mandatory; the currently armed PatchTST shadow is
not a valid proxy for the XGB production admission universe.

The current process is fail-closed: any missing fingerprint, different input
digest, dirty pinned checkout, calendar failure, quote failure, or arm mismatch
invalidates the whole pair and contributes neither to the denominator nor to a
success claim. Both arms remain broker-readonly.

### 3.2 Required decision-ledger contract

`renquant-pipeline` owns the sizing decision record. For each candidate it must
publish a schema-versioned record containing at least:

- immutable run/session IDs and input manifest digest;
- candidate ID, rank/order, all admission-gate outcomes, and baseline selection
  status;
- `target_notional`, unrounded quantity, `q0`, `q1`, reference price, and price
  timestamp;
- cap, reserve, available-cash, ordinary-buy reservation, and the exact reason
  a rescue was accepted or refused;
- the cumulative before/after exposure and the ordinary-buy displacement count.

This is an extension of the existing pipeline sizing authority, not a second
calculation. The current `sizing_target_notional()` implementation is already the
pre-quantization source of truth for 104, but its ledger stamp is conditional on a
non-legacy sizing mode. The paired experiment must stamp the same source value for
**both** arms, including baseline floor-OFF decisions and zero-quantity drops. A
treatment-only stamp would make a paired denominator unobservable and would invite
orchestrator-side reconstruction.

`renquant-orchestrator` owns pairing, run-bundle assembly, invalid-pair handling,
and session-level scorecards. It must consume this record, not recreate target
notional or sizing logic. `renquant-execution` owns any broker capability or
order-validation contract; this experiment performs no order submission.

### 3.3 Sampling and analysis

The protocol is future-only. The retrospective 2026-06-01 through 2026-07-10
replay and every session inspected to create it are hypothesis-generation data and
are excluded from the primary sample.

Mechanical readiness requires at least 30 qualifying candidate-events across at
least 10 valid sessions, spanning at least two calendar months if the calendar
permits. The report must include all valid sessions, including zero-rescue
sessions, and an explicit invalidation table. With zero hard-safety failures in
30 events, the exact one-sided 95% upper bound on the unobserved failure rate is
`1 - 0.05^(1/30) = 9.5%`; this is only a reliability bound, not economic power.
The report must not misstate it as evidence of positive PnL.

The report uses paired totals and cluster-robust session summaries rather than
treating multiple candidates from one session as independent market observations.
This avoids claiming independent market evidence from correlated candidates that
share one session's book, signal slate, and price environment. The paired arms
eliminate those shared inputs from the deterministic sizing comparison; they do
not eliminate serial dependence in forward market marks.
Any forward-mark economic endpoint follows the non-overlapping outcome-block and
dependence-robust rules in
`doc/design/2026-07-09-governor-prereg-replay-protocol.md`. It is not eligible for
a return-significance claim until that protocol's sample-size and effective-sample
size criteria are met.

### 3.4 Preconditions, stop rules, and decision rule

Shadow may start only after all of the following are committed and verified:

1. a clean production-mirror manifest and a one-field arm diff proof;
2. the pipeline decision-ledger schema and contract test;
3. an orchestrator paired-run bundle verifier and invalid-pair test;
4. a sealed cost-bound artifact if economic inference is requested.

Stop and classify as `INVALID`, never as a failed economic outcome, if an identity,
input, ordering, or quote invariant fails. Classify as `SAFETY_REJECT` and stop the
protocol if any valid pair shows ordinary-buy displacement, a cap/reserve breach,
an arm difference outside the feature flag, or any broker mutation.

No automatic enablement exists. A later, separate configuration PR may be considered
only when the mechanical sample completes with zero safety failures, the economic
endpoint has its precommitted cost bound and passes its own stated rule, and the
decision record explicitly names the enabled feature, expiry/review date, maximum
notional, monitoring owner, and rollback trigger. A raw deployment lift alone can
never meet this rule.

## 4. 105 Phase 0: make the question measurable

The first 105 change is an interface, not a sizing policy. `renquant-pipeline`
must emit a versioned pre-quantization sizing-intent record for the 105 decision
path. It must include the same target, price, quantity, eligibility, cap/reserve,
and reason-code fields required in Section 3.2, plus the source batch-score and
intraday state fingerprints. The pipeline unit test owns construction and schema
validation; the orchestrator integration test proves the record is persisted in the
105 session run bundle without recomputation.

This matches the current 105 boundary: the orchestrator scheduler already binds the
pipeline intraday decisioning entry point and explicitly refuses to assemble local
scoring or sizing internals. The required change is a pipeline contract extension,
followed by an orchestrator persistence consumer; it is not permission to add a
second 105 sizing path in this repository.

Once the field exists, the existing orchestrator scorecard can calculate the 105
denominator and report it by session. That measurement is a go/no-go for designing
a 105 treatment; it does not authorize one. 105 remains Stage-1/2 shadow/canary
only until its independent economic and operational gates are met.

## 5. Repository and pipeline boundaries

| Concern | Owner | Explicitly not the owner |
| --- | --- | --- |
| 104 and 105 strategy policy/configuration | `renquant-strategy-104` | orchestrator, umbrella |
| Pre-quantization sizing ledger and one-share algorithm | `renquant-pipeline` | orchestrator, execution |
| Broker capability, price/quantity validation, and live order audit | `renquant-execution` | pipeline, umbrella |
| Paired shadow schedule, run bundle, evidence join, and scorecard | `renquant-orchestrator` | strategy/pipeline internals |
| Immutable evidence storage | `renquant-artifacts` | a mutable runtime directory |

The deprecated `RenQuant` umbrella is neither a runtime input nor an implementation
target. It may appear only as historical provenance in an immutable evidence record.

## 6. Why this is not an MoE proposal

A mixture-of-experts model would alter scores, candidate ranks, admission breadth,
and therefore the experiment population. It cannot identify the effect of
whole-share rounding or a sizing floor. An MoE is a separate model-research
program: it needs model-owned training, point-in-time feature manifests, a frozen
baseline, out-of-sample evaluation, and pipeline serving compatibility. It must not
be smuggled into a cash-drag experiment as a way to increase deployment.

## 7. Required follow-on PR sequence

1. `renquant-pipeline`: publish and test the 104/105 sizing-intent contract.
2. `renquant-orchestrator`: consume the contract in a read-only, paired
   production-mirror 104 shadow runner and verify run bundles.
3. `renquant-artifacts`: seal the input manifests, arm outputs, cost-bound artifact,
   and final report.
4. Review the predeclared report. Only then may `renquant-strategy-104` carry a
   separately reviewed, default-OFF enablement change.

This order prevents the prior failure modes: wrong-path sweeps, retrospective
denominator selection, shadow/prod scorer mismatch, and a configuration toggle
being mistaken for evidence.
