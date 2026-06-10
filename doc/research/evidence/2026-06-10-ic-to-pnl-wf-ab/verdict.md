# Stage-A A2 on the real WF manifold — reality check (NOT a promotion; gate correctly blocked)

**Date:** 2026-06-10 · **Purpose:** the operator-approved step from the synthesis — take Stage-A A2 through the *real* step-4g A/B (true WF ConstraintSnapshots, DSR/PBO), dropping the diagnostic minimal-snapshot.
**Status:** **Honest negative.** The promotion gate **correctly blocked** the whole comparison as not decision-grade. The earlier "A2 ≫ QP" finding does **not** transfer to production as-is. Two real gaps are now exposed. Live unchanged.

## What the real gate returned

Run: `run_ab_replay --wf-artifact-root data/sim_runs.db --start-cut 2024-01-02 --end-cut 2026-03-27 --fwd-horizon-days 1`, 497 bars, full production ConstraintSnapshots.

| allocator | Sharpe | hard-constraint violations | promotable? |
|---|---|---|---|
| hybrid_option_f | 2.30 | 0 | (gate blocked, see below) |
| current_qp | 2.27 | 55 (cash_budget 2, dw_max 53) | **rejected** |
| inverse_vol | 1.97 | 0 | — |
| equal_weight | 1.91 | 0 | — |
| **stage_a_a2_long_only** | **1.67** | **497 (dw_max, every bar)** | **rejected** |

**Verdict: `promotion_candidate: null`, `next_action: iterate`, rationale "not decision-grade: replay snapshots are missing required constraint families."**

## The two real gaps the gate exposed (which the diagnostic hid)

1. **A2's daily form violates the per-bar turnover cap (`dw_max`) on every bar.** Daily A2 re-solves the whole book from scratch, so each bar's Δw blows the slippage band. This is not a surprise — it is the *quantified* version of the E2 finding that A2 must be **horizon-held (~3-bar)**; the daily floor I registered is not deployable as-is. A constraint-aware, horizon-held A2 is required before any real comparison.

2. **The WF manifold itself is not decision-grade.** Even the incumbent QP is rejected (55 violations: cash_budget, dw_max), and the harness flags `decision_grade_constraints: False` — the `sim_runs.db` candidate snapshots are **missing required constraint families**. This is the same constraint-fidelity gap that roadmap P0#0 step-4g has been blocked on; no allocator can earn a promotion verdict on this manifold until the snapshots carry the full constraint set.

## The honest correction to the synthesis

My earlier "A2 ≫ QP" conclusion was **specific to the diagnostic environment** (minimal long-only snapshot + the clean PatchTST signal) and does **not** survive contact with the real gate:

- On the **real WF manifold + GBDT signal**, the QP is healthy (**Sharpe 2.27**), not the flat-to-negative it showed on the clean PatchTST signal under a minimal snapshot. The negative-QP result was environment-specific (minimal snapshot let A2 ignore constraints A2 cannot actually ignore; and QP appears tuned to the GBDT signal it runs on).
- A2's apparent dominance came partly from **ignoring constraints** the minimal snapshot did not impose. Under real `dw_max` it violates every bar.

This is exactly why the synthesis withheld a promotion claim and routed through the gate. The gate did its job: it rejected an under-constrained comparison rather than rubber-stamping it.

## What it would take to get a real verdict (the actual next steps)

1. **A constraint-aware, horizon-held A2 allocator** that respects `dw_max`/sector/corr (e.g. A2 target projected through the ConstraintSnapshot, rebalanced on the E2 ~3-bar cadence with a GP-glide). The current `alpha_tilt_long_only` is a measurement instrument, not a deployable allocator.
2. **A decision-grade WF manifold**: snapshots carrying the full constraint families (the P0#0 step-4g constraint-fidelity work), or a PatchTST WF manifold (still blocked on the renquant-backtesting PatchTST WF-sim path).
3. Only then does an A2-vs-QP promotion verdict mean anything.

## Bearing on the operator decision

The approval to "take A2 through the gate" is honored — and the gate's answer is **"not yet, and here is precisely why."** No live change is warranted. The robust takeaways that survive are narrower than the synthesis implied:

- The **stop-layer** finding (E1) and the **horizon** finding (E2: ~3-bar, daily is too churny) are corroborated — the latter is now confirmed by the `dw_max` violations.
- The **"A2 beats QP" magnitude is not established on production constraints** and should not be cited as such until steps 1–2 above are done.

Live stays unchanged. Recommend the operator pick between: (a) build the constraint-aware horizon-held A2 + fix the WF manifold constraint fidelity (a multi-step engineering effort), or (b) park the IC→Sharpe production push here with the measurement findings documented, and return to the original priorities (daily full-run / retrains / decoupling).

Reproduction: `verdict.json` committed alongside.

Agent-Origin: Claude
