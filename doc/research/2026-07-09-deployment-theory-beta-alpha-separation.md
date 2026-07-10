# RS: The deployment decision — beta/alpha separation and vol-targeted exposure

STATUS: research memo, r2 — theory + tuning-subset empirical results. The data
PARTIALLY REFUTES this memo's own vol-targeting prior (§4a) and surfaces a
structural finding the theory missed (§4b). Recommendation revised accordingly
(§5). [EXPLORATORY / TUNING SUBSET — eval subset untouched.]
DATE: 2026-07-09
RELATION TO RFC #443: this memo proposes a MATERIAL REVISION to the RFC's L1
formula. The RFC's L2/L3/L4 layers and all invariants are unaffected.

## 1. The thesis: 65% cash is a category error, not a calibration error

Every diagnosis so far (including RFC #443 r0-r2) treated cash drag as a
calibration problem: multipliers too aggressive, thresholds mis-scaled, Kelly
fraction too small. The deeper defect is structural:

**The system makes BETA exposure conditional on ALPHA confidence.**

Every dollar of deployment must currently pass through μ̂-derived gates (veto
floor, conviction multiplier, signal-direction, Kelly on μ̂). When the signal is
weak — which for a realized IC ≈ 0.03 model is MOST of the time — the book
holds cash. But the alternative to a weak-alpha stock position is not cash: it
is BETA (the equity risk premium), which does not require the signal's
permission. A $10.7k account holding 65% cash through a bull market paid the
equity premium as an opportunity cost for the privilege of distrusting its own
alpha — a distrust that is CORRECT about alpha and IRRELEVANT to beta.

The RFC r2 formula `E* = min(Σ shrunk-Kelly, E_ceil)` inherits a milder form of
the same error: aggregate shrunk-Kelly is a function of μ̂, so deployment still
transmits μ̂ noise (day-to-day E* jitter from estimation error) and still
under-deploys structurally whenever the calibrator compresses ER — which is the
documented, permanent state of this model family.

## 2. Theory

### 2.1 Separation (Merton 1969; Grinold-Kahn 1999)

Merton's baseline: optimal risky fraction `w* = (μ_m − r) / (γ σ_m²)` — a
constant driven by the MARKET premium, risk aversion, and MARKET variance.
Individual-name alpha appears nowhere in the deployment decision; it belongs to
the selection/tilt decision. Grinold-Kahn formalize the same split for active
management: the benchmark (beta) allocation is the default state; active tilts
scale with IC — and with IC ≈ 0.03, the theoretically justified tilt is SMALL.
The correct architecture is therefore:

- **Deployment (how much)**: a risk-budget decision on estimable quantities
- **Selection (which names)**: the signal's job — ordering, not gating
- **Tilt (how unequal)**: IC-scaled; at our IC, close to equal-weight

The current pipeline inverts this: the signal gates deployment, and deployment
noise dwarfs any alpha the tilt could add.

### 2.2 Why vol-targeting is the right deployment rule (Moreira-Muir 2017)

`E* = min(σ_target / σ̂_pf, E_ceil(regime))`

- σ̂ (realized volatility) is the one input we estimate WELL (persistence of
  vol vs near-zero persistence of μ̂) — deployment driven by σ̂ transmits
  information; deployment driven by μ̂ transmits noise.
- Moreira-Muir: scaling exposure by 1/σ̂² raises Sharpe across equity factor
  portfolios — vol-managed exposure is one of the few robust, replicated
  results in the deployment literature.
- It fails SAFE in crisis: vol spikes → E* contracts mechanically, faster than
  any regime classifier flips — and the regime `E_ceil` remains as the second,
  independent brake.
- It is auditable: E* has two inputs (σ̂_pf, σ_target), both loggable; the
  operator sets σ_target as an explicit risk-appetite number (a genuine
  operator decision, unlike a Kelly aggregate nobody can inspect).

### 2.3 What fractional Kelly is actually for (MacLean-Thorp-Ziemba 2010)

Fractional Kelly is shrinkage against parameter uncertainty in μ̂ — it belongs
to the WEIGHT decision (how unequal the tilts are), not the GROSS decision.
Using Σ(fractional Kelly) as the gross exposure conflates the two: it shrinks
beta because alpha is uncertain. Under separation, capped Kelly (or equal
weight) sets RELATIVE weights inside a vol-targeted budget.

### 2.4 Selection at small N (DeMiguel-Garlappi-Uppal 2009)

With k ≤ 8 names and noisy μ̂, 1/N is the floor any optimization must beat
out-of-sample — our own exploratory replay (PR #445) reproduced exactly this:
no allocator separated from equal-weight at the significance bar. Consistent
with theory: the value at stake is in DEPLOYMENT and PARTICIPATION, not in
weight optimization. This memo's empirical section tests whether that holds
under the full stateful/tax/integer conventions.

## 3. Proposed L1 revision to RFC #443

```
σ̂_pf   = sqrt(w'Σ̂w) of the CANDIDATE book (trailing realized vol + avg-ρ approx)
E*_raw  = σ_target / σ̂_pf
E*      = min(E*_raw, E_ceil(regime))         regime brake unchanged
E*      = hysteresis(E*, E_current, band)      churn control unchanged
```

- σ_target: operator risk appetite, set explicitly (candidate values 12-15%
  annualized; the tuning subset selects within this range, NOT the eval set).
- Weak slate semantics IMPROVE: a weak-μ̂ slate no longer collapses E* — the
  top-k by ordering still fills the risk budget (beta is preserved); only a
  thin ADMITTED set (< k names passing hard risk gates) reduces deployable
  exposure, with the parking sleeve absorbing the residual.
- Model-fault fail-closed, L2 down-only allocator, L3 executed-state invariant,
  L4 staging: all unchanged from RFC r2.
- The signal-driven variant (Σ shrunk-Kelly governor) is retained as an ARM in
  the experiment — if it empirically beats vol-targeting net of everything, the
  data overrules this memo's prior.

## 4. Empirical section — PENDING (runs tonight, tuning subset only)

Six arms under full D6 conventions (stateful lots, tax 50/32, 5bps/side,
integer execution, in-arm caps), nested-selection discipline (tuning subset
seed 20260709, frac 0.3; eval subset untouched, reserved for the post-approval
confirmatory run):

| Arm | Deployment rule | Weights |
|---|---|---|
| ew_full | always 0.95 | 1/N top-k |
| kelly_raw | none (Σ capped Kelly, unscaled) | capped Kelly |
| govern_kelly | min(Σ capped Kelly, 0.95) + hysteresis | capped Kelly |
| voltarget_ew | min(15%/σ̂_pf, 0.95) | 1/N top-k |
| voltarget_kelly | min(15%/σ̂_pf, 0.95) | capped Kelly |
| voltarget_ew_12 | min(12%/σ̂_pf, 0.95) | 1/N top-k |

Estimands: E_executed distribution, net return, net Sharpe, MDD, tax/cost
totals, turnover, cap breaches, integer residual; HAC-paired vs ew_full.

`kelly_raw` doubles as the audit of the earlier "bridge" proposal (config-only
multiplier removal): its realized Σw distribution answers, with data, what that
change would actually deploy — a number previously (wrongly) asserted by
extrapolation.

## 4a. RESULTS (149 tuning sessions, fwd_1d, full conventions) — vol-targeting prior NOT supported

| arm | mean E_dep | net ret | Sharpe | MDD | HAC t vs ew_full (p) |
|---|---|---|---|---|---|
| **ew_full** (0.95 target) | **0.523** | **+4.70%** | +0.38 | −15.8% | — |
| kelly_raw (bridge) | 0.498 | +0.62% | +0.17 | −12.1% | −0.69 (0.49) |
| govern_kelly | 0.496 | +0.58% | +0.16 | −12.0% | −0.69 (0.49) |
| voltarget_ew 15% | 0.413 | −5.08% | −0.31 | −10.3% | −1.03 (0.30) |
| voltarget_kelly 15% | 0.422 | −3.80% | −0.21 | −9.7% | −0.86 (0.39) |
| voltarget_ew 12% | 0.361 | −4.14% | −0.29 | −8.2% | −0.87 (0.39) |

- **This memo's prior is not supported on the tuning sample**: vol-targeted arms
  lose −3.8..−5.1% while the fully-deployed naive baseline gains +4.7%. They win
  60-68% of SESSIONS but lose the mean on the right tail — the classic cost of
  vol-managed exposure in a bull-heavy sample. What vol-targeting buys is MDD
  (−8..−10% vs −16%) and lower tax/turnover, not return.
- Nothing separates at significance (all |t| ≤ 1.03; PBO 0.61) — orderings are
  noise-prone; treat as hypothesis-generating.
- **The "bridge" audited**: kelly_raw deploys mean 54% (p5-p95: 20%-96%) — NOT
  the asserted "cash→10-30%". Mechanism: raw 0.3·μ/σ² wants ~2.4× leverage, so
  the 12% cap binds on 96% of sessions and Σw ≈ 0.12 × candidate breadth.
- Hysteresis is inert at 0.05 band (breadth moves E* in ~0.12 steps).
- Caveat: universe churn × asymmetric tax dominates ALL arms (137-141/149 forced
  off-universe liquidations; tax ≈ 20× linear cost) — partly a non-contiguous-
  session artifact; the eval-run design must use contiguous windows.

## 4b. The structural finding the theory missed: the BREADTH × CAP ceiling

Even ew_full — which TARGETS 95% gross — only achieves mean 52% deployed.
Median admitted breadth is ~4 names; 4 × 12% per-name cap = 48% **hard ceiling
on deployment, regardless of any E* policy**. Every deployment policy is
second-order to this identity:

```
max deployable = (admitted breadth) × (per-name cap)
```

Two levers, both OUTSIDE the L1 formula:
1. **Per-name cap** (concentration): 12% → 20-25% would let 4-5 names carry
   80-100%. Aligns with the operator's concentration mandate; it is a
   capital-risk change (single-name event risk: a −20% gap on a 25% position =
   −5% book) requiring explicit operator sign-off. Note: the June cap sweep
   (Phase 4, VOID) found "cap never binds" — TRUE under the old multiplier
   stack (2-7% positions); remove the multipliers and the cap binds 96% of
   sessions. The sweep's null was an artifact of testing the cap behind the
   compression it never got to bind against.
2. **Admission breadth** (the veto floor returns, correctly this time): A-0 was
   closed as "not binding" — TRUE for order count, FALSE for deployable
   ceiling. Its end-of-chain deployment effect is now measurable with this
   harness, which is exactly the evidence codex required before touching it.

## 5. Revised recommendation (hypotheses for confirmatory evaluation — NOT
promotions; per review, nothing in this tuning result authorizes a change)

1. **L1 candidate rule** (preregistered candidate, pending confirmatory eval):
   ride `E_ceil(regime)` — the simplest rule consistent with the tuning
   evidence. Vol-targeting retained as eval arms (hypothesis: earns its keep in
   BEAR/VOLATILE, undersampled here; candidate MDD-reducer). Σshrunk-Kelly
   dropped as the default candidate (transmits μ̂ noise; second-order to the
   breadth×cap ceiling).
2. **The breadth × cap grid** becomes the D6 Phase-2 treatment family, LOCKED
   in the protocol BEFORE evaluation: per-name cap {12%, 20%, 25%} × veto
   floor {1.0σ, 0.5σ} × weights {equal, capped-Kelly}, deployment =
   regime-ceiling; PLUS a cash/parking-sleeve control arm; evaluation on
   rolling CONTIGUOUS train/eval folds (predeclared, dependence-aware); gates
   extended with a concentration-event gate and a turnover-tax gate.
3. **Cap raise remains an operator risk decision AFTER confirmatory evidence** —
   not a result of this memo.

## 5a. Status of the committed freeze record (per review — relabeled)

`d6_freeze_20260709.json` is an **EXPLORATORY split record only**. It predates
protocol approval, predates the §5.2 treatment family, and predates the move to
contiguous windows. Its "evaluation" subset is hereby **RETIRED** — it will NOT
serve as the confirmatory evaluation set. A fresh exact-session freeze will be
generated and pushed only after RFC #443 is amended and the final D6 protocol
commits the arms, windows, costs, safety gates, and selection rule.

## 6. Decision asks (for codex discussion on this PR)

1. Accept §4b's breadth×cap ceiling as the primary finding, and the §5.2 eval
   grid as the D6 Phase-2 arm set?
2. Accept the L1 simplification (regime-ceiling-riding; vol-target demoted to
   eval arm / MDD option)?
3. Agree the per-name-cap decision route: eval quantifies → operator signs off?
4. Eval-run design: contiguous session windows to kill the churn/tax artifact —
   any objection?
