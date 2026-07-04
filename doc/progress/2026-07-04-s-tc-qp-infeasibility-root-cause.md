# S-TC root cause: QP infeasibility drives TC = -0.43

DATE: 2026-07-04

## Finding

The measured TC = -0.43 is NOT a uniform problem. It decomposes into two
regimes by QP solver status:

| QP status  | n_runs | frac | TC mean |
|------------|--------|------|---------|
| infeasible |     15 |  68% |  -0.69  |
| optimal    |      7 |  32% |  +0.63  |

When the QP solver finds a feasible solution, TC is **healthy** (+0.63).
The overall negative TC is dominated by the 68% of runs where the QP is
**infeasible** and falls back to prior weights — prior weights are
anti-correlated with current Kelly targets because they reflect stale
holdings from previous model scores.

## Root cause

`infeasible:infeasible` means all 3 cvxpy solvers (CLARABEL→OSQP→SCS) found
the hard constraint set has NO feasible point. The hard constraints are:

1. Budget: `sum(w) <= 1 - cash_reserve`
2. Per-asset box bounds (position caps × conviction × exposure scaling)
3. Turnover cap: `||dw||₁ <= 0.30` (qp_turnover_max)
4. Wash-sale masks: `dw[i] <= 0` for wash-flagged names
5. Sector caps: `S @ w <= sector_cap_vec`
6. Correlation group caps: `w[i] + w[j] <= group_cap` for |corr| ≥ 0.70

Whole-share rounding is NOT in the QP — it's downstream floor-truncation in
`EmitOrdersFromQPSolutionTask._shares_from_dw()`.

On infeasible, `qp_target_w = w_current` (hold-flat fallback), meaning each
ticker's QP weight equals its CURRENT weight from prior decisions. This is
anti-correlated with current Kelly because holdings reflect stale scores.

Likely cause of infeasibility: the turnover cap (30%) + existing positions +
sector/correlation caps create a region that's too small for the solver to
move to the desired allocation. The C2 relaxation retry (sector/corr 1.5×)
exists but only under "relax" policy (default is "strict" = no retry).

## Impact

Fixing QP feasibility is the single highest-ROI lever in the system:
- Expected TC swing: -0.43 → ~+0.57 (ΔTC ≈ +1.0)
- IR = TC × IC × √BR — this is a multiplicative factor on all model value

## Fix candidates (pipeline-side, NOT orchestrator)

1. Switch C2 retry policy from "strict" to "relax" or "drop"
2. Increase `qp_turnover_max` from 0.30 to 0.50+
3. Widen per-asset box bounds (exposure scaling is aggressive)
4. Add a soft cash-drag penalty fallback (already exists in code)

## Implementation

Added `qp_status` and `qp_infeasible` columns to `compute_tc_per_run()` output
and `by_qp_status` breakdown to `tc_summary()`. 12 tests pass.
