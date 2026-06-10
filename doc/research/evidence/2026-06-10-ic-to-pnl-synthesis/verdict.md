# IC → Sharpe: investigation synthesis + production recommendation

**Date:** 2026-06-10 · **Closes:** the IC→Sharpe RFC investigation (`doc/research/2026-06-10-ic-to-pnl-architecture.md`) experiments E1–E4 on the verified clean signal.
**Status:** Decision document for the operator. Strong directional evidence on which to base a production experiment; **not itself a promotion** (promotion still gates on WF + DSR/PBO).

## The question and the one-line answer

Operator: *"PatchTST IC ≈ 0.1 but realized APY/Sharpe are terrible — the decision tree wastes the IC."*

**Confirmed, quantified, and fixable.** The IC is real but smaller than stated (placebo-clean OOS **+0.0724**, not 0.1). The current decision tree destroys most of it — the single-day-loss stop and the QP allocator are the two ranked destroyers. A direct rank→weight long-only book (Stage A "A2") held on a **~3-day** cadence converts the same signal to a measurement Sharpe of **~2.6**, versus the production path which goes flat-to-negative on it.

## The evidence chain (all on the verified signal, all reproducible)

| Experiment | Finding | Evidence |
|---|---|---|
| **P0** clean IC | OOS IC **+0.0724**, sanity battery PASS (leak-free) — the operator's "0.1" corrected | renquant-model #37/#38 |
| **E1** TC ladder | A2 long-only **1.85**; single-day-loss stop = largest destroyer (1.46→0.26); QP long-only **+0.21** ≪ A2; admission floor −0.41; H-B (scalar overlay) TC-neutral | `2026-06-10-ic-to-pnl-E1-clean-patchtst/` |
| **E3** breadth | admission floor collapses effective breadth **2.44→1.58 bets** | pipeline #70 |
| **E2** A0 horizon | dollar-neutral ceiling peaks at hold≈5 (0.49), **negative at 60d** — label horizon ≠ holding horizon | `…-E2-horizon-clean/` |
| **E2** A2 horizon | **deployable A2 long-only peaks at hold≈3 (Sharpe 2.59)**, positive at every horizon | this dir, `e2_a2_results.csv` |

A2 long-only horizon profile (clean signal, measurement instrument):

| hold (bars) | 1 | 3 | 5 | 10 | 20 | 40 |
|---|---|---|---|---|---|---|
| Sharpe | 1.99 | **2.59** | 2.32 | 2.13 | 1.75 | 2.24 |
| TC | 0.92 | 0.70 | 0.66 | 0.57 | 0.48 | 0.37 |

## Why the decision tree wastes the IC (mechanism, not just numbers)

1. **Daily path-dependent stops on a fast-decaying signal** are whipsaw, not protection (E1 −1.20 Sharpe; live +3.6pp post-exit regret). Han-Zhou-Zhu: stops help in momentum-crash states, not calm-bull.
2. **The QP optimizer** turns the clean signal flat-to-negative (E1 +0.21 long-only) — its complexity is not paying for itself here; it is the §8 "does QP beat the simplest rule" question answered *no* on this signal.
3. **Hard admission floors** coarsen a continuous rank and collapse breadth (E3 2.44→1.58), costing √BR.
4. **Horizon mismatch**: the book was managed against a 60-day label while the tradeable alpha lives at ~3 days (E2). Holding to the label horizon is value-destroying.

## Recommended production experiment (operator decision required)

A single, well-scoped candidate to take through the **real** gate (WF + step-4g replay, DSR/PBO, per-regime):

> **"Stage-A A2": long-only α-tilt (w ∝ positive cross-sectional z(score)), ~3-day rebalance with a Gârleanu-Pedersen cost-aware glide, a scalar vol-target/drawdown overlay, and hard stops demoted to safety-only (true blow-up / wash-sale / liquidity). QP retired from the selection path.**

Rationale: every component is an E1–E4 finding, not a guess. The expected failure modes are pre-registered (RFC §5.6): if the WF/DSR-PBO run does not reproduce the measurement ranking, the decomposition was incomplete — that is itself a finding, and no production change ships without it.

**What this is NOT:** not a claim that live Sharpe will be 2.6 (measurement instrument, minimal long-only snapshot, single holdout, gross of tax). The robust, snapshot-independent claims are the *orderings*: A2 ≫ QP, stops destroy, breadth matters, horizon ≈ 3d ≪ 60d.

## The three standing caveats (every number above inherits them)

1. Minimal long-only snapshot — not a production decision-trace reproduction.
2. Single fixed OOS holdout — not walk-forward; promotion gates on WF + DSR/PBO.
3. 1-day PnL, gross of tax — absolute Sharpes are benchmarks; the orderings are the result.

## Decision points for the operator

1. **Approve building the Stage-A A2 candidate** into the WF gate + step-4g replay for a promotion-grade DSR/PBO verdict? (This is the path from measurement to a real trading decision.)
2. **PatchTST WF-gate path** is still broken (renquant-backtesting follow-up) — a promotion-grade A2 run on PatchTST needs it fixed, or the candidate can be evaluated on the GBDT signal first (whose own placebo status is the separate M6 question).
3. Until a candidate clears the gate, **live stays sell-only / unchanged** — this investigation does not authorize any live change by itself.

Agent-Origin: Claude
