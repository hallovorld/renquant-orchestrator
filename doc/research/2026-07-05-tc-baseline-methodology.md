# S-TC baseline methodology — transfer coefficient measurement

DATE: 2026-07-05
STATUS: REFERENCE (methodology documentation for the TC measurement program)

## Theory

The Grinold-Kahn fundamental law of active management decomposes information
ratio as:

    IR = TC × IC × √BR

where TC (transfer coefficient) = corr(w_unconstrained, w_constrained) measures
how much of the model's information survives the portfolio construction stack.
A TC of 0.4 means 60% of the model's cross-sectional signal is lost to
constraints (position limits, sector caps, correlation caps, whole-share
rounding, cash constraints, etc.).

Source: Clarke, de Silva, Thorley (2002) "Portfolio Constraints and the
Fundamental Law of Active Management."

## Implementation history

Three artifacts exist, each building on the previous:

1. **POC** (`scripts/poc_transfer_coefficient.py`, PR #234, 3 Codex review
   rounds) — exploratory diagnostic; two measurements (full-book + buy-side
   decision-TC); 12 tests. Not scheduled.

2. **transfer_coefficient.py** (PR #305, merged) — TC = corr(kelly_target_pct,
   qp_target_w) per run from candidate_scores. CLI via `rq-tc`. Measures the
   QP-stage transfer specifically.

3. **tc_measurement.py** (PR #391, under review) — standing daily batch job
   computing buy-side decision-TC per canonical run, persisting to
   `decision_ledger.db::tc_metrics`. Evolution of the POC methodology.

## Buy-side decision-TC methodology (tc_measurement.py)

### Population

For each canonical daily run (one per run_date, latest `created_at`):

1. **Eligible candidates**: `role='candidate' AND mu >= 0.03 AND
   kelly_target_pct IS NOT NULL`. Minimum 4 eligible to proceed.

2. **Admission taxonomy** (3-round refinement, derived from pipeline writer
   code — not guessed from string values):

   | Category | `blocked_by` values | Pipeline stage |
   |---|---|---|
   | PRE_SELECTION | wash_sale, sector, correlation, tier, defensive_non_bear, candidate_not_selected | Before sizing (selection.py::run_selection_loop) |
   | SIZING_FAILED | buy_blocked, skip_buys, size_bad_price, size_insufficient_cash, size_cash_invariant, kelly_zero:capped_zero, bear_defensive_slot_cap, bear_defensive_insufficient_cash | After selection (task_selection.py::SizeAndEmitTask) |
   | SELECTED_SUBMITTED | broker_pending_submitted | Selected + submitted; fill unconfirmed at trace time |
   | BROKER_OUTCOME | broker_skip:* | Post-selection broker-stage skip |
   | UNCLASSIFIED | anything else | Excluded from both sides |

3. **Sizing population** (`n_survived_admission`): everyone EXCEPT
   `pre_selection_blocked` and `unclassified`. Minimum 4 to proceed.

4. **Correlation population** (`n_corr_population`): sizing population MINUS
   `selected_submitted` names with no confirmed fill (their true delivered
   weight is unknown, not zero).

### Computation

- **w_star** = `kelly_target_pct` (the model's unconstrained Kelly weight)
- **w_actual** = `target_pct` from `trades` table for buy actions; 0.0 for
  names in the correlation population that were not bought

TC = Pearson corr(w_star, w_actual) over the correlation population.

### Category assignment

Each run gets exactly one category:

| Category | Condition | TC reported |
|---|---|---|
| `insufficient_sizing_population` | < 4 names survived admission | None |
| `insufficient_corr_population` | < 4 in correlation population | None |
| `no_deployment` | 0 buys in corr population | None |
| `zero_dispersion` | All buys at same target_pct (Pearson undefined) | None |
| `measured` | Genuine Pearson correlation computable | Yes |

Only `measured` runs enter the rolling mean/SE.

### Exposure transfer ratio (ETR)

Complement metric for magnitude sensitivity. Pearson TC is scale-invariant —
it cannot detect uniform deployment shrinkage (if w_actual = k × w_star for
constant k, Pearson reads 1.0 regardless of k).

ETR = dot(w_actual, w_star) / dot(w_star, w_star)

This is the OLS-through-origin slope: if w_actual is a uniformly shrunk copy
of w_star, ETR ≈ k. Reported alongside, never instead of, TC.

### Persistence

Results are appended to `decision_ledger.db::tc_metrics` (WAL mode, busy
timeout 5s). Schema:

```sql
CREATE TABLE tc_metrics (
  run_id TEXT PRIMARY KEY,
  run_date TEXT NOT NULL,
  category TEXT NOT NULL,
  buy_side_tc REAL,
  exposure_transfer_ratio REAL,
  n_eligible INTEGER NOT NULL,
  n_survived_admission INTEGER NOT NULL,
  n_corr_population INTEGER NOT NULL,
  n_bought INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Idempotent: `INSERT OR IGNORE` on run_id.

## Canonical run selection

A "canonical daily run" is defined as:

1. `run_id LIKE '%-live-%'` (live runs only)
2. `>= 80` candidate_scores rows (MIN_FULL_RUN_CANDIDATES — excludes partial
   or test runs)
3. One per `run_date`: the row with max `created_at` (last completed run that
   day supersedes an earlier same-day attempt)

This deduplication was added in round 2 to fix double-counting on dates with
multiple runs (e.g., 2026-06-09 had two entries in the raw pipeline_runs
table).

## Known limitations

1. **Small sample**: as of 2026-07-02, only 4 `measured`-category runs exist
   (mean TC = 0.288, SE = 0.167, n=4). Far too small for a stable estimate.
   The standing job accumulates more observations automatically.

2. **No full-book same-day TC**: the POC's full-book measurement pairs live
   broker positions against the latest run's desired vector — a cross-day
   pairing (explicitly flagged `same_day_aligned: false`). A genuine
   same-timestamp measurement requires the S5 decision ledger to persist
   per-run position snapshots.

3. **Taxonomy completeness**: the `_classify_reason` taxonomy covers all
   `blocked_by` values observed in the data through 2026-07-02
   (`n_unclassified = 0` on every run). New pipeline reasons would fall to
   `unclassified` and be excluded from both populations — safe by default but
   requiring taxonomy updates.

4. **Kelly-target vs QP-target**: `tc_measurement.py` measures TC against
   `kelly_target_pct` (unconstrained intent). `transfer_coefficient.py` (PR
   #305) measures against `qp_target_w` (QP-constrained weight). These are
   complementary: kelly→actual captures the FULL stack; kelly→qp captures
   the QP optimizer specifically.

## Readiness monitor integration

`readiness_monitor.py` check `S_TC_baseline` requires ≥10 `measured`-category
sessions before reporting READY. This gates downstream automation that depends
on a stable TC baseline.

## Cross-references

- POC script: `scripts/poc_transfer_coefficient.py`
- POC progress (3 rounds): `doc/progress/2026-07-02-s-tc-measurement.md`
- QP-stage TC module: `src/renquant_orchestrator/transfer_coefficient.py`
- Standing measurement: `tc_measurement.py` (PR #391)
- Unified master plan TC term: #231 §1
