# GOAL-1 closeout: AC2's structural finding and the AC4 decision package

STATUS: AC2 and AC4 delivered; with AC1 merged (#1028) and AC3 honoured
throughout (no config change shipped from Stage 0), **GOAL-1's measurement
programme is complete**. What remains is the capital decision itself, which
is the operator's by hard gate.

## AC2: a return-based cap comparison is STRUCTURALLY unavailable — not underpowered

The plan was Stage 1 = compare forward returns under cap variants, gated on
ESS. The measurement kills the plan at a level deeper than power:

1. **Counterfactual entries have no realized outcomes.** History ran cap 8
   only; the names a higher cap would have admitted were never bought, so
   there are no fills, no exits, no realized P&L — only forward-return
   proxies that ignore execution, wash-sale interactions, and the cash-path
   coupling between positions.
2. **Even the proxy is empty.** Of 467 cap-cut admissible names across live
   history, 50 have an `fwd_20d` proxy (the backfilled window is narrow), on
   10 sessions, and the non-overlapping ESS at h=20 is **n_eff = 1**
   [VERIFIED — runs DB, 2026-08-24].

A statistical comparison that cannot be constructed is not "pending more
data" at any horizon the book trades. AC3 anticipated exactly this shape:
**the cap decision is mechanical evidence + operator judgment**, and stating
so is AC2's honest deliverable.

## AC4: the recommendation, with every cost named

**Recommended: raise `max_concurrent_positions` 8 → 10 and enable fractional
sizing IN THE SAME change**, per the S-FRAC enablement contract's own steps.

Mechanical evidence (AC1 v3 grid, production-seam parity 2.3e-5, era-gated):

| | cap 8 (today) | cap 10 | cap 15 |
|---|---:|---:|---:|
| median deployment, integer | 17.3% | **32.6%** | 44.6% (saturated) |
| median deployment, fractional | 20.3% | **35.2%** | 47.3% |
| price tilt, integer | 1.28× | 1.20× | **1.40×** |
| price tilt, fractional | 1.00× | 1.06× | 1.10× |

Why 10 and not 15: the marginal deployment from 10→15 (+12pp) is bought with
the worst integer-tilt regime (1.40×) and thinner per-name tickets; 8→10
captures the bulk of the unmet admissible demand (20–27 names/session vs 0–2
free slots) at the smallest structural change.

**Costs and couplings, named (the AC4 requirement):**
- **Ticket size**: at ~$10.9k equity, cap 10 → typical per-entry notional
  falls; under INTEGER sizing this amplifies the orch#608 anti-high-price
  exclusion — which is why the cap must not move without fractional.
- **Concentration**: per-name max weight unchanged (regime-capped), but the
  realized book spreads thinner; idiosyncratic single-name risk falls,
  factor-crowding risk (more names from the same admitted cohort) rises.
- **Wash-sale surface**: more names held → more lots → broader wash-sale
  interaction surface (renquant-pipeline#223's missing materiality floor
  becomes marginally more expensive).
- **Fractional readiness** [all VERIFIED today]: execution-side support
  exists (`renquant_execution/execution.py`, `live_commit.py`); the
  `floor_eligible_*` evidence counters are LIVE in production runs; the
  enablement bit and its documented preconditions live in strategy-104
  (`execution.fractional_shares.enabled`, broker-guard + sizing-fidelity
  steps per the S-FRAC v2 contract). Those contract steps are the checklist
  for the change PR — not bypassed here.

**The exact change, for when the operator decides** (strategy-104, one PR,
reviewed): `max_concurrent_positions: 8 → 10`;
`execution.fractional_shares.enabled: false → true` after its contract's
broker-guard verification, with `_reason` notes on both lines. **This
document does not make that change** (AC3; landing actions are ask-first).

## GOAL-1 ledger

| AC | state |
|---|---|
| AC1 mechanical grid, reproducible | ✅ merged (#1028, v3 with parity + provenance) |
| AC2 ESS before any return rule | ✅ this doc — the rule is structurally unavailable, stated as the finding |
| AC3 no config change from Stage 0 | ✅ honoured throughout |
| AC4 recommendation with named costs | ✅ this doc |
