# Pre-registration: equal-weight top-k deployment experiment

STATUS: pre-registration RFC (no behavior change until evaluation completes)
DATE: 2026-07-13
PRIOR: deployment governor RFC (2026-07-09) REJECTED by D6 confirmatory replay
  (PBO 0.874, all 16 candidates fail; turnover-tax gate fails every arm)

---

## 1. Motivation

The D6 confirmatory replay (PR #466) rejected the deployment governor family but
produced one actionable finding: `equal_weight_top_k` at its natural deployment
level (~0.47) beat every governor arm by +9.3% (annualized), Sharpe 0.53.

This is NOT an arming shortcut. The D6 result is a hypothesis, not a verdict:
- The eval window had zero CHOPPY/BEAR sessions
- The +9.3% may be period-specific (single BULL_CALM block)
- Turnover-tax destroyed every D6 arm; equal-weight's lower turnover may be the
  real driver (not a property of equal-weighting itself)

This document pre-registers a prospective experiment to determine whether
equal-weight top-k deployment is a durable improvement over the status quo.

## 2. Hypothesis

**H0 (null):** Equal-weight top-k at natural deployment produces the same or
worse risk-adjusted return as the status-quo sizing path (greedy Kelly +
conviction multipliers + whole-share rounding).

**H1 (alternative):** Equal-weight top-k produces higher risk-adjusted net
return, with non-degradation on drawdown, across regime types including
CHOPPY and BEAR.

## 3. Design

### 3.1 Arms (fixed, no adaptive components)

Two arms only. No dynamic components, no regime-linked algorithms, no
hysteresis. The governor's failure mode was complexity; this experiment tests
whether the simplest possible allocator wins.

| Arm | Label | Description |
|-----|-------|-------------|
| A | `status_quo` | Current production sizing: `min(0.12, 0.3 * mu/sigma^2) * conv * sig_m`, whole-share, greedy cash allocation. Unchanged from live. |
| B | `equal_weight_top_k` | Equal weight `1/k` across the top-k admitted names (k = max_concurrent_positions, regime-aware, existing). No conviction weighting, no multiplier stack. Fractional or whole-share per current mode. |

Both arms share the SAME:
- Admission chain (universe gates, wash-sale, vol gate, veto, signal direction)
- Exit logic (stops, trailing, panel exit, regime halts)
- k selection (max_concurrent_positions, regime-aware)
- Candidate ranking (panel score)

The ONLY difference is how admitted top-k names are SIZED.

### 3.2 Why equal-weight specifically

DeMiguel, Garlappi & Uppal (2009) showed 1/N beats 14 Markowitz variants
out-of-sample for N < ~50 and estimation windows < ~3000 months. Our universe
(k=5-8 names from ~104) is squarely in 1/N's sweet spot. The governor's PBO
0.874 is consistent with their finding: optimized weights overfit when the
signal-to-noise ratio is low.

Equal-weight is also structurally low-turnover: only membership changes cause
rebalancing, not weight changes from noisy mu/sigma estimates. This directly
addresses the D6 killer (turnover-tax eating 86-100% of gross).

## 4. Evaluation protocol

### 4.1 Data

- **Discovery set (shadow):** prospective daily shadow from activation date
  forward. Both arms computed daily alongside the live run; no live footprint.
- **Historical replay:** held-out window NOT previously used in D6 or any
  prior analysis. Window selected and frozen before any arm is evaluated on it.
  D6's hypothesis-generation window (2026-06-23 to 2026-07-09) is EXCLUDED.
- **Regime coverage requirement:** evaluation may NOT conclude until the shadow
  period contains at least 5 trading days each in BULL_CALM, BULL_VOLATILE, and
  CHOPPY regimes. If BEAR does not occur naturally, the historical replay must
  include at least one BEAR block. Results must be reported per-regime.

### 4.2 Primary metric

**Paired daily net return difference** (arm B minus arm A), evaluated using
Newey-West HAC standard errors (max_lag = floor(sqrt(n))).

"Net" means after:
- Transaction costs at the existing sim cost model rate
- Turnover-proportional slippage
- Lot-level tax drag on sells (existing `tax_drag()` helper)

One-sided test: H1 is that B > A.

### 4.3 Go/no-go decision rule (frozen before evaluation)

**GO** requires ALL of:

| Gate | Criterion | Rationale |
|------|-----------|-----------|
| G1 | p < 0.10 on primary metric (shadow) | Directional evidence at relaxed alpha (small sample) |
| G2 | Delta net return > 0 in at least 2 of 3 regime types (BULL_CALM, BULL_VOLATILE, CHOPPY) | Not a single-regime artifact |
| G3 | Max drawdown (arm B) <= 1.2 * max drawdown (arm A) | Non-degradation on tail risk |
| G4 | Mean daily turnover (arm B) <= mean daily turnover (arm A) | Confirm the structural turnover advantage |
| G5 | No single-name concentration > 25% at any point | Hard safety cap (equal-weight at k=4 is 25%) |
| G6 | Historical replay direction consistent with shadow (same sign on delta net return) | Out-of-sample confirmation |

**NO-GO** if any gate fails. No re-tuning, no "close enough" exceptions. A
failed experiment is a valid evidentiary outcome.

### 4.4 Minimum observation period

- Shadow: at least 40 trading days with the regime coverage requirement met
- Historical replay: at least 120 trading days (non-overlapping with D6 data)

### 4.5 Cost assumptions (frozen)

| Parameter | Value | Source |
|-----------|-------|--------|
| Base transaction cost | 5 bps round-trip | Existing sim infrastructure |
| Adverse selection | 2x base for names with daily volume < $50M | Existing sim convention |
| Tax rate (short-term) | 50% | Existing rotation convention |
| Tax rate (long-term) | 32% | Existing rotation convention |
| Slippage model | Existing sim infrastructure | No change |

## 5. Non-goals

- This is NOT a deployment governor. There is no dynamic regime-linked exposure
  algorithm, no hysteresis, no confidence scaling, no L2-L4 layer stack.
- This does NOT change the admission chain or exit logic.
- This does NOT introduce fractional shares (the arm uses whatever share mode
  is currently live — fractional if S-FRAC is enabled, whole-share otherwise).
- This is NOT alpha research. Equal-weight does not claim better stock
  selection; it claims better capital efficiency from simpler sizing.

## 6. Deliverables

| # | Deliverable | Repo | Nature |
|---|-------------|------|--------|
| D1 | This pre-registration | orchestrator | design doc |
| D2 | Shadow telemetry (arm B computed daily, logged) | orchestrator | code, read-only |
| D3 | Historical replay on held-out window | orchestrator | evaluation |
| D4 | Result memo with per-regime breakdowns | orchestrator | research output |
| D5 | Go/no-go recommendation to operator | orchestrator | decision artifact |

## 7. Rollout (if GO)

1. **S0:** Shadow (D2) — no live footprint
2. **S1:** Canary ($500, 5 trading days) — operator authorization required
3. **S2:** Full enable — operator authorization required

Kill switch at every stage: single config flag back to status quo.

## 8. Relationship to prior work

- **Deployment governor (rejected):** this experiment tests the D6 finding's
  strongest control arm in isolation. If equal-weight fails, the deployment
  problem remains unsolved — no reversion to governor candidates.
- **S-FRAC:** fractional shares improve both arms equally (less integer
  residual). This experiment is orthogonal.
- **G4 ensemble:** if ensemble changes the score ranking, both arms see the
  same ranking change. Orthogonal.
