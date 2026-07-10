# RS: The deployment decision — beta/alpha separation and vol-targeted exposure

STATUS: research memo, r1 — THEORY COMPLETE, EMPIRICAL SECTION PENDING (a 6-arm
tuning-subset replay is running; results land in this PR before merge).
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

## 5. Decision asks (for codex discussion on this PR)

1. Accept the beta/alpha separation as the L1 design principle (amending RFC
   #443 §2.1 from signal-driven to vol-targeted E* with regime ceilings)?
2. σ_target as an explicit operator risk-appetite parameter — agree this is the
   correct location for the "aggressive" mandate to enter the system?
3. Agree the signal-driven governor stays as an experimental ARM (falsifiable),
   not the default?
4. Any additional arm or estimand required before this memo's empirical section
   can support the RFC amendment?
