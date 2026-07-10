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
| Fractional needs software stops | **BUILT, unarmed**: ratchet-only `software_stops.py` registry + `SoftwareStopExitTask` wired into SellOnlyPipeline; Z9 routes fractional to it. Alpaca structural fact: fractional = TIF DAY only, no GTC → broker-side dead-box stop impossible. Machine-death loss is an **operator risk ASSUMPTION, not a mechanical bound**: 10% fractional book cap × an ASSUMED ≤20% adverse move during the unprotected window ≈ 2% PV; a 40% gap scenario ≈ 4% PV. The only hard levers are lowering `fractional_max_book_pct` or an intraday kill-switch flatten. Pager SLA demonstration = hard pre-enable kill condition, NOT yet done |
| Uncertain EV | **Dissolved by re-scoping**: fractional no longer claims cash-drag deployment (parking sleeve owns that; Governor L1 owns deployment). Its value is SIZING FIDELITY — measured ~2.9× round-up overshoot on BLK ($950 share vs $324 target) and ~11% undershoot on cheap names under whole-share + one-share floor |

## Remaining gap inventory

1. **`runner_execmath.py:36`** (umbrella): `affordable = int(cash // price)` in
   `cap_buy_order_to_cash` — the ONLY remaining integer truncation on the buy path.
   Fires only when a buy exceeds available cash; under fractional sizing it would
   silently truncate a cash-capped resize to whole shares. Fix = fractional-aware
   6dp floor, conditional on the flag (flag-off byte-identical); extend the AST
   auditor (`check_commit_path_no_int_truncation.py`) to order-sizing casts.
   **Repo-ownership note (review point accepted)**: this logic lives in the
   umbrella because the entire RunnerAdapter layer is umbrella-resident legacy —
   the fix must land where the bug lives. This is a TIME-BOUNDED MIGRATION
   EXCEPTION, not a proposed architecture: the target owner for execution math is
   renquant-execution, and the adapter-migration program (moving RunnerAdapter
   order math into the execution repo) is the removal plan. Until that migration,
   any change to umbrella-resident order math must carry this exception label and
   must not add NEW umbrella-owned capabilities beyond closing the S-FRAC v2
   contract gap.
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
- The real accepted risk is the machine-death window — an operator sign-off item
  on an ASSUMPTION (≈2% PV at an assumed ≤20% adverse move; ≈4% at a 40% gap),
  not an engineered bound.

## Conclusion: capability inventory (not a readiness claim)

This memo is a CAPABILITY INVENTORY. The live path is NOT ready: prerequisites are
complete only after (1) the execmath fix merges under the documented migration
exception, (2) strategy-104 #46 + a `software_stops` config key merge, (3) pins
bump, and (4) the recorded stage-3 shadow + pager gates pass.

**PROCEED with the prerequisites** [recommendation]. Marginal cost is one small
flag-conditional fix + config merges + a shadow window; the A-3 arm-B ledger
provides a free before/after baseline and S-FRAC v2 §7.6 success criteria are
already frozen (PnL-independent).

Operator decisions requested:
1. Approve the `runner_execmath.py:36` fix PR (umbrella #454, flag-conditional,
   flag-off byte-identical test-pinned) under the time-bounded migration exception
2. Merge strategy-104 #46 (already codex-APPROVED) + software_stops key
3. Start the stage-3 shadow window (calendar time; runs parallel to Governor S1)
4. At enable time (NOT now): sign off the machine-death risk ASSUMPTION with the
   tail scenarios above on record
