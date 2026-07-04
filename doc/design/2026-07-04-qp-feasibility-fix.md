# QP feasibility fix — recovering TC from -0.43 to +0.57

DATE: 2026-07-04
STATUS: DESIGN (not yet implemented)
SPRINT: S-TC follow-on, highest-priority lever
REPO: renquant-pipeline (changes), renquant-orchestrator (measurement)

## Problem statement

The transfer coefficient TC = corr(w_kelly, w_qp) is measured at -0.43 on 22
live runs (PR #305 / #308). TC enters the Grinold–Kahn identity multiplicatively:

    IR = TC × IC × √BR

so a negative TC means the portfolio construction stack is **destroying model
information** — the optimizer's output is anti-correlated with what the model
recommends.

### Root cause decomposition

| QP status  | n_runs | frac | TC mean | Interpretation                      |
|------------|--------|------|---------|-------------------------------------|
| infeasible |     15 |  68% |  -0.69  | Fallback to prior weights (stale)   |
| optimal    |      7 |  32% |  +0.63  | QP solves, preserves signal well    |

The overall -0.43 is not a QP quality problem — it's a **QP feasibility
problem**. When the solver succeeds, TC ≈ +0.63 (healthy). But 68% of runs
hit `infeasible:infeasible` (all 3 cvxpy solvers find no feasible point), so
the fallback `qp_target_w = w_current` (hold flat) kicks in. Prior weights
are anti-correlated with current Kelly because they reflect stale scores.

### Why the constraint set is infeasible

Hard constraints in the QP (from `qp_solver.py` + `tasks.py`):

1. Budget: `sum(w) <= 1 - cash_reserve`
2. Per-asset box bounds (position caps × exposure scaling × conviction)
3. **Turnover cap: `||dw||₁ <= 0.30`** (qp_turnover_max)
4. Wash-sale masks: `dw[i] <= 0` for wash-flagged names
5. Sector caps: per-sector weight sum
6. Correlation group caps: `w[i] + w[j] <= group_cap` for |corr| ≥ 0.70

Actual config values (strategy_config.json):
- `qp_turnover_max`: **0.15 (BULL_CALM) / 0.20 (global)** — tighter than
  the code default of 0.30. Set 2026-05-23 by Codex for churn reduction.
- `qp_c2_infeasible_policy`: **"strict"** — explicitly "block orders rather
  than relax risk constraints". Set 2026-05-24.
- `qp_dw_max`: 0.50 (per-asset max trade size — reasonable).

The turnover caps + strict C2 policy + existing position structure leave
no room for the solver to reach desired weights. The anti-churn controls
are destroying more value (TC = -0.69 on 68% of runs) than the churn they
prevent.

## Proposed fix (staged)

### Stage 0: diagnostic (DONE — PR #308)

`tc_summary()` now reports `by_qp_status` breakdown. Any TC report
immediately shows the infeasible/optimal split.

### Stage 1: C2 retry policy → "relax" (pipeline PR)

Switch `c2_retry_policy` from `"strict"` to `"relax"`. This multiplies
sector and correlation caps by 1.5× and retries once before declaring
infeasible. Zero risk to position sizes — only loosens inter-name caps.

**Expected impact**: converts some infeasible runs to optimal, reduces the
infeasible fraction. Minimal risk (caps are already conservative).

### Stage 2: turnover cap bump (pipeline config change)

Increase `qp_turnover_max` from 0.15/0.20 to 0.35/0.40. The current caps
were set 2026-05-23 for churn reduction, but with 5-7 name books and
commission-free trading, a 15% turnover cap means the QP can only trade
~1.5 names per day at 10% weight each — too tight.

**Expected impact**: this is the most likely binding constraint. A 35%
turnover cap still limits daily rebalancing reasonably while giving the
solver room to find a feasible point.

### Stage 3: soft-turnover migration (pipeline code change)

Move turnover from a hard constraint to a soft penalty in the objective:
`-kappa_turnover * ||dw||₁`. This makes the QP always feasible (removing
turnover from the constraint set removes the most binding constraint) while
still penalizing excessive trading.

**Expected impact**: eliminates infeasibility from turnover entirely. The
linear transaction cost term `kappa` already penalizes trading; the hard cap
is redundant protection.

### Stage 4: infeasibility fallback improvement (pipeline code change)

When the QP is infeasible despite the above, use a better fallback than
`w_current`:
- Option A: equal-weight the top-K Kelly targets (preserves signal direction)
- Option B: solve an LP (feasibility problem) to find the closest feasible
  point to the Kelly allocation
- Option C: solve the QP with only budget + box constraints (drop sector/corr)

Any of these would yield TC > 0 on infeasible runs instead of TC ≈ -0.69.

## Success metric

| Metric               | Current | Stage 1  | Stage 1+2 | Full (1-4) |
|----------------------|---------|----------|-----------|------------|
| Infeasible rate      | 68%     | ~50%     | ~20%      | ~5%        |
| TC mean              | -0.43   | ~-0.10   | ~+0.40    | ~+0.55     |
| IR multiplier (vs 0) | -0.43×  | ~-0.10×  | ~+0.40×   | ~+0.55×    |

## Implementation ownership

Stages 1-4 are **pipeline-side changes** (renquant-pipeline). The orchestrator
owns the measurement (S-TC module, PR #305/#308) and will track the TC
time series to verify improvement after each stage deploys.

## Risk assessment

- Stage 1 (relax C2): LOW — loosens inter-name caps by 1.5×, no single-name
  risk change. Reversible (config flag).
- Stage 2 (turnover 50%): LOW — still caps daily rebalancing at half the book.
  Commission-free broker means no cost impact. Reversible.
- Stage 3 (soft turnover): MEDIUM — removes the hard trading cap. Needs
  parameter tuning for the penalty coefficient. Should shadow-run first.
- Stage 4 (fallback): LOW — only fires on infeasible runs which currently
  produce no-trade (zero value). Any positive TC is an improvement.
