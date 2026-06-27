# renquant105 milestone M2 — gates + shadow e2e (no live orders)

2026-06-27. Part of the renquant105 suite.

> ## ⛔ STATUS — M2 (H1 intraday-ALPHA gates) is **PARKED** (reversible)
> M2 is entered only if M1 passes, and **M1 is PARKED** (Phase -1 #199 measured net edge negative
> at plausible IC; master §0 banner) — so M2's alpha-gate work is **not built now**, retained for a
> future un-park. **Exception:** the H2.0 arrival-price/IS capture that M2 *consumes* is on the
> independent ACTIVE branch (it does NOT depend on M1/M2) and proceeds for H2.

**Only entered if M1 passed** (the H1-alpha chain — currently PARKED).
Still **zero live orders** — shadow/observe only. **Note (finding 2):** the H2.0 arrival-price/IS
capture and the H2 execution-timing milestone are **NOT** gated by M1/M2 — they run on the
independent parallel branch of the acyclic DAG (master §7.0); M2 only **consumes** H2.0's IS
module, it does not own it. So "only entered if M1 passed" applies to the M2 alpha-gate work, not
to H2/H2.0.

## Objective + scope
Build the stricter conjunctive gate stack + the new gates, wire the decision ledger,
run 105 end-to-end in **shadow mode** (`alpaca_shadow`/`readonly-alpaca`, no orders),
stand up the **champion-challenger shadow model** and the **daily retrospective**, and
prove the gate stack actually prevents unreliable trades. **M2 CONSUMES the
implementation-shortfall module from H2.0 (finding 2) — it does NOT own/deliver arrival-price
capture** (that moved to the independent H2.0 milestone so H2 is not blocked on M1/M2; master
§7.0 DAG). Gates are classified by the §4 **taxonomy** (finding 4): alpha/admission gates are
validated by nested-OOS ablation; **safety invariants are NEVER optimized on PnL**.

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
- F2.5 The **daily 复盘** job (IS attribution **via the H2.0 IS module — consumed, not built
  here; finding 2**, gate counterfactual, rolling-IC + decay, realized-vs-expected slippage,
  regime/time-of-day slicing, champion-vs-shadow) + the ntfy line.
- F2.6 **Gate taxonomy tagging + validation routing (finding 4).** Each of G1–G8 is tagged
  `alpha/admission` | `portfolio constraint` | `safety invariant` (master §4 table). Alpha gates
  → nested-OOS ablation; portfolio constraints → feasibility tests; safety invariants → fault
  injection + invariant/property tests + zero-tolerance incident SLOs (reliability §4/§5).
  **Safety invariants are never required to show marginal alpha and are never PnL-optimized.**
**Non-functional:** zero live orders; fail-closed defaults; everything observable via the ledger.

## Deliverables
The wired decision ledger; the G1–G8 gate stack **with each gate tagged by class
(alpha/admission | portfolio constraint | safety invariant; finding 4)**; the reliability
fixes (dedup/run-lock/ daily-loss-breaker/intraday-freshness); the shadow-model loop (MLflow
aliases); the daily retrospective report + ntfy. **The implementation-shortfall module is
CONSUMED from H2.0, not built here (finding 2).** The **EXACT-parity reconciliation report**
(finding 5): the enumerated list of every allowed champion-vs-itself difference, all reconciled.

## Metrics / KPIs
Gate-stack precision (P(**open→close return**>0|selected)); killed-winner rate; selection
edge (selected_mean − vetoed_mean); **two distinct comparators (execution-plan gap), measured
DIFFERENTLY (finding 5):**
(a) **pipeline parity** = champion-vs-itself — a deterministic shadow repro of the SAME
model/data/config/clock/policy must agree **EXACTLY (100%) at the decision-contract level**, NOT
"90% intent agreement" (10% disagreement on a same-system deterministic repro hides
timestamp/data/nondeterminism defects). Parity is checked field-by-field: **eligible universe**
(exact set), **features / fingerprints** (exact), **scores** (within a stated numeric
tolerance), **gate verdicts** (exact), **target sizes** (exact), **intents** (exact). Every
allowed difference is **enumerated and reconciled** in the parity report; an unreconciled
disagreement FAILS parity.
(b) **strategy lift** = challenger-vs-champion (does the new model add edge?) — **this is the
ONLY place statistical correlation / agreement thresholds (ρ, ≥X% agreement) apply**; never to
same-system parity.
**Per-gate marginal contribution** is computed **only for the alpha/admission class** (finding
4 — safety invariants are NOT scored on alpha): ablation, multiplicity-corrected; safety
invariants are verified by fault injection + property tests (reliability §4) instead.
False-positive-trade rate.

## Acceptance criteria (gate to M3)
| Criterion | Threshold |
|---|---|
| Gate-stack precision | ≥ **0.55** (on the **open→close** label, not fwd_5d) |
| Killed-winner rate | ≤ **15%** (blocked names whose open→close return was top-tercile) |
| Selection edge | > 0 with a **block-bootstrap 95% CI lower bound > 0** over the effective-N sample (not "≥80% of 21 runs") |
| **Pipeline parity** (champion vs itself — EXACT, finding 5) | **100% (exact) agreement** at the decision-contract level: eligible universe (exact set), features/fingerprints (exact), scores (within a stated numeric tolerance), gate verdicts (exact), target sizes (exact), intents (exact). Every allowed difference **enumerated + reconciled** in the parity report; any unreconciled disagreement FAILS (the old "≥90% / ρ≥0.9" is WRONG for a same-system deterministic repro) |
| **Strategy lift** (challenger vs champion) | positive marginal IC with a CI lower bound > 0 (separate from parity; **the ONLY comparator that uses statistical correlation/agreement thresholds**) |
| **Per-gate ablation (ALPHA gates only — finding 4)** | each retained **alpha/admission** gate shows positive marginal contribution, **multiplicity-corrected**; **safety-invariant** gates are NOT alpha-scored — verified by fault injection + invariant/property tests + zero-tolerance incident SLOs (reliability §4/§5) |
| Sample | ≥ the **power/MinTRL-derived minimum in effective-independent observations** (not "20 runs") |
| Reliability blockers | dedup + run-lock + daily-loss-breaker(→NO_NEW_RISK) + intraday-freshness **closed** |
| FP-trade SLO | ≤ **0.5%**, **zero** duplicate/stale-price orders |

## Expected outcome (预期) + kill condition
A validated, observable, fail-closed gate stack the shadow demonstrates prevents
unreliable trades, plus a working champion-challenger loop + daily 复盘. **Kill:** if the
shadow shows the gates kill winners (killed-winner > 15%) or the e2e is cost-negative,
**do NOT proceed to live** — return to M1 / re-scope.

## Dependencies / inputs
M1 pass; the **H2.0 IS module** (consumed, owned by H2.0 — finding 2); the #133 ledger; 104's
shadow scorer + readonly-e2e harness; MLflow.

## Risks (FMEA subset)
Non-independent gates → false confidence (verify with placebo that the conjunction
raises *realized* precision, not just shrinks coverage; gate-independence matrix); the
dedup/run-lock gaps (highest-RPN reliability rows); killed winners (the BULL_CALM
panel-exit precedent).

## Effort
~4–6 weeks (ledger wiring + 6 new gates + reliability fixes + the retrospective +
shadow loop). The ledger wiring + IS module are the long poles.
