# renquant105 milestone M2 — gates + shadow e2e (no live orders)

2026-06-27. Part of the renquant105 suite. **Only entered if M1 passed.** Still **zero
live orders** — shadow/observe only.

## Objective + scope
Build the stricter conjunctive gate stack + the new gates, wire the decision ledger,
run 105 end-to-end in **shadow mode** (`alpaca_shadow`/`readonly-alpaca`, no orders),
stand up the **champion-challenger shadow model** and the **daily retrospective**, and
prove the gate stack actually prevents unreliable trades.

## Requirements
**Functional:**
- F2.1 **Wire `GateRegistry.persist()` / the #133 decision-ledger** (the keystone — it
  unblocks the shadow comparison, the gate counterfactual, and the IS attribution;
  collect-only today).
- F2.2 The G1–G8 stack (master spec §4): G1 cost-edge (`net_alpha > k·RT_cost`, live
  spread), G2 conformal lower-bound (ACI/block — intraday non-exchangeable), G3 **entry
  meta-label** (P(profit)≥τ — highest-leverage new gate, symmetric to the existing exit
  veto), G4 **CHOPPY→no-trade** (ADX>20 / ATR%), G5 vol/spread/freshness, G6 risk budget
  + **P&L daily-loss circuit breaker** (104 gap) mapping to **`NO_NEW_RISK`** (blocks new
  buys, **allows** reduce-only/cancel exits — NOT `TRADING_OFF`/all-orders-off; finding 7),
  G7 top-k under scarcity, G8 kill-switch state machine + max-deviation slippage reject.
- F2.3 **Reliability blockers (close before any live):** `client_order_id` dedup on the
  equities path (F29); a **run-lock** (F37); **intraday-granular DataFreshnessGate** (F1/F20);
  broker submit try/except + reconciliation (F30).
- F2.4 Champion-challenger via **MLflow aliases** (`@champion`/`@challenger`, `validation_status`
  tag); shadow scores logged with realized forward returns.
- F2.5 The **daily 复盘** job (IS attribution, gate counterfactual, rolling-IC + decay,
  realized-vs-expected slippage, regime/time-of-day slicing, champion-vs-shadow) + the ntfy line.
**Non-functional:** zero live orders; fail-closed defaults; everything observable via the ledger.

## Deliverables
The wired decision ledger; the G1–G8 gate stack; the reliability fixes (dedup/run-lock/
daily-loss-breaker/intraday-freshness); the shadow-model loop (MLflow aliases); the daily
retrospective report + ntfy; the implementation-shortfall module.

## Metrics / KPIs
Gate-stack precision (P(**open→close return**>0|selected)); killed-winner rate; selection
edge (selected_mean − vetoed_mean); **two distinct comparators (execution-plan gap):**
(a) **pipeline parity** = champion-vs-itself order-intent agreement (does the shadow pipeline
reproduce the live one?), (b) **strategy lift** = challenger-vs-champion (does the new model
add edge?) — these are different questions and must not be conflated; **per-gate marginal
contribution** (ablation, multiplicity-corrected); false-positive-trade rate.

## Acceptance criteria (gate to M3)
| Criterion | Threshold |
|---|---|
| Gate-stack precision | ≥ **0.55** (on the **open→close** label, not fwd_5d) |
| Killed-winner rate | ≤ **15%** (blocked names whose open→close return was top-tercile) |
| Selection edge | > 0 with a **block-bootstrap 95% CI lower bound > 0** over the effective-N sample (not "≥80% of 21 runs") |
| **Pipeline parity** (champion vs itself) | order-intent agreement ≥ **90%**, score rank-corr ρ ≥ **0.9** |
| **Strategy lift** (challenger vs champion) | positive marginal IC with a CI lower bound > 0 (separate from parity) |
| **Per-gate ablation** | each retained gate shows positive marginal contribution, **multiplicity-corrected** (not just a conjunction-level placebo) |
| Sample | ≥ the **power/MinTRL-derived minimum in effective-independent observations** (not "20 runs") |
| Reliability blockers | dedup + run-lock + daily-loss-breaker(→NO_NEW_RISK) + intraday-freshness **closed** |
| FP-trade SLO | ≤ **0.5%**, **zero** duplicate/stale-price orders |

## Expected outcome (预期) + kill condition
A validated, observable, fail-closed gate stack the shadow demonstrates prevents
unreliable trades, plus a working champion-challenger loop + daily 复盘. **Kill:** if the
shadow shows the gates kill winners (killed-winner > 15%) or the e2e is cost-negative,
**do NOT proceed to live** — return to M1 / re-scope.

## Dependencies / inputs
M1 pass; the #133 ledger; 104's shadow scorer + readonly-e2e harness; MLflow.

## Risks (FMEA subset)
Non-independent gates → false confidence (verify with placebo that the conjunction
raises *realized* precision, not just shrinks coverage; gate-independence matrix); the
dedup/run-lock gaps (highest-RPN reliability rows); killed winners (the BULL_CALM
panel-exit precedent).

## Effort
~4–6 weeks (ledger wiring + 6 new gates + reliability fixes + the retrospective +
shadow loop). The ledger wiring + IS module are the long poles.
