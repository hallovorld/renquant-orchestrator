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

1. **`runner_execmath.py:36`** — **CLOSED 2026-07-10**. The last integer
   truncation on the buy path (`affordable = int(cash // price)` in
   `cap_buy_order_to_cash`) is fixed AND owned by the correct repo, not carried
   under an exception. Sequence: Codex's r2 review on this PR correctly rejected
   labelling umbrella#454 a "time-bounded migration exception" — no owner PR,
   milestone, or removal path existed, so the label was rhetoric. The cash-cap
   sizing math was moved to `renquant-execution#25`
   (`src/renquant_execution/order_math.py::cap_affordable_qty`, MERGED
   2026-07-10T06:17:59Z), importing `MIN_FRACTIONAL_NOTIONAL_USD` from that
   repo's own `broker.py` rather than duplicating a cross-repo constant.
   `RenQuant#454` (MERGED 2026-07-10T06:38:28Z) was reworked into a thin
   delegating call-site in `cap_buy_order_to_cash`: it imports
   `cap_affordable_qty` from `renquant_execution.order_math` and calls it;
   `ImportError` fail-closes to the pre-existing whole-share `int()` cap (never
   local fractional math) with `log.warning("EXECMATH-CASHCAP-FALLBACK: ...")`.
   Both "owner present" and "owner absent" scenarios are test-verified. The
   umbrella no longer owns this math — no exception, no removal plan needed,
   because there is nothing left to remove.
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
complete only after (1) strategy-104 #46 + a `software_stops` config key merge,
(2) pins bump, and (3) the recorded stage-3 shadow + pager gates pass. The
execmath gap (former prerequisite 1) is CLOSED — no exception pending, no
architectural detour outstanding.

**PROCEED with the remaining prerequisites** [recommendation]. Marginal cost is
config merges + a shadow window; the A-3 arm-B ledger provides a free
before/after baseline and S-FRAC v2 §7.6 success criteria are already frozen
(PnL-independent).

Operator decisions requested:
1. Merge strategy-104 #46 (already codex-APPROVED, structurally blocked on the
   `require_last_push_approval` deadlock — separate operator-level fix needed)
   + software_stops key
2. Start the stage-3 shadow window (calendar time; runs parallel to Governor S1)
3. At enable time (NOT now): sign off the machine-death risk ASSUMPTION with the
   tail scenarios above on record
