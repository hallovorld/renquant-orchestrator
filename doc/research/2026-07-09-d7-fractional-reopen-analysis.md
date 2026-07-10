# D7: Fractional-shares reopen analysis (Deployment Governor RFC deliverable)

STATUS: research memo → operator decision
DATE: 2026-07-09
CONTEXT: RFC #443 D7. Full read-only audit across umbrella / pipeline / execution /
strategy-104 (branches, pins, active commit path). All claims [VERIFIED] by file:line
inspection unless marked.

## Bottom line

**The reopen already happened and is ~80% built.** Fractional was re-scoped and
reopened 2026-07-02 as S-FRAC v2 (orchestrator design RFC #254, merged). Stages 0–2
plus the software-stop registry are merged AND included in the current live pins.
The 2026-06-30 closure objections are each resolved or bounded. What remains is one
small code gap, two config merges + pin bumps, and the stage-3 process gate.

## The 06-30 objections, revisited

| Objection (06-30) | Status now |
|---|---|
| Active path (RunnerAdapter.commit) untested/unwired | **CLOSED**: stage 0 (umbrella #439) made commit float-preserving end-to-end with a machine-verifiable `fractional_capability_gate` + per-buy fail-close + `commit_path_fingerprint=fractional-v2-stage0`; 44 tests. The historic `int(filled_qty)` cast is gone (`normalize_fill_qty`, eps-guarded) |
| Fractional needs software stops | **BUILT, unarmed**: ratchet-only `software_stops.py` registry + `SoftwareStopExitTask` wired into SellOnlyPipeline; Z9 routes fractional to it. Alpaca structural fact: fractional = TIF DAY only, no GTC → broker-side dead-box stop impossible; residual machine-death risk bounded by design at **2% of PV** (10% fractional book cap × 20% worst-case move) with 15-min pager SLA. Pager demonstration = hard pre-enable kill condition, NOT yet done |
| Uncertain EV | **Dissolved by re-scoping**: fractional no longer claims cash-drag deployment (parking sleeve owns that; Governor L1 owns deployment). Its value is SIZING FIDELITY — measured ~2.9× round-up overshoot on BLK ($950 share vs $324 target) and ~11% undershoot on cheap names under whole-share + one-share floor |

## Remaining gap inventory

1. **`runner_execmath.py:36`** (umbrella): `affordable = int(cash // price)` in
   `cap_buy_order_to_cash` — the ONLY remaining integer truncation on the buy path.
   Fires only when a buy exceeds available cash; under fractional sizing it would
   silently truncate a cash-capped resize to whole shares. Fix = fractional-aware
   6dp floor, conditional on the flag (flag-off byte-identical); extend the AST
   auditor (`check_commit_path_no_int_truncation.py`) to order-sizing casts.
2. **strategy-104 PR #46** (`execution.fractional_shares` block, default OFF):
   already APPROVED, unmerged. Merge + add `execution.software_stops.enabled` key.
3. **Pin bumps**: strategy pin predates merged #49 (one-share floor) and #46.
4. **Stage-3 enablement packet** (process, the long pole): ≥10 frozen shadow
   sessions, rollback drill (flag-off with an existing fractional holding stays
   exitable + stop-covered), pager SLA demonstration, operator risk sign-off on the
   2%-of-PV machine-death bound.

## Interaction with the Deployment Governor (RFC #443)

- Governor L3 (integer-aware execution) collapses to exact execution under
  fractional — but the Governor does NOT depend on it (L3 handles whole-share).
- One-share floor (#49, merged) and fractional are complements, not substitutes:
  coded precedence is fractional → one_share_floor → drop; A-3 remains the
  permanent fallback for non-fractionable symbols and gate-fail conditions.
- Neither is the cash-drag fix; deployment belongs to Governor L1 + parking sleeve.

## Risk surface (verified)

- Wash-sale with fractional lots: LOW — stamps are per-ticker not per-lot;
  full-liquidation dust clamped to 0.0 in the same order; $25 anti-churn floor on
  trims/entries.
- Reconciliation: LOW — partial-fill float accumulation, cancel-replace sums, and
  restart stop-routing re-derivation are regression-pinned (stage-0 tests).
- DB schema: NONE — `trades.shares` is already REAL.
- The real accepted risk is the bounded machine-death window (2% PV) — an operator
  sign-off item, not engineering.

## Recommendation and decision asks

**PROCEED** [recommendation]. Marginal cost is one small umbrella PR + config merges
+ a shadow window; the A-3 arm-B ledger provides a free before/after baseline and
S-FRAC v2 §7.6 success criteria are already frozen (PnL-independent).

Operator decisions requested:
1. Approve the `runner_execmath.py:36` fix PR (umbrella, flag-conditional,
   flag-off byte-identical) — being prepared now
2. Merge strategy-104 #46 (already codex-APPROVED) + software_stops key
3. Start the stage-3 shadow window (calendar time; runs parallel to Governor S1)
4. Sign off the 2%-of-PV machine-death bound at enable time (NOT now)
