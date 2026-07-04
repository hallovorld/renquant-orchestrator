# S-TC diagnostic: QP infeasibility — leading hypothesis for TC = -0.43

DATE: 2026-07-04

## Finding

The measured TC = -0.43 is NOT a uniform problem. It decomposes by QP
solver status, but the split is only defined over the runs that pass
`min_candidates=5` (both `kelly_target_pct` and `qp_target_w` non-null),
which today is a small population: 18 live runs.

| QP status  | n_runs | frac | TC mean |
|------------|--------|------|---------|
| infeasible |     14 |  78% |  -0.68  |
| optimal    |      4 |  22% |  +0.44  |

(Re-measured 2026-07-04 against the current `runs.alpaca.db`; the
initial pass had counted 15/7 — the DB has moved since. Re-run
`measure_tc()` before quoting these numbers again, they will keep
drifting as more runs land.)

When the QP solver finds a feasible solution, TC is **healthy** (+0.44).
The overall negative TC is dominated by the runs where the QP is
**infeasible** and falls back to prior weights — prior weights are
anti-correlated with current Kelly targets because they reflect stale
holdings from previous model scores.

### Evidence-boundary correction (this round)

`tc_summary()` previously computed this split via
`for label, mask in [("infeasible", True), ("optimal", False)]` — i.e. it
took a boolean `qp_infeasible` flag and labeled the `False` bucket
`"optimal"`. That silently folds every non-infeasible outcome into
"optimal", including a run whose `qp_status` was never stamped at all.

Checked against the real DB (`runs.alpaca.db`, read-only): among ALL live
runs (not just the 18 that clear `min_candidates=5`), **33,282 of 33,304
runs (99.9%) have a blank `qp_status`** — only 15 are `infeasible` and 7
are `optimal` at the run level. None of the 33,282 blank-status runs
happen to clear the `min_candidates=5` filter today, so the 14/4 numbers
above are not currently corrupted by this bug — but the code would have
silently mislabeled any blank-status run that did qualify as evidence of
solver success. Fixed by classifying on the actual `qp_status` string
(`infeasible` / `optimal` / `missing` / `other:<value>`) instead of a
collapsed boolean. See `qp_status_category` column on
`compute_tc_per_run()` output and the `by_qp_status` breakdown in
`tc_summary()`.

Given only 18 runs clear the sizing filter and only 22 runs total (out of
33,304) have `qp_status` recorded at all, this remains a **small-sample
diagnostic** — treat the ROI estimate below as directional, not as a
validated claim, until the pipeline stamps `qp_status` on a much larger
share of runs.

## Leading hypothesis (diagnostic, not yet validated)

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

## Potential impact (contingent on the hypothesis validating — NOT established)

IF the infeasible/optimal split above holds at scale (it currently does not
have enough support to say so — 18 qualifying runs, 22/33,304 total runs with
`qp_status` stamped at all), fixing QP feasibility would be a high-ROI lever:
- Projected TC swing: -0.43 → ~+0.44 (ΔTC ≈ +0.9), based on the 18-run sample
  only — treat this as a back-of-envelope scale estimate, not a forecast
- IR = TC × IC × √BR — this is a multiplicative factor on all model value
  IF the projection above holds

This is a projection from a small sample (see evidence-boundary note above),
not a validated result — see #309 for the hypothesis-driven design that
enumerates competing explanations and states an explicit falsification
criterion before committing to this fix path.

## Fix candidates (pipeline-side, NOT orchestrator)

1. Switch C2 retry policy from "strict" to "relax" or "drop"
2. Increase `qp_turnover_max` from 0.30 to 0.50+
3. Widen per-asset box bounds (exposure scaling is aggressive)
4. Add a soft cash-drag penalty fallback (already exists in code)

## Implementation

Added `qp_status`, `qp_status_category`, and `qp_infeasible` columns to
`compute_tc_per_run()` output, and an honest `by_qp_status` breakdown
(grouped by the real `qp_status_category` value — `infeasible` / `optimal`
/ `missing` / `other:<value>` — not a collapsed boolean) to `tc_summary()`.
13 tests pass (added `test_tc_missing_qp_status_not_counted_as_optimal`
covering the fixed case).

### Round 3: narrowed causal framing (this round)

Round 2 fixed the taxonomy bug itself (collapsed boolean → honest
`qp_status_category` grouping). Codex's round-2 review confirmed the
implementation is now correct but held the PR because the title and this
doc's headline still presented a small-sample diagnostic (18 qualifying
runs, 22/33,304 total runs with `qp_status` stamped at all) as a settled
"root cause" finding with an established causal projection
(`-0.43 -> +0.44`).

Fixed by renaming this doc's own title and the "Root cause" section to
"leading hypothesis" / diagnostic framing, rewording the "Impact" section
to be explicitly conditional ("IF the hypothesis validates..."), and
updating the PR title/body to match (dropped "root cause" language,
corrected the stale pre-taxonomy-fix numbers referenced in the original
PR body). No code/logic change — the implementation itself was already
accepted as correct in round 2; this round is scoped entirely to claim
discipline in the title, PR body, and progress doc.
