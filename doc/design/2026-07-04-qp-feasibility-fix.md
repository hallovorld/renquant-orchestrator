# QP feasibility — a leading hypothesis for TC degradation, pending validation

DATE: 2026-07-04
STATUS: DESIGN (not yet implemented) — HYPOTHESIS, staged validation required before Stage 1+
SPRINT: S-TC follow-on
REPO: renquant-pipeline (changes), renquant-orchestrator (measurement)

## Evidence boundary

The transfer coefficient TC = corr(w_kelly, w_qp) is measured at -0.43 on
**22 live runs** (PR #305 / #308) — a small sample by any standard; a single
regime shift, a handful of atypical sessions, or a transient config change
could all move this number substantially. This design should be read as a
**leading hypothesis**, not an established diagnosis.

The infeasible/optimal breakdown below (15/7) is itself under active
revision: PR #308 originally collapsed *every non-infeasible run* into the
label `optimal` via a binary `True`/`False` split on the infeasible flag,
which means the true "solver actually succeeded cleanly" count could be
lower than 7 if any runs carried a missing, unexpected, or otherwise
non-infeasible-but-non-optimal `qp_status` — those would have been silently
folded into "optimal" and could be muddying the TC ≈ +0.63 signal in the
"succeeds" bucket. #308 is being corrected to use an honest status taxonomy;
**the specific counts and per-bucket TC means below should be re-verified
against #308's corrected output before this design is used as a basis for
implementation**, not treated as final.

TC enters the Grinold–Kahn identity multiplicatively:

    IR = TC × IC × √BR

so a negative TC would mean the portfolio construction stack is destroying
model information — the optimizer's output is anti-correlated with what the
model recommends — *if* the measurement holds up under more data and a
corrected taxonomy.

## Competing explanations

QP infeasibility is one candidate explanation for the negative TC. It is not
the only one, and the current evidence does not yet rule the others out:

- **QP feasibility (this doc's hypothesis)**: the solver can't find a
  feasible point under the current constraint set, so a stale-weights
  fallback fires and drags TC negative. Plausible: the constraint audit
  below shows genuinely tight turnover caps relative to book size. Not yet
  confirmed: whether infeasibility is *causally* linked to the negative TC
  runs specifically, versus merely correlated in a 22-run sample.
- **Gating loss**: upstream signal or admission-gate logic could be
  discarding otherwise-valid high-Kelly candidates before they ever reach
  the QP, so the QP is optimizing over a smaller/decayed candidate set than
  the Kelly weights assume — a mismatch that would look like "the optimizer
  disagrees with the model" without infeasibility being the driver at all.
  Not yet checked in this design.
- **Stale holdings**: if the position snapshot the QP starts from is
  lagged relative to the Kelly weights' inputs, `w_current` and `w_kelly`
  are being compared across different points in time, which could produce
  spurious anti-correlation independent of solver feasibility. Not yet
  checked.
- **Status-mapping ambiguity**: the exact #308 taxonomy issue above — some
  fraction of runs currently bucketed as "optimal" may not have cleanly
  succeeded, which would inflate the apparent optimal-bucket TC and/or
  understate the true infeasible fraction, changing the shape of the
  decomposition below in either direction.

## Falsification criterion

This hypothesis is falsified if either of the following holds once #308's
corrected taxonomy and more live samples are available:
- Infeasible runs are a small minority of total runs (i.e., the 68% figure
  was an artifact of a short/atypical measurement window), **or**
- Pipeline-side telemetry (`renquant_pipeline.kernel.decision_trace.qp_trace_maps`
  and the QP status recorded in `kernel/portfolio_qp/qp_solver.py` /
  `tasks.py`) shows TC degradation occurring even on runs where `qp_status`
  is confirmed cleanly `optimal` under the corrected taxonomy — that would
  mean feasibility isn't the driver and one of the competing explanations
  above needs investigating instead.

### Root cause decomposition (PRE-#308-FIX NUMBERS — re-verify before use)

| QP status  | n_runs | frac | TC mean | Interpretation                      |
|------------|--------|------|---------|-------------------------------------|
| infeasible |     15 |  68% |  -0.69  | Fallback to prior weights (stale)   |
| optimal    |      7 |  32% |  +0.63  | QP solves, preserves signal well    |

Under the ORIGINAL (uncorrected) taxonomy, the overall -0.43 does not look
like a QP quality problem — it looks like a QP feasibility problem: when the
solver succeeds, TC ≈ +0.63. 68% of runs hit `infeasible:infeasible` (all 3
cvxpy solvers find no feasible point) under this same original taxonomy, so
the fallback `qp_target_w = w_current` (hold flat) kicks in. Prior weights
are anti-correlated with current Kelly because they reflect stale scores —
**this reasoning chain is only as sound as the taxonomy it's built on**,
which is why Stage 0.5 below re-runs this decomposition against #308's fix
before anything downstream proceeds.

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
little apparent room for the solver to reach desired weights, and — on the
current (pre-#308-fix) numbers — the anti-churn controls correlate with
more value lost (TC = -0.69 on the 68% bucket) than the churn they prevent.
This is a plausible mechanism, not yet a demonstrated one; Stage 0.5 below
is the gate before treating it as confirmed.

## Proposed fix (staged, conditional on validation)

Stages 1-4 are **not authorized to start** until Stage 0.5 passes. This
design previously presented the recovery path (-0.43 → +0.57) as already
established; it is not — it is the expected outcome *if* the QP-feasibility
hypothesis survives validation, and should be read that way throughout.

### Stage 0: diagnostic (DONE — PR #308, correction in flight)

`tc_summary()` reports a `by_qp_status` breakdown so any TC report shows
the infeasible/optimal split. A follow-up correction to the status
taxonomy is in progress (see Evidence boundary above) to stop collapsing
non-infeasible-but-non-optimal statuses into "optimal"; Stage 0.5 depends
on that correction landing first.

### Stage 0.5: confirm the diagnosis in pipeline-side telemetry (gate — must pass before Stage 1)

Before any pipeline-side change is proposed for implementation:

1. Re-run the root-cause decomposition above against #308's corrected
   taxonomy and report the corrected counts/means — do not carry the
   -0.43/+0.57/68% figures forward if they change materially.
2. Cross-check the QP status recorded in orchestrator's TC measurement
   against the pipeline's own solver telemetry for the same runs —
   `renquant_pipeline.kernel.decision_trace.qp_trace_maps` and the status
   values set in `kernel/portfolio_qp/qp_solver.py` / `tasks.py` — to
   confirm the two sides agree on which runs were actually infeasible
   (rules out status-mapping ambiguity as an explanation).
3. Check whether TC on confirmed-`optimal` runs holds up as positive once
   the taxonomy is corrected (rules out the possibility that the "optimal"
   bucket's healthy TC was itself partly an artifact of mislabeled runs).
4. Spot-check a handful of infeasible runs' holdings timestamps against
   the Kelly-weight computation timestamp for staleness (rules out the
   stale-holdings competing explanation) and check whether the admission
   gate dropped any high-Kelly names before the QP saw them (rules out the
   gating-loss competing explanation).

If (2)-(4) contradict the feasibility hypothesis per the falsification
criterion above, this design should be abandoned or narrowed in favor of
whichever competing explanation the telemetry actually supports, rather
than proceeding to Stage 1.

### Stage 1: C2 retry policy → "relax" (pipeline PR, conditional on Stage 0.5)

Switch `c2_retry_policy` from `"strict"` to `"relax"`. This multiplies
sector and correlation caps by 1.5× and retries once before declaring
infeasible. Zero risk to position sizes — only loosens inter-name caps.

**Expected impact**: converts some infeasible runs to optimal, reduces the
infeasible fraction. Minimal risk (caps are already conservative).

### Stage 2: turnover cap bump (pipeline config change, conditional on Stage 0.5)

Increase `qp_turnover_max` from 0.15/0.20 to 0.35/0.40. The current caps
were set 2026-05-23 for churn reduction, but with 5-7 name books and
commission-free trading, a 15% turnover cap means the QP can only trade
~1.5 names per day at 10% weight each — too tight.

**Expected impact**: this is the most likely binding constraint. A 35%
turnover cap still limits daily rebalancing reasonably while giving the
solver room to find a feasible point.

### Stage 3: soft-turnover migration (pipeline code change, conditional on Stage 0.5 + Stages 1-2 results)

Move turnover from a hard constraint to a soft penalty in the objective:
`-kappa_turnover * ||dw||₁`. **This does not make the QP always feasible** —
budget, box, wash-sale, sector, and correlation constraints remain in the
constraint set and can still conflict with each other independent of
turnover. What this stage removes is *turnover-driven* infeasibility
specifically: our working hypothesis (per the root-cause decomposition
above, pending Stage 0.5 re-verification) is that turnover is the dominant
binding constraint in the observed infeasible runs, so eliminating it as a
hard constraint should resolve most of them — not all, and not by
mathematical guarantee.

**Expected impact**: reduces infeasibility attributable to the turnover cap.
The linear transaction cost term `kappa` already penalizes trading; the hard
cap is redundant protection for that specific constraint — but the QP can
still come back infeasible on the other five constraints listed under "Why
the constraint set is infeasible" above. Stage 4's fallback improvement
exists precisely because some non-zero infeasible rate is expected to
remain (see the ~5% Full (1-4) projection in Success metric below, not 0%).

### Stage 4: infeasibility fallback improvement (pipeline code change, conditional on Stage 0.5)

When the QP is infeasible despite the above, use a better fallback than
`w_current`:
- Option A: equal-weight the top-K Kelly targets (preserves signal direction)
- Option B: solve an LP (feasibility problem) to find the closest feasible
  point to the Kelly allocation
- Option C: solve the QP with only budget + box constraints (drop sector/corr)

If the feasibility hypothesis holds, any of these should improve TC on
runs that remain infeasible, instead of the current ~-0.69 on that bucket.

## Success metric (projected — contingent on Stage 0.5 confirming the hypothesis)

The table below carries forward the pre-#308-fix numbers only as an
illustration of the *shape* of expected improvement if the hypothesis
holds. Treat every non-"Current" cell as a projection to be replaced once
Stage 0.5 produces corrected figures — not a committed target.

| Metric               | Current (pre-fix, re-verify) | Stage 1  | Stage 1+2 | Full (1-4) |
|----------------------|-------------------------------|----------|-----------|------------|
| Infeasible rate       | 68%                           | ~50%     | ~20%      | ~5%        |
| TC mean               | -0.43                         | ~-0.10   | ~+0.40    | ~+0.55     |
| IR multiplier (vs 0)  | -0.43×                        | ~-0.10×  | ~+0.40×   | ~+0.55×    |

## Implementation ownership

Stages 1-4 (once authorized by Stage 0.5) are **pipeline-side changes**
(renquant-pipeline). The orchestrator owns the measurement (S-TC module,
PR #305/#308) and will track the TC time series to (a) re-run Stage 0.5's
validation once #308 lands, and (b) verify improvement after each stage
deploys, so that a stage which doesn't move TC in the expected direction
is caught rather than assumed to have worked.

## Risk assessment

- Stage 1 (relax C2): LOW — loosens inter-name caps by 1.5×, no single-name
  risk change. Reversible (config flag).
- Stage 2 (turnover 50%): LOW-MEDIUM — still caps daily rebalancing at half
  the book. The broker is commission-free, but higher turnover is not
  cost-free: slippage and spread-capture costs scale with trade frequency,
  and faster rebalancing could degrade realized IR even absent explicit
  commissions. This should be monitored via the TC time series (S-TC
  module) alongside the infeasible-rate metric during rollout, not assumed
  benign because commissions are zero. Reversible.
- Stage 3 (soft turnover): MEDIUM — removes the hard trading cap. Needs
  parameter tuning for the penalty coefficient. Should shadow-run first.
- Stage 4 (fallback): LOW — only fires on infeasible runs which currently
  produce no-trade (zero value). Any positive TC is an improvement.
